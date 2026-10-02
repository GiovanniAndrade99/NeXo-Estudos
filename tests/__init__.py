"""Os testes rodam sempre isolados do ambiente real.

Valores vazios aqui vencem o .env (o load_dotenv não sobrescreve variáveis já definidas):
sem NEXO_DB_URL o backend usa SQLite e pasta local, e sem as chaves o reCAPTCHA fica desligado.
"""
import os

for variavel in ("NEXO_DB_URL", "RECAPTCHA_SITE_KEY", "RECAPTCHA_SECRET_KEY"):
    os.environ[variavel] = ""
