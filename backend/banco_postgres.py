"""Contas e histórico no Postgres do Supabase, com miniaturas no Supabase Storage.

O backend se conecta como o papel nexo_app, que está sujeito ao Row Level Security.
Operações de uma conta logada rodam dentro de `_como(usuario_id)`, que informa ao
banco quem é o usuário (app.usuario_id); as políticas do banco recusam qualquer linha
de outra conta, mesmo que o código aqui esqueça um filtro. Antes do login, o acesso
passa pelas funções SECURITY DEFINER da migração (conta_por_email, criar_conta...).
"""
from __future__ import annotations

import atexit
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .contas import (
    _HASH_FALSO, VALIDADE_TOKEN_SEGUNDOS, ErroConta, _hash_token, email_valido, gerar_hash_senha,
    hash_desatualizado, normalizar_email, validar_senha_nova, verificar_senha,
)
from .historico import MAXIMO_REGISTROS, caminho_miniatura


def _epoca(valor):
    return valor.timestamp() if isinstance(valor, datetime) else valor


def _linha_usuario(linha: dict | None) -> dict | None:
    """Mesmo formato do repositório SQLite: datas como segundos desde 1970."""
    if not linha:
        return None
    return {**linha, "criado_em": _epoca(linha["criado_em"]), "consentimento_em": _epoca(linha.get("consentimento_em"))}


def _publico(linha: dict) -> dict:
    return {"provider": "senha", "id": str(linha["id"]), "name": linha["nome"], "email": linha["email"], "role": linha["papel"]}


class BancoPostgres:
    def __init__(self, url: str):
        self.pool = ConnectionPool(
            url, min_size=1, max_size=5, open=True, name="nexo",
            kwargs={"row_factory": dict_row, "connect_timeout": 15, "autocommit": True},
        )
        # Fecha as conexões antes de o Python encerrar (evita aviso de threads do pool na saída).
        atexit.register(self.pool.close)

    @contextmanager
    def transacao(self):
        with self.pool.connection() as conexao, conexao.transaction():
            yield conexao

    @contextmanager
    def como(self, usuario_id: int | str):
        """Transação em nome de uma conta: o RLS só libera as linhas dela."""
        with self.transacao() as conexao:
            conexao.execute("select set_config('app.usuario_id', %s, true)", (str(int(usuario_id)),))
            yield conexao


