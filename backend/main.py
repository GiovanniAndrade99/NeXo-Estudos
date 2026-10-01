"""API e página web do demonstrador."""
from pathlib import Path
import os
import logging
import secrets
import time
from time import perf_counter

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from html import escape
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
import cv2
import fitz
import numpy as np
import base64
import binascii

from pydantic import BaseModel, Field

from .contas import (
    ErroConta, LimiteTentativas, RepositorioContas, email_valido, enviar_email,
    enviar_link_recuperacao, normalizar_email, smtp_configurado,
)
from .processamento import LIMITE_LADO, codificar_png, decodificar_imagem, processar, tesseract_disponivel
from .seguranca import bloquear_outras_origens, chave_site_recaptcha, headers_de_seguranca, verificar_recaptcha

RAIZ = Path(__file__).resolve().parent.parent
PASTA_FRONTEND = RAIZ / "frontend"
load_dotenv(RAIZ / ".env")
TAMANHO_MAXIMO_BYTES = 12 * 1024 * 1024
TIPOS_ACEITOS = {"image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp", "application/pdf"}
MAX_PAGINAS_PDF = 10
SESSAO_CURTA_SEGUNDOS = 8 * 60 * 60
SESSAO_LONGA_SEGUNDOS = 30 * 24 * 60 * 60
# Caminhos acessíveis sem login: a própria tela de login e as rotas de autenticação.
ROTAS_PUBLICAS = {"/login", "/privacidade", "/api/health", "/auth/logout"}
# Versão da política de privacidade aceita no cadastro (LGPD); mude ao alterar o texto da política.
VERSAO_POLITICA = "2026-10-01"
# Arquivos das páginas de login e de privacidade ficam em pastas próprias, liberadas por inteiro;
# os do laboratório (frontend/laboratorio) continuam exigindo login.
PREFIXOS_PUBLICOS = ("/api/auth/", "/static/login/", "/static/privacidade/")
logger = logging.getLogger(__name__)

contas = RepositorioContas(os.getenv("CONTAS_DB") or RAIZ / "contas.db")
limite_login = LimiteTentativas(maximo=5, bloqueio_segundos=15 * 60)
limite_recuperacao = LimiteTentativas(maximo=5, bloqueio_segundos=15 * 60)
# Cada envio conta como uma "tentativa": no máximo 10 e-mails de histórico por usuário a cada hora.
limite_compartilhamento = LimiteTentativas(maximo=10, bloqueio_segundos=60 * 60)
# Cadastros por IP e processamentos por usuário também contam a cada pedido, com ou sem sucesso.
limite_cadastro = LimiteTentativas(maximo=5, bloqueio_segundos=60 * 60)
limite_processamento = LimiteTentativas(maximo=30, bloqueio_segundos=10 * 60)
limite_exclusao = LimiteTentativas(maximo=5, bloqueio_segundos=15 * 60)
TAMANHO_MAXIMO_IMAGEM_EMAIL = 3 * 1024 * 1024

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
# Rodam antes da sessão: barram pedidos de outros sites e põem os headers de segurança em toda resposta.
app.add_middleware(BaseHTTPMiddleware, dispatch=bloquear_outras_origens)
app.add_middleware(BaseHTTPMiddleware, dispatch=headers_de_seguranca)

