"""Testes das proteções do site: SQL injection, isolamento entre contas (equivalente ao RLS),
LGPD, rate limit, reCAPTCHA, hash de senha, headers e checagem de origem."""
import hashlib
import os
import secrets
import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend import main
from backend.contas import LimiteTentativas, RepositorioContas

ADMIN = ("admin@exemplo.com", "senha-segura-123")
ANA = ("ana@exemplo.com", "girassol-azul-7")
BRUNO = ("bruno@exemplo.com", "jabuticaba-roxa-9")


class BaseSeguranca(unittest.TestCase):
    def setUp(self):
        # O .env pode ter chaves reais do reCAPTCHA; os testes rodam com ele desligado.
        sem_captcha = mock.patch.dict(os.environ, {"RECAPTCHA_SITE_KEY": "", "RECAPTCHA_SECRET_KEY": ""})
        sem_captcha.start()
        self.addCleanup(sem_captcha.stop)
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.caminho_db = Path(self.pasta.name) / "contas.db"
        self.repositorio = RepositorioContas(self.caminho_db)
        self.repositorio.definir_admin(*ADMIN)
        for nome, valor in {
            "contas": self.repositorio,
            "limite_login": LimiteTentativas(maximo=5, bloqueio_segundos=900),
            "limite_recuperacao": LimiteTentativas(maximo=5, bloqueio_segundos=900),
            "limite_cadastro": LimiteTentativas(maximo=5, bloqueio_segundos=3600),
            "limite_processamento": LimiteTentativas(maximo=30, bloqueio_segundos=600),
            "limite_exclusao": LimiteTentativas(maximo=5, bloqueio_segundos=900),
        }.items():
            patcher = mock.patch.object(main, nome, valor)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cliente = TestClient(main.app)

    def cadastrar(self, nome, email, senha, cliente=None, **extra):
        dados = {"name": nome, "email": email, "password": senha, "accept_privacy": True, **extra}
        return (cliente or self.cliente).post("/api/auth/signup", json=dados)

    def entrar(self, email, senha, cliente=None):
        return (cliente or self.cliente).post("/api/auth/login", json={"email": email, "password": senha})


class TestSqlInjection(BaseSeguranca):
    PAYLOADS = ["' OR '1'='1", "admin@exemplo.com' --", "\" OR 1=1 --", "'; DROP TABLE usuarios; --", "x' UNION SELECT * FROM usuarios --"]

    def test_login_nao_e_contornado(self):
        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                self.assertNotEqual(self.entrar(payload, payload).status_code, 200)
                self.assertNotEqual(self.entrar(ADMIN[0], payload).status_code, 200)

    def test_payload_vira_dado_e_tabela_continua_intacta(self):
        nome = "Robert'); DROP TABLE usuarios; --"
        self.assertEqual(self.cadastrar(nome, "bobby@exemplo.com", "mesa-de-cedro-3").status_code, 201)
        with closing(sqlite3.connect(self.caminho_db)) as banco, banco:
            nomes = [linha[0] for linha in banco.execute("SELECT nome FROM usuarios")]
        self.assertIn(nome, nomes)
        self.assertEqual(len(nomes), 2)


class TestIsolamentoEntreContas(BaseSeguranca):
    """Equivalente ao Row Level Security: cada usuário só enxerga e altera a própria linha."""

    def setUp(self):
        super().setUp()
        self.ana, self.bruno = TestClient(main.app), TestClient(main.app)
        self.assertEqual(self.cadastrar("Ana", *ANA, cliente=self.ana).status_code, 201)
        self.assertEqual(self.cadastrar("Bruno", *BRUNO, cliente=self.bruno).status_code, 201)

    def test_exportacao_traz_so_os_proprios_dados(self):
        dados = self.ana.get("/api/conta/dados").json()["conta"]
        self.assertEqual(dados["email"], ANA[0])
        self.assertNotIn("senha_hash", dados)
        self.assertNotIn(BRUNO[0], str(dados))

    def test_id_enviado_pelo_navegador_e_ignorado(self):
        id_bruno = self.bruno.get("/api/auth/me").json()["user"]["id"]
        resposta = self.ana.get(f"/api/conta/dados?id={id_bruno}&usuario_id={id_bruno}")
        self.assertEqual(resposta.json()["conta"]["email"], ANA[0])
        # A senha da Ana não exclui a conta do Bruno, mesmo indicando o id dele.
        self.ana.post("/api/conta/excluir", json={"password": ANA[1], "id": id_bruno})
        self.assertEqual(self.entrar(*BRUNO).status_code, 200)

    def test_sem_login_nada_e_acessivel(self):
        anonimo = TestClient(main.app)
        self.assertEqual(anonimo.get("/api/conta/dados").status_code, 401)
        self.assertEqual(anonimo.post("/api/conta/excluir", json={"password": "x"}).status_code, 401)
        self.assertEqual(anonimo.post("/api/auth/password", json={"current_password": "x", "password": "y"}).status_code, 401)


