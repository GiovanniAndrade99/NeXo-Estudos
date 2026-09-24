"""API e página web do demonstrador."""
from pathlib import Path
import os
import logging
import secrets
import time
from time import perf_counter

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
import cv2
import fitz
import numpy as np
from pydantic import BaseModel

from .contas import ErroConta, LimiteTentativas, RepositorioContas, enviar_link_recuperacao, normalizar_email
from .processamento import LIMITE_LADO, codificar_png, decodificar_imagem, processar, tesseract_disponivel

RAIZ = Path(__file__).resolve().parent.parent
PASTA_FRONTEND = RAIZ / "frontend"
load_dotenv(RAIZ / ".env")
TAMANHO_MAXIMO_BYTES = 12 * 1024 * 1024
TIPOS_ACEITOS = {"image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp", "application/pdf"}
MAX_PAGINAS_PDF = 10
SESSAO_CURTA_SEGUNDOS = 8 * 60 * 60
SESSAO_LONGA_SEGUNDOS = 30 * 24 * 60 * 60
# Caminhos acessíveis sem login: a própria tela de login e as rotas de autenticação.
ROTAS_PUBLICAS = {"/login", "/static/login.css", "/static/login.js", "/static/login-hero.jpg", "/api/health"}
PREFIXOS_PUBLICOS = ("/api/auth/", "/auth/")
logger = logging.getLogger(__name__)

contas = RepositorioContas(os.getenv("CONTAS_DB") or RAIZ / "contas.db")
limite_login = LimiteTentativas(maximo=5, bloqueio_segundos=15 * 60)
limite_recuperacao = LimiteTentativas(maximo=5, bloqueio_segundos=15 * 60)

app = FastAPI(
    title="Laboratório de Processamento de Imagens",
    description="Pré-processamento de imagens de estudo e reconhecimento de texto (OCR).",
    version="1.0.0",
)
_arquivo_chave_sessao = RAIZ / ".auth_session_secret"
CHAVE_SESSAO = os.getenv("SESSION_SECRET")
if not CHAVE_SESSAO:
    if _arquivo_chave_sessao.exists():
        CHAVE_SESSAO = _arquivo_chave_sessao.read_text(encoding="utf-8").strip()
    else:
        CHAVE_SESSAO = secrets.token_urlsafe(48)
        _arquivo_chave_sessao.write_text(CHAVE_SESSAO, encoding="utf-8")


def usuario_da_sessao(request: Request) -> dict | None:
    usuario = request.session.get("user")
    if not usuario:
        return None
    if request.session.get("expira_em", 0) < time.time():
        request.session.clear()
        return None
    return usuario


def iniciar_sessao(request: Request, usuario: dict, lembrar: bool = False) -> None:
    request.session.clear()
    request.session["user"] = usuario
    request.session["expira_em"] = time.time() + (SESSAO_LONGA_SEGUNDOS if lembrar else SESSAO_CURTA_SEGUNDOS)