class RepositorioContasPostgres:
    def __init__(self, banco: BancoPostgres, url_admin: str | None = None):
        self.banco = banco
        self.url_admin = url_admin

    def buscar_por_email(self, email: str) -> dict | None:
        with self.banco.transacao() as c:
            return _linha_usuario(c.execute("select * from nexo.conta_por_email(%s)", (normalizar_email(email),)).fetchone())

    def criar(self, nome: str, email: str, senha: str, papel: str = "usuario", versao_politica: str | None = None) -> dict:
        nome, email = (nome or "").strip(), normalizar_email(email)
        if not nome:
            raise ErroConta("Informe seu nome.")
        if not email_valido(email):
            raise ErroConta("Informe um e-mail válido.")
        validar_senha_nova(senha, email)
        try:
            with self.banco.transacao() as c:
                linha = c.execute("select * from nexo.criar_conta(%s, %s, %s, %s)",
                                  (email, nome[:80], gerar_hash_senha(senha), versao_politica)).fetchone()
        except psycopg.errors.UniqueViolation as erro:
            raise ErroConta("Já existe uma conta com este e-mail.") from erro
        return _publico(linha)

    def definir_admin(self, email: str, senha: str, senha_hash: str | None = None) -> None:
        """Cria ou promove o administrador. Exige a conexão de administrador (SUPABASE_DB_URL),
        porque o papel nexo_app não pode alterar o papel de uma conta."""
        if not self.url_admin:
            raise ErroConta("Defina SUPABASE_DB_URL no .env para criar o administrador.")
        email = normalizar_email(email)
        if senha_hash is None:
            validar_senha_nova(senha, email)
            senha_hash = gerar_hash_senha(senha)
        with psycopg.connect(self.url_admin, connect_timeout=15) as c, c.transaction():
            c.execute(
                """insert into nexo.usuarios (email, nome, senha_hash, papel) values (%s, 'Administrador', %s, 'admin')
                   on conflict (email) do update set senha_hash = excluded.senha_hash, papel = 'admin'""",
                (email, senha_hash),
            )

    def autenticar(self, email: str, senha: str) -> dict | None:
        linha = self.buscar_por_email(email)
        # Verifica um hash mesmo sem conta, para não revelar pelo tempo de resposta se o e-mail existe.
        senha_ok = verificar_senha(senha, linha["senha_hash"] if linha else _HASH_FALSO)
        if not (linha and senha_ok):
            return None
        if hash_desatualizado(linha["senha_hash"]):
            with self.banco.transacao() as c:
                c.execute("select nexo.atualizar_hash(%s, %s)", (linha["id"], gerar_hash_senha(senha)))
        return _publico(linha)

    def alterar_senha(self, email: str, senha_atual: str, senha_nova: str) -> bool:
        validar_senha_nova(senha_nova, email)
        usuario = self.autenticar(email, senha_atual)
        if not usuario:
            return False
        if senha_nova == senha_atual:
            raise ErroConta("A nova senha precisa ser diferente da atual.")
        with self.banco.como(usuario["id"]) as c:
            c.execute("select nexo.trocar_senha(%s)", (gerar_hash_senha(senha_nova),))
        return True

    def exportar_dados(self, usuario_id: int | str) -> dict | None:
        with self.banco.como(usuario_id) as c:
            linha = c.execute(
                "select id, email, nome, papel, criado_em, consentimento_em, versao_politica from nexo.usuarios"
            ).fetchone()
            if not linha:
                return None
            pendentes = c.execute("select nexo.tokens_pendentes() as n").fetchone()["n"]
        return {**_linha_usuario(linha), "links_recuperacao_pendentes": pendentes}

    def excluir(self, usuario_id: int | str, senha: str) -> bool:
        with self.banco.como(usuario_id) as c:
            linha = c.execute("select senha_hash from nexo.usuarios").fetchone()
            if not linha or not verificar_senha(senha, linha["senha_hash"]):
                return False
            c.execute("delete from nexo.usuarios where id = nexo.usuario_atual()")
        return True

    def registrar_consentimento(self, usuario_id: int | str, versao_politica: str) -> None:
        with self.banco.como(usuario_id) as c:
            c.execute("update nexo.usuarios set consentimento_em = now(), versao_politica = %s where id = nexo.usuario_atual()",
                      (versao_politica,))

    def criar_token_recuperacao(self, email: str) -> str | None:
        token = secrets.token_urlsafe(32)
        with self.banco.transacao() as c:
            criado = c.execute("select nexo.criar_token_senha(%s, %s, %s) as ok",
                               (normalizar_email(email), _hash_token(token), timedelta(seconds=VALIDADE_TOKEN_SEGUNDOS))).fetchone()["ok"]
        return token if criado else None

    def redefinir_senha(self, token: str, senha: str) -> dict:
        validar_senha_nova(senha)
        with self.banco.transacao() as c:
            linha = c.execute("select * from nexo.redefinir_senha(%s, %s)", (_hash_token(token or ""), gerar_hash_senha(senha))).fetchone()
        if not linha:
            raise ErroConta("O link de recuperação é inválido ou expirou. Peça um novo.")
        return _publico(linha)


class ArmazenamentoSupabase:
    """Miniaturas no bucket privado "miniaturas", acessado só pelo backend com a chave secreta."""

    def __init__(self, url_projeto: str, chave_secreta: str, bucket: str = "miniaturas"):
        self.base = f"{url_projeto.rstrip('/')}/storage/v1/object"
        self.bucket = bucket
        self.cabecalhos = {"apikey": chave_secreta, "Authorization": f"Bearer {chave_secreta}"}

    def enviar(self, caminho: str, conteudo: bytes) -> None:
        resposta = httpx.post(f"{self.base}/{self.bucket}/{caminho}", content=conteudo, timeout=30,
                              headers={**self.cabecalhos, "Content-Type": "image/jpeg", "x-upsert": "true"})
        resposta.raise_for_status()

    def baixar(self, caminho: str) -> bytes | None:
        resposta = httpx.get(f"{self.base}/{self.bucket}/{caminho}", headers=self.cabecalhos, timeout=30)
        if resposta.status_code in (400, 404):
            return None
        resposta.raise_for_status()
        return resposta.content

    def apagar(self, caminhos: list[str]) -> None:
        if caminhos:
            resposta = httpx.request("DELETE", f"{self.base}/{self.bucket}", json={"prefixes": caminhos},
                                     headers=self.cabecalhos, timeout=30)
            resposta.raise_for_status()


