"""Contas com login por e-mail e senha, recuperação de senha e limite de tentativas.

As contas ficam em um banco SQLite local (contas.db). Senhas e tokens de
recuperação nunca são guardados em texto: apenas o hash.

Para criar ou trocar a senha do administrador, execute na raiz do projeto:

    python -m backend.contas
"""
from contextlib import contextmanager
from email.message import EmailMessage
from getpass import getpass
from pathlib import Path
import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time

RAIZ = Path(__file__).resolve().parent.parent
TAMANHO_MINIMO_SENHA = 8
VALIDADE_TOKEN_SEGUNDOS = 30 * 60
_N, _R, _P = 2**14, 8, 1
_EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
logger = logging.getLogger(__name__)


class ErroConta(ValueError):
    """Erro de validação com mensagem que pode ser mostrada ao usuário."""


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def gerar_hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${derivada.hex()}"


def verificar_senha(senha: str, hash_salvo: str) -> bool:
    try:
        algoritmo, n, r, p, sal, esperado = hash_salvo.split("$")
        if algoritmo != "scrypt":
            return False
        derivada = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derivada.hex(), esperado)


# Hash de referência para gastar o mesmo tempo quando o e-mail não existe.
_HASH_FALSO = gerar_hash_senha(secrets.token_urlsafe(16))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validar_senha_nova(senha: str) -> None:
    if len(senha) < TAMANHO_MINIMO_SENHA:
        raise ErroConta(f"A senha precisa ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres.")