async def exigir_login(request: Request, chamar_proximo):
    caminho = request.url.path
    if caminho in ROTAS_PUBLICAS or caminho.startswith(PREFIXOS_PUBLICOS) or usuario_da_sessao(request):
        return await chamar_proximo(request)
    if caminho.startswith("/api/"):
        return JSONResponse({"detail": "Faça login para continuar."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


# A ordem importa: o middleware adicionado por último roda primeiro, então a sessão é lida antes da verificação de login.
app.add_middleware(BaseHTTPMiddleware, dispatch=exigir_login)
app.add_middleware(
    SessionMiddleware,
    secret_key=CHAVE_SESSAO,
    same_site="lax",
    max_age=SESSAO_LONGA_SEGUNDOS,
    https_only=os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true",
)

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
oauth.register(
    name="github",
    client_id=os.getenv("GITHUB_CLIENT_ID"),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
    authorize_url="https://github.com/login/oauth/authorize",
    access_token_url="https://github.com/login/oauth/access_token",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)
PROVEDORES_OAUTH = {"google", "github"}
app.mount("/static", StaticFiles(directory=PASTA_FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def pagina_inicial():
    return FileResponse(PASTA_FRONTEND / "index.html")


@app.get("/login", include_in_schema=False)
def pagina_login(request: Request):
    if usuario_da_sessao(request) and "reset" not in request.query_params:
        return RedirectResponse("/", status_code=303)
    return FileResponse(PASTA_FRONTEND / "login.html")


@app.get("/api/auth/status")
def status_autenticacao():
    return {
        "providers": {
            "google": bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")),
            "github": bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET")),
        }
    }


@app.get("/api/auth/me")
def usuario_atual(request: Request):
    usuario = usuario_da_sessao(request)
    return {"authenticated": bool(usuario), "user": usuario}


class DadosLogin(BaseModel):
    email: str
    password: str
    remember: bool = False


class DadosCadastro(BaseModel):
    name: str
    email: str
    password: str


class DadosRecuperacao(BaseModel):
    email: str


class DadosNovaSenha(BaseModel):
    token: str
    password: str


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def _mensagem_bloqueio(segundos: int) -> str:
    minutos = max(1, -(-segundos // 60))
    return f"Muitas tentativas. Tente novamente em {minutos} minuto{'s' if minutos > 1 else ''}."


@app.post("/api/auth/login")
def login_senha(request: Request, dados: DadosLogin):
    chaves = (f"ip:{_ip(request)}", f"email:{normalizar_email(dados.email)}")
    bloqueio = limite_login.segundos_bloqueado(*chaves)
    if bloqueio:
        return JSONResponse({"detail": _mensagem_bloqueio(bloqueio), "retry_after": bloqueio}, status_code=429, headers={"Retry-After": str(bloqueio)})
    usuario = contas.autenticar(dados.email, dados.password)
    if not usuario:
        restantes = limite_login.registrar_falha(*chaves)
        if restantes == 0:
            bloqueio = limite_login.segundos_bloqueado(*chaves)
            return JSONResponse({"detail": _mensagem_bloqueio(bloqueio), "retry_after": bloqueio}, status_code=429, headers={"Retry-After": str(bloqueio)})
        texto = f"E-mail ou senha incorretos. Você ainda tem {restantes} tentativa{'s' if restantes > 1 else ''}."
        return JSONResponse({"detail": texto, "remaining": restantes}, status_code=401)
    limite_login.limpar(*chaves)
    iniciar_sessao(request, usuario, dados.remember)
    return {"authenticated": True, "user": usuario}


@app.post("/api/auth/signup", status_code=201)
def cadastrar(request: Request, dados: DadosCadastro):
    try:
        usuario = contas.criar(dados.name, dados.email, dados.password)
    except ErroConta as erro:
        raise HTTPException(400, str(erro)) from erro
    iniciar_sessao(request, usuario)
    return {"authenticated": True, "user": usuario}


@app.post("/api/auth/forgot")
def esqueci_senha(request: Request, dados: DadosRecuperacao):
    chave = f"ip:{_ip(request)}"
    bloqueio = limite_recuperacao.segundos_bloqueado(chave)
    if bloqueio:
        return JSONResponse({"detail": _mensagem_bloqueio(bloqueio)}, status_code=429, headers={"Retry-After": str(bloqueio)})
    limite_recuperacao.registrar_falha(chave)
    token = contas.criar_token_recuperacao(dados.email)
    if token:
        link = str(request.url_for("pagina_login").include_query_params(reset=token))
        try:
            enviar_link_recuperacao(normalizar_email(dados.email), link)
        except OSError:
            logger.exception("Falha ao enviar o e-mail de recuperação de senha")
            raise HTTPException(502, "Não foi possível enviar o e-mail agora. Tente novamente mais tarde.")
    # Mesma resposta com ou sem conta, para não revelar quais e-mails estão cadastrados.
    return {"detail": "Se houver uma conta com este e-mail, enviamos um link para criar uma nova senha. Ele vale por 30 minutos."}


@app.post("/api/auth/reset")
def redefinir_senha(request: Request, dados: DadosNovaSenha):
    try:
        usuario = contas.redefinir_senha(dados.token, dados.password)
    except ErroConta as erro:
        raise HTTPException(400, str(erro)) from erro
    limite_login.limpar(f"email:{usuario['email']}")
    iniciar_sessao(request, usuario)
    return {"authenticated": True, "user": usuario}


# Precisa vir antes de /auth/{provider}, senão "logout" é tratado como nome de provedor.
@app.get("/auth/logout")
def sair(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/auth/{provider}")
async def iniciar_login_oauth(request: Request, provider: str):
    if provider not in PROVEDORES_OAUTH:
        raise HTTPException(404, "Provedor de login desconhecido.")
    variaveis = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET") if provider == "google" else ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET")
    if not all(os.getenv(nome) for nome in variaveis):
        return RedirectResponse(f"/login?error={provider}_not_configured", status_code=303)
    callback = request.url_for("callback_oauth", provider=provider)
    return await getattr(oauth, provider).authorize_redirect(request, callback)


@app.get("/auth/callback/{provider}", name="callback_oauth")
async def callback_oauth(request: Request, provider: str):
    if provider not in PROVEDORES_OAUTH:
        raise HTTPException(404, "Provedor de login desconhecido.")
    cliente = getattr(oauth, provider)
    try:
        if provider == "github":
            token = await cliente.authorize_access_token(request, headers={"Accept": "application/json"})
        else:
            token = await cliente.authorize_access_token(request)
        if provider == "google":
            perfil = token.get("userinfo") or await cliente.userinfo(token=token)
            usuario = {
                "provider": "google",
                "id": str(perfil.get("sub", "")),
                "name": perfil.get("name") or perfil.get("email") or "Usuário Google",
                "email": perfil.get("email"),
                "avatar": perfil.get("picture"),
            }
        else:
            perfil = (await cliente.get("user", token=token)).json()
            resposta_emails = await cliente.get("user/emails", token=token)
            emails = resposta_emails.json() if resposta_emails.is_success else []
            email = perfil.get("email")
            if not email:
                email_primario = next((item for item in emails if item.get("primary") and item.get("verified")), None)
                email = email_primario.get("email") if email_primario else None
            usuario = {
                "provider": "github",
                "id": str(perfil.get("id", "")),
                "name": perfil.get("name") or perfil.get("login") or "Usuário GitHub",
                "email": email,
                "avatar": perfil.get("avatar_url"),
            }
    except Exception:
        # Não expor códigos OAuth ou respostas dos provedores na URL exibida ao usuário.
        logger.exception("Falha ao concluir autenticação OAuth com %s", provider)
        request.session.pop("user", None)
        return RedirectResponse("/login?error=oauth_failed", status_code=303)
    iniciar_sessao(request, usuario)
    return RedirectResponse("/", status_code=303)


@app.get("/api/health")
def health():
    disponivel, aviso = tesseract_disponivel()
    return {"status": "ok", "ocr_disponivel": disponivel, "aviso": aviso}


def _decodificar_pdf(conteudo: bytes) -> list[np.ndarray]:
    try:
        documento = fitz.open(stream=conteudo, filetype="pdf")
    except (fitz.FileDataError, RuntimeError) as erro:
        raise ValueError("O PDF está inválido ou não pôde ser aberto.") from erro
    if documento.is_encrypted:
        raise ValueError("PDF protegido por senha não é aceito.")
    if documento.page_count < 1:
        raise ValueError("O PDF não contém páginas para processar.")
    if documento.page_count > MAX_PAGINAS_PDF:
        raise ValueError(f"O PDF pode ter no máximo {MAX_PAGINAS_PDF} páginas.")

    imagens = []
    for pagina in documento:
        escala = min(2, LIMITE_LADO / max(pagina.rect.width, pagina.rect.height))
        pixmap = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False)
        imagem = cv2.imdecode(np.frombuffer(pixmap.tobytes("png"), dtype=np.uint8), cv2.IMREAD_COLOR)
        if imagem is None:
            raise ValueError("Não foi possível converter uma página do PDF em imagem.")
        imagens.append(imagem)
    documento.close()
    return imagens


@app.post("/api/processar")
async def processar_arquivo(arquivos: list[UploadFile] = File(...)):
    if not arquivos:
        raise HTTPException(400, "Nenhuma imagem foi enviada.")
    if len(arquivos) > 2:
        raise HTTPException(400, "Voce pode enviar no maximo 2 arquivos por vez.")

    resultados = []
    for arquivo in arquivos:
        nome_arquivo = Path(arquivo.filename or "imagem").name
        eh_pdf = nome_arquivo.lower().endswith(".pdf") or arquivo.content_type == "application/pdf"
        tipo_aceito = arquivo.content_type in TIPOS_ACEITOS or (
            eh_pdf and arquivo.content_type in {"application/octet-stream", ""}
        )
        if not tipo_aceito:
            raise HTTPException(415, f"Formato nao aceito para {nome_arquivo}.")
        conteudo = await arquivo.read(TAMANHO_MAXIMO_BYTES + 1)
        if not conteudo:
            raise HTTPException(400, f"O arquivo {nome_arquivo} esta vazio.")
        if len(conteudo) > TAMANHO_MAXIMO_BYTES:
            raise HTTPException(413, f"O arquivo {nome_arquivo} deve ter no maximo 12 MB.")
        try:
            imagens = _decodificar_pdf(conteudo) if eh_pdf else [decodificar_imagem(conteudo)]
            paginas = []
            for indice, imagem in enumerate(imagens, start=1):
                inicio = perf_counter()
                resultado = processar(imagem)
                tempo_ms = round((perf_counter() - inicio) * 1000, 2)
                altura, largura = resultado.original.shape[:2]
                paginas.append({
                    "pagina": indice if eh_pdf else None,
                    "dimensoes": {"largura": largura, "altura": altura},
                    "tempo_processamento_ms": tempo_ms,
                    "inclinacao_corrigida_graus": resultado.inclinacao_corrigida_graus,
                    "ocr_disponivel": resultado.ocr_disponivel,
                    "aviso": resultado.aviso,
                    "texto": resultado.texto,
                    "assistente_estudos": resultado.assistente_estudos,
                    "descricao_processo": resultado.descricao_processo,
                    "imagens": {
                        "original": codificar_png(resultado.original),
                        "tons_cinza": codificar_png(resultado.tons_cinza),
                        "processada": codificar_png(resultado.tratada),
                    },
                })
        except ValueError as erro:
            raise HTTPException(400, str(erro)) from erro
        except (fitz.FileDataError, RuntimeError) as erro:
            raise HTTPException(400, "O PDF esta invalido ou nao pode ser convertido.") from erro
        resultados.append({"nome_arquivo": nome_arquivo, "formato": "PDF" if eh_pdf else "imagem", "paginas": paginas})

    if len(resultados) == 1 and resultados[0]["formato"] != "PDF":
        pagina = resultados[0]["paginas"][0]
        return {"nome_arquivo": resultados[0]["nome_arquivo"], **pagina}
    return {"quantidade": len(resultados), "arquivos": resultados}
