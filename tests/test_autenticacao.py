import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend import main
from backend.contas import LimiteTentativas, RepositorioContas

EMAIL = "admin@exemplo.com"
SENHA = "senha-segura-123"


class TestAutenticacao(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        repositorio = RepositorioContas(Path(self.pasta.name) / "contas.db")
        repositorio.definir_admin(EMAIL, SENHA)
        for nome, valor in {
            "contas": repositorio,
            "limite_login": LimiteTentativas(maximo=5, bloqueio_segundos=900),
            "limite_recuperacao": LimiteTentativas(maximo=5, bloqueio_segundos=900),
        }.items():
            patcher = mock.patch.object(main, nome, valor)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.repositorio = repositorio
        self.cliente = TestClient(main.app)

    def entrar(self, email=EMAIL, senha=SENHA, lembrar=False):
        return self.cliente.post("/api/auth/login", json={"email": email, "password": senha, "remember": lembrar})

    def test_laboratorio_exige_login(self):
        resposta = self.cliente.get("/", follow_redirects=False)
        self.assertEqual(resposta.status_code, 303)
        self.assertEqual(resposta.headers["location"], "/login")
        self.assertEqual(self.cliente.get("/static/app.js", follow_redirects=False).status_code, 303)
        self.assertEqual(self.cliente.post("/api/processar").status_code, 401)
        self.assertEqual(self.cliente.get("/login").status_code, 200)
        self.assertEqual(self.cliente.get("/static/login.js").status_code, 200)

    def test_login_libera_laboratorio_e_logout_bloqueia(self):
        self.assertEqual(self.entrar(email="  ADMIN@exemplo.com ").status_code, 200)
        self.assertEqual(self.cliente.get("/", follow_redirects=False).status_code, 200)
        self.assertEqual(self.cliente.get("/login", follow_redirects=False).status_code, 303)
        self.cliente.get("/auth/logout")
        self.assertEqual(self.cliente.get("/", follow_redirects=False).status_code, 303)

    def test_bloqueia_apos_cinco_tentativas(self):
        for restantes in (4, 3, 2, 1):
            resposta = self.entrar(senha="errada")
            self.assertEqual(resposta.status_code, 401)
            self.assertEqual(resposta.json()["remaining"], restantes)
        self.assertEqual(self.entrar(senha="errada").status_code, 429)
        # Nem a senha correta entra durante o bloqueio.
        bloqueada = self.entrar()
        self.assertEqual(bloqueada.status_code, 429)
        self.assertGreater(bloqueada.json()["retry_after"], 0)

    def test_bloqueio_expira(self):
        for _ in range(5):
            self.entrar(senha="errada")
        with mock.patch("backend.contas.time.time", return_value=time.time() + 901):
            self.assertEqual(self.entrar().status_code, 200)

    def test_sucesso_zera_contagem(self):
        for _ in range(4):
            self.entrar(senha="errada")
        self.assertEqual(self.entrar().status_code, 200)
        self.assertEqual(self.entrar(senha="errada").json()["remaining"], 4)

    def test_criar_conta(self):
        dados = {"name": "Ana", "email": "ana@exemplo.com", "password": "12345678"}
        resposta = self.cliente.post("/api/auth/signup", json=dados)
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["user"]["role"], "usuario")
        self.assertEqual(self.cliente.get("/", follow_redirects=False).status_code, 200)
        self.assertEqual(self.cliente.post("/api/auth/signup", json=dados).status_code, 400)
        curta = {"name": "Bia", "email": "bia@exemplo.com", "password": "123"}
        self.assertEqual(self.cliente.post("/api/auth/signup", json=curta).status_code, 400)

    def test_recuperar_senha(self):
        with mock.patch.object(main, "enviar_link_recuperacao") as enviar:
            resposta = self.cliente.post("/api/auth/forgot", json={"email": EMAIL})
            inexistente = self.cliente.post("/api/auth/forgot", json={"email": "ninguem@exemplo.com"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), inexistente.json())
        enviar.assert_called_once()
        token = enviar.call_args.args[1].split("reset=")[1]

        self.assertEqual(self.cliente.post("/api/auth/reset", json={"token": token, "password": "nova-senha-456"}).status_code, 200)
        self.cliente.get("/auth/logout")
        self.assertEqual(self.entrar().status_code, 401)
        self.assertEqual(self.entrar(senha="nova-senha-456").status_code, 200)
        # O link só pode ser usado uma vez.
        self.assertEqual(self.cliente.post("/api/auth/reset", json={"token": token, "password": "outra-senha-789"}).status_code, 400)

    def trocar_senha(self, atual, nova):
        return self.cliente.post("/api/auth/password", json={"current_password": atual, "password": nova})

    def test_trocar_senha(self):
        self.assertEqual(self.trocar_senha(SENHA, "nova-senha-456").status_code, 401)
        self.entrar()
        errada = self.trocar_senha("errada", "nova-senha-456")
        self.assertEqual(errada.status_code, 400)
        self.assertIn("atual", errada.json()["detail"])
        self.assertEqual(self.trocar_senha(SENHA, "curta").status_code, 400)
        self.assertEqual(self.trocar_senha(SENHA, SENHA).status_code, 400)
        self.assertEqual(self.trocar_senha(SENHA, "nova-senha-456").status_code, 200)
        self.cliente.get("/auth/logout")
        self.assertEqual(self.entrar().status_code, 401)
        self.assertEqual(self.entrar(senha="nova-senha-456").status_code, 200)

    def test_trocar_senha_bloqueia_apos_tentativas(self):
        self.entrar()
        for _ in range(4):
            self.assertEqual(self.trocar_senha("errada", "nova-senha-456").status_code, 400)
        self.assertEqual(self.trocar_senha("errada", "nova-senha-456").status_code, 429)
        self.assertEqual(self.trocar_senha(SENHA, "nova-senha-456").status_code, 429)

    def test_me_traz_dados_da_conta(self):
        self.assertFalse(self.cliente.get("/api/auth/me").json()["authenticated"])
        self.entrar()
        dados = self.cliente.get("/api/auth/me").json()
        self.assertEqual(dados["user"]["role"], "admin")
        self.assertIsNotNone(dados["account"]["created_at"])
        self.assertGreater(dados["account"]["session_expires_at"], time.time())

    def test_sessao_curta_e_longa(self):
        self.entrar()
        agora = time.time()
        with mock.patch("backend.main.time.time", return_value=agora + 9 * 3600):
            self.assertEqual(self.cliente.get("/", follow_redirects=False).status_code, 303)
        self.entrar(lembrar=True)
        with mock.patch("backend.main.time.time", return_value=agora + 9 * 3600):
            self.assertEqual(self.cliente.get("/", follow_redirects=False).status_code, 200)


if __name__ == "__main__":
    unittest.main()