class RepositorioContas:
    def __init__(self, caminho: Path | str):
        self.caminho = Path(caminho)
        with self._conectar() as banco:
            banco.executescript("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    nome TEXT NOT NULL,
                    senha_hash TEXT NOT NULL,
                    papel TEXT NOT NULL DEFAULT 'usuario',
                    criado_em REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tokens_senha (
                    token_hash TEXT PRIMARY KEY,
                    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    expira_em REAL NOT NULL
                );
            """)

    @contextmanager
    def _conectar(self):
        # "with sqlite3.connect()" só confirma a transação; a conexão precisa ser fechada à parte.
        banco = sqlite3.connect(self.caminho)
        banco.row_factory = sqlite3.Row
        banco.execute("PRAGMA foreign_keys = ON")
        try:
            with banco:
                yield banco
        finally:
            banco.close()

    @staticmethod
    def _publico(linha: sqlite3.Row) -> dict:
        return {"provider": "senha", "id": str(linha["id"]), "name": linha["nome"], "email": linha["email"], "role": linha["papel"], "avatar": None}

    def buscar_por_email(self, email: str) -> sqlite3.Row | None:
        with self._conectar() as banco:
            return banco.execute("SELECT * FROM usuarios WHERE email = ?", (normalizar_email(email),)).fetchone()

    def criar(self, nome: str, email: str, senha: str, papel: str = "usuario") -> dict:
        nome, email = (nome or "").strip(), normalizar_email(email)
        if not nome:
            raise ErroConta("Informe seu nome.")
        if not _EMAIL_VALIDO.match(email):
            raise ErroConta("Informe um e-mail válido.")
        validar_senha_nova(senha)
        try:
            with self._conectar() as banco:
                cursor = banco.execute(
                    "INSERT INTO usuarios (email, nome, senha_hash, papel, criado_em) VALUES (?, ?, ?, ?, ?)",
                    (email, nome[:80], gerar_hash_senha(senha), papel, time.time()),
                )
                linha = banco.execute("SELECT * FROM usuarios WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError as erro:
            raise ErroConta("Já existe uma conta com este e-mail.") from erro
        return self._publico(linha)

    def definir_admin(self, email: str, senha: str, senha_hash: str | None = None) -> None:
        """Cria o admin ou atualiza a senha e o papel de uma conta existente."""
        email = normalizar_email(email)
        if senha_hash is None:
            validar_senha_nova(senha)
            senha_hash = gerar_hash_senha(senha)
        with self._conectar() as banco:
            banco.execute(
                """INSERT INTO usuarios (email, nome, senha_hash, papel, criado_em) VALUES (?, 'Administrador', ?, 'admin', ?)
                   ON CONFLICT(email) DO UPDATE SET senha_hash = excluded.senha_hash, papel = 'admin'""",
                (email, senha_hash, time.time()),
            )

    def autenticar(self, email: str, senha: str) -> dict | None:
        linha = self.buscar_por_email(email)
        # Verifica um hash mesmo sem conta, para não revelar pelo tempo de resposta se o e-mail existe.
        senha_ok = verificar_senha(senha, linha["senha_hash"] if linha else _HASH_FALSO)
        return self._publico(linha) if linha and senha_ok else None

    def criar_token_recuperacao(self, email: str) -> str | None:
        linha = self.buscar_por_email(email)
        if not linha:
            return None
        token = secrets.token_urlsafe(32)
        with self._conectar() as banco:
            banco.execute("DELETE FROM tokens_senha WHERE usuario_id = ? OR expira_em < ?", (linha["id"], time.time()))
            banco.execute("INSERT INTO tokens_senha VALUES (?, ?, ?)", (_hash_token(token), linha["id"], time.time() + VALIDADE_TOKEN_SEGUNDOS))
        return token

    def redefinir_senha(self, token: str, senha: str) -> dict:
        validar_senha_nova(senha)
        with self._conectar() as banco:
            registro = banco.execute("SELECT * FROM tokens_senha WHERE token_hash = ?", (_hash_token(token or ""),)).fetchone()
            if not registro or registro["expira_em"] < time.time():
                raise ErroConta("O link de recuperação é inválido ou expirou. Peça um novo.")
            banco.execute("UPDATE usuarios SET senha_hash = ? WHERE id = ?", (gerar_hash_senha(senha), registro["usuario_id"]))
            banco.execute("DELETE FROM tokens_senha WHERE usuario_id = ?", (registro["usuario_id"],))
            linha = banco.execute("SELECT * FROM usuarios WHERE id = ?", (registro["usuario_id"],)).fetchone()
        return self._publico(linha)


class LimiteTentativas:
    """Bloqueia uma chave (IP ou e-mail) após muitas falhas seguidas de login."""

    def __init__(self, maximo: int = 5, bloqueio_segundos: int = 15 * 60):
        self.maximo = maximo
        self.bloqueio_segundos = bloqueio_segundos
        self._falhas: dict[str, tuple[int, float]] = {}
        self._trava = threading.Lock()

    def _estado(self, chave: str) -> tuple[int, float]:
        falhas, inicio = self._falhas.get(chave, (0, 0.0))
        if falhas and time.time() - inicio > self.bloqueio_segundos:
            self._falhas.pop(chave, None)
            return 0, 0.0
        return falhas, inicio

    def segundos_bloqueado(self, *chaves: str) -> int:
        with self._trava:
            restante = 0
            for chave in chaves:
                falhas, inicio = self._estado(chave)
                if falhas >= self.maximo:
                    restante = max(restante, int(inicio + self.bloqueio_segundos - time.time()) + 1)
            return restante

    def registrar_falha(self, *chaves: str) -> int:
        """Registra a falha e devolve quantas tentativas ainda restam."""
        with self._trava:
            maior = 0
            for chave in chaves:
                falhas, inicio = self._estado(chave)
                falhas += 1
                self._falhas[chave] = (falhas, inicio or time.time())
                maior = max(maior, falhas)
            return max(0, self.maximo - maior)

    def limpar(self, *chaves: str) -> None:
        with self._trava:
            for chave in chaves:
                self._falhas.pop(chave, None)


def enviar_link_recuperacao(email: str, link: str) -> None:
    """Envia o link por SMTP; sem SMTP configurado, mostra o link no terminal do servidor."""
    host = os.getenv("SMTP_HOST")
    if not host:
        logger.warning("SMTP não configurado. Link de recuperação de senha para %s: %s", email, link)
        return
    mensagem = EmailMessage()
    mensagem["Subject"] = "Redefinição de senha - Nexo Estudos"
    mensagem["From"] = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "nao-responda@localhost"
    mensagem["To"] = email
    mensagem.set_content(
        "Recebemos um pedido para redefinir a senha da sua conta.\n\n"
        f"Abra o link abaixo em até 30 minutos para criar uma nova senha:\n{link}\n\n"
        "Se você não fez esse pedido, ignore este e-mail."
    )
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as servidor:
        servidor.starttls()
        if os.getenv("SMTP_USER"):
            servidor.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        servidor.send_message(mensagem)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
    repositorio = RepositorioContas(os.getenv("CONTAS_DB") or RAIZ / "contas.db")
    email = input("E-mail do administrador: ").strip()
    senha = getpass(f"Nova senha (mínimo {TAMANHO_MINIMO_SENHA} caracteres): ")
    if senha != getpass("Repita a senha: "):
        raise SystemExit("As senhas não conferem.")
    try:
        repositorio.definir_admin(email, senha)
    except ErroConta as erro:
        raise SystemExit(str(erro))
    print("Conta de administrador salva.")