app.mount("/static", StaticFiles(directory=PASTA_FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def pagina_inicial():
    return FileResponse(PASTA_FRONTEND / "laboratorio" / "index.html")


@app.get("/login", include_in_schema=False)
def pagina_login(request: Request):
    if usuario_da_sessao(request) and "reset" not in request.query_params:
        return RedirectResponse("/", status_code=303)
    return FileResponse(PASTA_FRONTEND / "login" / "login.html")


@app.get("/api/auth/status")
def status_autenticacao():
    return {
        "recaptcha_site_key": chave_site_recaptcha(),
        "privacy_policy_version": VERSAO_POLITICA,
    }


@app.get("/api/auth/me")
def usuario_atual(request: Request):
    usuario = usuario_da_sessao(request)
    if not usuario:
        return {"authenticated": False, "user": None}
    linha = contas.buscar_por_email(usuario.get("email", ""))
    conta = {
        "session_expires_at": request.session.get("expira_em"),
        "created_at": linha["criado_em"] if linha else None,
        "privacy_accepted_at": linha["consentimento_em"] if linha else None,
        "privacy_version": linha["versao_politica"] if linha else None,
        "privacy_current_version": VERSAO_POLITICA,
    }
    return {"authenticated": True, "user": usuario, "account": conta}


class DadosLogin(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    remember: bool = False
    captcha: str | None = Field(None, max_length=4096)


class DadosCadastro(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)
    accept_privacy: bool = False
    captcha: str | None = Field(None, max_length=4096)


class DadosExclusao(BaseModel):
    password: str = Field(max_length=256)


def _exigir_captcha(request: Request, token: str | None) -> None:
    if not verificar_recaptcha(token, _ip(request)):
        raise HTTPException(400, "Confirme que você não é um robô.")


class DadosTrocaSenha(BaseModel):
    current_password: str
    password: str


class DadosRecuperacao(BaseModel):
    email: str = Field(max_length=254)
    captcha: str | None = Field(None, max_length=4096)


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
    _exigir_captcha(request, dados.captcha)
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
    chave = f"cadastro:{_ip(request)}"
    bloqueio = limite_cadastro.segundos_bloqueado(chave)
    if bloqueio:
        return JSONResponse({"detail": _mensagem_bloqueio(bloqueio)}, status_code=429, headers={"Retry-After": str(bloqueio)})
    if not dados.accept_privacy:
        raise HTTPException(400, "Para criar a conta, leia e aceite a Política de Privacidade.")
    _exigir_captcha(request, dados.captcha)
    limite_cadastro.registrar_falha(chave)
    try:
        usuario = contas.criar(dados.name, dados.email, dados.password, versao_politica=VERSAO_POLITICA)
    except ErroConta as erro:
        raise HTTPException(400, str(erro)) from erro
    iniciar_sessao(request, usuario)
    return {"authenticated": True, "user": usuario}


def _usuario_logado(request: Request) -> dict:
    """Usuário da sessão. Toda operação na conta usa este id, nunca um id enviado pelo navegador."""
    usuario = usuario_da_sessao(request)
    if not usuario:
        raise HTTPException(401, "Faça login para continuar.")
    return usuario


@app.get("/api/conta/dados")
def exportar_meus_dados(request: Request):
    """LGPD: o titular baixa todos os dados pessoais que o servidor guarda sobre ele."""
    usuario = _usuario_logado(request)
    dados = contas.exportar_dados(usuario["id"])
    if not dados:
        raise HTTPException(404, "Conta não encontrada.")
    return {
        "conta": dados,
        "observacao": "O histórico de imagens processadas fica somente neste navegador (localStorage e IndexedDB) e não é enviado ao servidor.",
        "exportado_em": time.time(),
    }


@app.post("/api/conta/excluir")
def excluir_minha_conta(request: Request, dados: DadosExclusao):
    """LGPD: exclusão da conta e dos dados ligados a ela, confirmada com a senha."""
    usuario = _usuario_logado(request)
    chave = f"excluir:{usuario['id']}"
    bloqueio = limite_exclusao.segundos_bloqueado(chave)
    if bloqueio:
        return JSONResponse({"detail": _mensagem_bloqueio(bloqueio)}, status_code=429, headers={"Retry-After": str(bloqueio)})
    if not contas.excluir(usuario["id"], dados.password):
        limite_exclusao.registrar_falha(chave)
        raise HTTPException(400, "Senha incorreta. A conta não foi excluída.")
    request.session.clear()
    return {"detail": "Sua conta e seus dados foram excluídos."}


@app.post("/api/conta/consentimento")
def aceitar_politica(request: Request):
    """Registra o aceite da política atual por contas criadas antes dela."""
    usuario = _usuario_logado(request)
    contas.registrar_consentimento(usuario["id"], VERSAO_POLITICA)
    return {"detail": "Consentimento registrado.", "version": VERSAO_POLITICA}


@app.get("/privacidade", include_in_schema=False)
def pagina_privacidade():
    # O contato do controlador vem do .env, para não deixar um e-mail fixo no código.
    contato = os.getenv("PRIVACIDADE_CONTATO") or os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "o responsável pelo projeto"
    html = (PASTA_FRONTEND / "privacidade" / "privacidade.html").read_text(encoding="utf-8")
    html = html.replace("{{CONTATO}}", escape(contato)).replace("{{VERSAO}}", VERSAO_POLITICA)
    return HTMLResponse(html)


@app.post("/api/auth/password")
def trocar_senha(request: Request, dados: DadosTrocaSenha):
    # /api/auth/ é público no middleware, então a sessão é conferida aqui.
    usuario = usuario_da_sessao(request)
    if not usuario:
        raise HTTPException(401, "Faça login para continuar.")
    chaves = (f"ip:{_ip(request)}", f"email:{normalizar_email(usuario['email'])}")
    bloqueio = limite_login.segundos_bloqueado(*chaves)
    if bloqueio:
        return JSONResponse({"detail": _mensagem_bloqueio(bloqueio), "retry_after": bloqueio}, status_code=429, headers={"Retry-After": str(bloqueio)})
    try:
        trocou = contas.alterar_senha(usuario["email"], dados.current_password, dados.password)
    except ErroConta as erro:
        raise HTTPException(400, str(erro)) from erro
    if not trocou:
        restantes = limite_login.registrar_falha(*chaves)
        if restantes == 0:
            bloqueio = limite_login.segundos_bloqueado(*chaves)
            return JSONResponse({"detail": _mensagem_bloqueio(bloqueio), "retry_after": bloqueio}, status_code=429, headers={"Retry-After": str(bloqueio)})
        return JSONResponse({"detail": "A senha atual está incorreta."}, status_code=400)
    limite_login.limpar(*chaves)
    return {"detail": "Senha alterada com sucesso."}


class AssistenteCompartilhado(BaseModel):
    livro: str = Field("", max_length=300)
    autor: str = Field("", max_length=300)
    resumo_estudo: str = Field("", max_length=4000)
    exercicios_revisao: list[str] = Field(default_factory=list, max_length=10)


class RegistroCompartilhado(BaseModel):
    nome: str = Field(max_length=300)
    dimensoes: str = Field("", max_length=60)
    tempo_ms: float | None = None
    data: str = Field("", max_length=60)
    status: str = Field("", max_length=60)
    assistente: AssistenteCompartilhado = Field(default_factory=AssistenteCompartilhado)


class DadosCompartilhamento(BaseModel):
    destinatario: str = Field(max_length=254)
    mensagem: str = Field("", max_length=1000)
    registro: RegistroCompartilhado
    imagem: str | None = Field(None, description="Miniatura do histórico como data URL JPEG")


def _relatorio_historico(registro: RegistroCompartilhado) -> str:
    assistente = registro.assistente
    tempo = f"{registro.tempo_ms / 1000:.2f} s" if registro.tempo_ms is not None else "não informado"
    linhas = [
        f"Imagem: {registro.nome}",
        f"Dimensões: {registro.dimensoes or 'não informadas'}",
        f"Tempo de processamento: {tempo}",
        f"Processado em: {registro.data or 'não informado'}",
        f"Status: {registro.status or 'não informado'}",
        f"Livro sugerido: {assistente.livro or 'não identificado'}",
        f"Autor: {assistente.autor or 'não identificado'}",
        f"Resumo: {assistente.resumo_estudo or 'não disponível'}",
    ]
    if assistente.exercicios_revisao:
        linhas += ["", "Exercícios de revisão:"]
        linhas += [f"{n}. {exercicio[:500]}" for n, exercicio in enumerate(assistente.exercicios_revisao, 1)]
    return "\n".join(linhas)


def _decodificar_miniatura(data_url: str | None) -> bytes | None:
    if not data_url:
        return None
    prefixo = "data:image/jpeg;base64,"
    if not data_url.startswith(prefixo):
        raise HTTPException(400, "A imagem do histórico está em um formato inesperado.")
    try:
        conteudo = base64.b64decode(data_url[len(prefixo):], validate=True)
    except (binascii.Error, ValueError) as erro:
        raise HTTPException(400, "Não foi possível ler a imagem do histórico.") from erro
    if len(conteudo) > TAMANHO_MAXIMO_IMAGEM_EMAIL:
        raise HTTPException(413, "A imagem do histórico é grande demais para enviar por e-mail.")
    return conteudo


@app.post("/api/historico/enviar")
def compartilhar_historico(request: Request, dados: DadosCompartilhamento):
    usuario = usuario_da_sessao(request)
    if not usuario:
        raise HTTPException(401, "Faça login para continuar.")
    destinatario = normalizar_email(dados.destinatario)
    if not email_valido(destinatario):
        raise HTTPException(400, "Informe um e-mail de destino válido.")
    if not smtp_configurado():
        raise HTTPException(503, "O envio de e-mails não está configurado neste servidor.")
    chave = f"compartilhar:{usuario.get('email') or usuario.get('id')}"
    bloqueio = limite_compartilhamento.segundos_bloqueado(chave)
    if bloqueio:
        return JSONResponse({"detail": f"Limite de envios atingido. {_mensagem_bloqueio(bloqueio)}"}, status_code=429, headers={"Retry-After": str(bloqueio)})

    miniatura = _decodificar_miniatura(dados.imagem)
    remetente = usuario.get("name") or usuario.get("email") or "Um usuário"
    relatorio = _relatorio_historico(dados.registro)
    corpo = [f"{remetente} compartilhou com você um resultado do NeXo Estudos.", ""]
    if dados.mensagem.strip():
        corpo += ["Mensagem:", dados.mensagem.strip(), ""]
    corpo += ["---", relatorio, "---", "", "Para responder, basta responder a este e-mail."]
    nome_base = "".join(c if c.isalnum() or c in "-_" else "-" for c in dados.registro.nome.rsplit(".", 1)[0])[:60] or "imagem"
    anexos = [(f"{nome_base}-relatorio.txt", relatorio.encode("utf-8"), "text/plain")]
    if miniatura:
        anexos.append((f"{nome_base}.jpg", miniatura, "image/jpeg"))
    try:
        enviar_email(
            destinatario,
            f"{remetente} compartilhou um resultado do NeXo Estudos: {dados.registro.nome[:80]}",
            "\n".join(corpo),
            anexos,
            responder_para=usuario.get("email"),
        )
    except OSError:
        logger.exception("Falha ao enviar o histórico por e-mail")
        raise HTTPException(502, "Não foi possível enviar o e-mail agora. Tente novamente mais tarde.")
    limite_compartilhamento.registrar_falha(chave)
    return {"detail": f"Enviado para {destinatario}."}


@app.post("/api/auth/forgot")
def esqueci_senha(request: Request, dados: DadosRecuperacao):
    chave = f"ip:{_ip(request)}"
    bloqueio = limite_recuperacao.segundos_bloqueado(chave)
    if bloqueio:
        return JSONResponse({"detail": _mensagem_bloqueio(bloqueio)}, status_code=429, headers={"Retry-After": str(bloqueio)})
    _exigir_captcha(request, dados.captcha)
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


@app.get("/auth/logout")
def sair(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


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
async def processar_arquivo(request: Request, arquivos: list[UploadFile] = File(...)):
    # O OCR é pesado: limitar por usuário evita que uma conta derrube o servidor com envios em massa.
    usuario = usuario_da_sessao(request) or {}
    chave = f"processar:{usuario.get('id') or _ip(request)}"
    bloqueio = limite_processamento.segundos_bloqueado(chave)
    if bloqueio:
        return JSONResponse({"detail": f"Você atingiu o limite de processamentos. {_mensagem_bloqueio(bloqueio)}"}, status_code=429, headers={"Retry-After": str(bloqueio)})
    limite_processamento.registrar_falha(chave)
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
