"""Camadas de segurança HTTP: headers, checagem de origem (CSRF) e reCAPTCHA.

O reCAPTCHA (v2, caixa "Não sou um robô") só é exigido quando as chaves
RECAPTCHA_SITE_KEY e RECAPTCHA_SECRET_KEY estão no .env; sem elas, a
verificação é desligada e o restante do site funciona normalmente.
"""
from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

URL_VERIFICACAO_RECAPTCHA = "https://www.google.com/recaptcha/api/siteverify"
METODOS_QUE_ALTERAM = {"POST", "PUT", "PATCH", "DELETE"}

# Scripts só do próprio site e do reCAPTCHA: nada inline, nada de eval.
# Estilos inline são permitidos porque o widget do reCAPTCHA os usa; o risco é baixo sem script inline.
POLITICA_CONTEUDO = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob:",
    "connect-src 'self'",
    "frame-src https://www.google.com/recaptcha/ https://recaptcha.google.com/recaptcha/",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])


def chave_site_recaptcha() -> str | None:
    if os.getenv("RECAPTCHA_SITE_KEY") and os.getenv("RECAPTCHA_SECRET_KEY"):
        return os.getenv("RECAPTCHA_SITE_KEY")
    return None


def verificar_recaptcha(token: str | None, ip: str | None = None) -> bool:
    """Confirma com o Google que o desafio foi resolvido. Sem chaves configuradas, sempre aprova."""
    segredo = os.getenv("RECAPTCHA_SECRET_KEY")
    if not (segredo and os.getenv("RECAPTCHA_SITE_KEY")):
        return True
    if not token:
        return False
    dados = {"secret": segredo, "response": token}
    if ip:
        dados["remoteip"] = ip
    try:
        resposta = httpx.post(URL_VERIFICACAO_RECAPTCHA, data=dados, timeout=10)
        return bool(resposta.json().get("success"))
    except (httpx.HTTPError, ValueError):
        # Falha de rede com o Google: recusa, para o captcha não poder ser contornado derrubando a conexão.
        logger.exception("Não foi possível verificar o reCAPTCHA")
        return False


async def headers_de_seguranca(request: Request, chamar_proximo):
    resposta = await chamar_proximo(request)
    resposta.headers.setdefault("Content-Security-Policy", POLITICA_CONTEUDO)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resposta.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    resposta.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        # Respostas da API trazem dados da conta: não devem ficar em cache.
        resposta.headers.setdefault("Cache-Control", "no-store")
    else:
        # Páginas, scripts e estilos: o navegador pode guardar, mas confere a versão a cada visita
        # (resposta 304 rápida quando nada mudou). Evita ficar preso a um login.js antigo após atualizações.
        resposta.headers.setdefault("Cache-Control", "no-cache")
    if os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true":
        resposta.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resposta


async def bloquear_outras_origens(request: Request, chamar_proximo):
    """Defesa contra CSRF: pedidos que alteram dados precisam vir deste mesmo site.

    O cookie de sessão já é SameSite=Lax; esta checagem cobre navegadores antigos
    e subdomínios. Pedidos sem Origin nem Referer (scripts, testes) seguem, pois
    navegadores sempre enviam um dos dois em POST entre sites.
    """
    if request.method in METODOS_QUE_ALTERAM:
        origem = request.headers.get("origin") or request.headers.get("referer")
        if origem and origem != "null":
            partes = urlsplit(origem)
            host_pedido = request.headers.get("host", "")
            if partes.netloc != host_pedido:
                return JSONResponse({"detail": "Origem do pedido não permitida."}, status_code=403)
        elif origem == "null":
            return JSONResponse({"detail": "Origem do pedido não permitida."}, status_code=403)
    return await chamar_proximo(request)