class RepositorioHistoricoPostgres:
    def __init__(self, banco: BancoPostgres, armazenamento: ArmazenamentoSupabase):
        self.banco = banco
        self.armazenamento = armazenamento

    @staticmethod
    def _publico(linha: dict) -> dict:
        dados = {k: linha[k] for k in ("nome_arquivo", "pagina", "largura", "altura", "ocr_disponivel", "palavras", "trecho", "assistente")}
        dados["tempo_ms"] = float(linha["tempo_ms"]) if linha["tempo_ms"] is not None else None
        dados["inclinacao_graus"] = float(linha["inclinacao_graus"]) if linha["inclinacao_graus"] is not None else None
        return {"id": str(linha["id"]), **dados, "criado_em": _epoca(linha["criado_em"]),
                "tem_miniatura": bool(linha["miniatura_caminho"])}

    def adicionar(self, usuario_id: int | str, registro: dict, miniatura: bytes | None) -> dict:
        with self.banco.como(usuario_id) as c:
            linha = c.execute(
                """insert into nexo.processamentos (usuario_id, nome_arquivo, pagina, largura, altura, tempo_ms,
                       ocr_disponivel, inclinacao_graus, palavras, trecho, assistente)
                   values (nexo.usuario_atual(), %(nome_arquivo)s, %(pagina)s, %(largura)s, %(altura)s, %(tempo_ms)s,
                       %(ocr_disponivel)s, %(inclinacao_graus)s, %(palavras)s, %(trecho)s, %(assistente)s)
                   returning *""",
                {**registro, "assistente": Jsonb(registro.get("assistente") or {})},
            ).fetchone()
            excedentes = c.execute(
                "delete from nexo.processamentos where id in (select id from nexo.processamentos order by criado_em desc offset %s)"
                " returning miniatura_caminho", (MAXIMO_REGISTROS,),
            ).fetchall()
        if miniatura:
            caminho = caminho_miniatura(usuario_id, str(linha["id"]))
            self.armazenamento.enviar(caminho, miniatura)
            with self.banco.como(usuario_id) as c:
                linha = c.execute("update nexo.processamentos set miniatura_caminho = %s where id = %s returning *",
                                  (caminho, linha["id"])).fetchone()
        self.armazenamento.apagar([l["miniatura_caminho"] for l in excedentes if l["miniatura_caminho"]])
        return self._publico(linha)

    def listar(self, usuario_id: int | str, limite: int = MAXIMO_REGISTROS) -> list[dict]:
        with self.banco.como(usuario_id) as c:
            linhas = c.execute("select * from nexo.processamentos order by criado_em desc limit %s", (limite,)).fetchall()
        return [self._publico(l) for l in linhas]

    def obter(self, usuario_id: int | str, registro_id: str) -> dict | None:
        with self.banco.como(usuario_id) as c:
            linha = c.execute("select * from nexo.processamentos where id = %s", (registro_id,)).fetchone()
        return self._publico(linha) if linha else None

    def miniatura(self, usuario_id: int | str, registro_id: str) -> bytes | None:
        with self.banco.como(usuario_id) as c:
            linha = c.execute("select miniatura_caminho from nexo.processamentos where id = %s", (registro_id,)).fetchone()
        return self.armazenamento.baixar(linha["miniatura_caminho"]) if linha and linha["miniatura_caminho"] else None

    def apagar_tudo(self, usuario_id: int | str) -> int:
        with self.banco.como(usuario_id) as c:
            apagados = c.execute("delete from nexo.processamentos returning miniatura_caminho").fetchall()
        self.armazenamento.apagar([l["miniatura_caminho"] for l in apagados if l["miniatura_caminho"]])
        return len(apagados)
