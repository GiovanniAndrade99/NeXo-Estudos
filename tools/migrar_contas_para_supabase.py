"""Copia as contas do contas.db (SQLite) para o Supabase, mantendo os hashes de senha.

Ninguém precisa redefinir a senha: o hash scrypt é copiado como está. Contas que já
existem no Supabase (mesmo e-mail) são mantidas sem alteração.

Uso (na raiz do projeto, com SUPABASE_DB_URL no .env):
    python tools/migrar_contas_para_supabase.py
"""
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]


def data(segundos):
    return datetime.fromtimestamp(segundos, tz=timezone.utc) if segundos else None


def main() -> None:
    url_admin = dotenv_values(RAIZ / ".env").get("SUPABASE_DB_URL")
    if not url_admin:
        sys.exit("Defina SUPABASE_DB_URL no .env.")
    caminho = RAIZ / "contas.db"
    if not caminho.exists():
        sys.exit("contas.db não encontrado: não há contas locais para migrar.")
    with closing(sqlite3.connect(caminho)) as local:
        local.row_factory = sqlite3.Row
        colunas = {linha["name"] for linha in local.execute("PRAGMA table_info(usuarios)")}
        contas = local.execute("SELECT * FROM usuarios ORDER BY id").fetchall()
    with psycopg.connect(url_admin, connect_timeout=20) as remoto, remoto.transaction():
        for conta in contas:
            consentimento = conta["consentimento_em"] if "consentimento_em" in colunas else None
            versao = conta["versao_politica"] if "versao_politica" in colunas else None
            criada = remoto.execute(
                """insert into nexo.usuarios (email, nome, senha_hash, papel, criado_em, consentimento_em, versao_politica)
                   values (%s, %s, %s, %s, %s, %s, %s)
                   on conflict (email) do nothing returning id""",
                (conta["email"], conta["nome"], conta["senha_hash"], conta["papel"], data(conta["criado_em"]),
                 data(consentimento) if versao else None, versao if consentimento else None),
            ).fetchone()
            print(f"{conta['email']} ({conta['papel']}): {'copiada' if criada else 'já existia, mantida'}")
    print(f"{len(contas)} conta(s) verificada(s).")


if __name__ == "__main__":
    main()