class TestLgpd(BaseSeguranca):
    def test_cadastro_exige_aceitar_politica(self):
        resposta = self.cadastrar("Ana", *ANA, accept_privacy=False)
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("Política de Privacidade", resposta.json()["detail"])

    def test_consentimento_fica_registrado(self):
        self.cadastrar("Ana", *ANA)
        dados = self.cliente.get("/api/conta/dados").json()["conta"]
        self.assertIsNotNone(dados["consentimento_em"])
        self.assertEqual(dados["versao_politica"], main.VERSAO_POLITICA)

    def test_excluir_conta(self):
        self.cadastrar("Ana", *ANA)
        self.assertEqual(self.cliente.post("/api/conta/excluir", json={"password": "errada-123"}).status_code, 400)
        self.assertEqual(self.cliente.post("/api/conta/excluir", json={"password": ANA[1]}).status_code, 200)
        self.assertFalse(self.cliente.get("/api/auth/me").json()["authenticated"])
        self.assertEqual(self.entrar(*ANA).status_code, 401)
        self.assertIsNone(self.repositorio.buscar_por_email(ANA[0]))

    def test_politica_e_publica(self):
        resposta = TestClient(main.app).get("/privacidade")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Política de Privacidade", resposta.text)


class TestSenhas(BaseSeguranca):
    def test_senhas_fracas_sao_recusadas(self):
        for senha in ("12345678", "password", "ana@exemplo.com", "aaaaaaaa", "x" * 129):
            with self.subTest(senha=senha):
                self.assertEqual(self.cadastrar("Ana", ANA[0], senha).status_code, 400)

    def test_hash_e_scrypt_com_sal_e_nao_guarda_a_senha(self):
        self.cadastrar("Ana", *ANA)
        hash_salvo = self.repositorio.buscar_por_email(ANA[0])["senha_hash"]
        algoritmo, n, r, p, sal, _ = hash_salvo.split("$")
        self.assertEqual((algoritmo, n, r, p), ("scrypt", "32768", "8", "3"))
        self.assertEqual(len(bytes.fromhex(sal)), 16)
        self.assertNotIn(ANA[1], hash_salvo)

    def test_hash_antigo_e_atualizado_no_login(self):
        sal = secrets.token_bytes(16)
        antigo = hashlib.scrypt(ADMIN[1].encode(), salt=sal, n=2**14, r=8, p=1)
        with closing(sqlite3.connect(self.caminho_db)) as banco, banco:
            banco.execute("UPDATE usuarios SET senha_hash = ? WHERE email = ?",
                          (f"scrypt${2**14}$8$1${sal.hex()}${antigo.hex()}", ADMIN[0]))
        self.assertEqual(self.entrar(*ADMIN).status_code, 200)
        self.assertTrue(self.repositorio.buscar_por_email(ADMIN[0])["senha_hash"].startswith("scrypt$32768$8$3$"))


class TestRateLimit(BaseSeguranca):
    def test_cadastro_limitado_por_ip(self):
        for n in range(5):
            self.assertEqual(self.cadastrar(f"P{n}", f"p{n}@exemplo.com", "laranja-doce-42").status_code, 201)
        self.assertEqual(self.cadastrar("P6", "p6@exemplo.com", "laranja-doce-42").status_code, 429)

    def test_processamento_limitado(self):
        self.entrar(*ADMIN)
        with mock.patch.object(main, "limite_processamento", LimiteTentativas(maximo=2, bloqueio_segundos=600)):
            arquivo = {"arquivos": ("vazio.png", b"", "image/png")}
            for _ in range(2):
                self.assertNotEqual(self.cliente.post("/api/processar", files=arquivo).status_code, 429)
            self.assertEqual(self.cliente.post("/api/processar", files=arquivo).status_code, 429)


class TestRecaptcha(BaseSeguranca):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"RECAPTCHA_SITE_KEY": "site", "RECAPTCHA_SECRET_KEY": "segredo"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def resposta_google(self, sucesso):
        return mock.patch("backend.seguranca.httpx.post", return_value=mock.Mock(json=lambda: {"success": sucesso}))

    def test_status_publica_a_chave_do_site(self):
        self.assertEqual(self.cliente.get("/api/auth/status").json()["recaptcha_site_key"], "site")

    def test_sem_token_ou_token_invalido_e_recusado(self):
        self.assertEqual(self.entrar(*ADMIN).status_code, 400)
        with self.resposta_google(False):
            resposta = self.cliente.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1], "captcha": "falso"})
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("robô", resposta.json()["detail"])

    def test_token_valido_passa(self):
        with self.resposta_google(True):
            resposta = self.cliente.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1], "captcha": "ok"})
            cadastro = self.cadastrar("Ana", *ANA, captcha="ok")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(cadastro.status_code, 201)


class TestHeadersEOrigem(BaseSeguranca):
    def test_headers_de_seguranca(self):
        resposta = self.cliente.get("/login")
        self.assertIn("script-src 'self'", resposta.headers["content-security-policy"])
        self.assertIn("frame-ancestors 'none'", resposta.headers["content-security-policy"])
        self.assertEqual(resposta.headers["x-frame-options"], "DENY")
        self.assertEqual(resposta.headers["x-content-type-options"], "nosniff")
        self.assertEqual(self.cliente.get("/api/health").headers["cache-control"], "no-store")

    def test_pedido_de_outro_site_e_bloqueado(self):
        dados = {"email": ADMIN[0], "password": ADMIN[1]}
        de_fora = self.cliente.post("/api/auth/login", json=dados, headers={"Origin": "https://site-malicioso.com"})
        self.assertEqual(de_fora.status_code, 403)
        do_proprio_site = self.cliente.post("/api/auth/login", json=dados, headers={"Origin": "http://testserver"})
        self.assertEqual(do_proprio_site.status_code, 200)


if __name__ == "__main__":
    unittest.main()
