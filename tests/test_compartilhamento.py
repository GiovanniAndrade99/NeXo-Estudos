import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend import main
from backend.contas import LimiteTentativas, RepositorioContas

EMAIL = "admin@exemplo.com"
SENHA = "senha-segura-123"
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0imagem-falsa").decode()
REGISTRO = {
    "nome": "apostila.png",
    "dimensoes": "800 x 600",
    "tempo_ms": 1234,
    "data": "01/10/2026 10:00",
    "status": "OCR OK",
    "assistente": {"livro": "Cálculo", "autor": "Stewart", "resumo_estudo": "Limites", "exercicios_revisao": ["Defina limite."]},
}


class TestCompartilharHistorico(unittest.TestCase):
    def setUp(self):
        # O .env pode ter chaves reais do reCAPTCHA; os testes rodam com ele desligado.
        sem_captcha = mock.patch.dict(os.environ, {"RECAPTCHA_SITE_KEY": "", "RECAPTCHA_SECRET_KEY": ""})
        sem_captcha.start()
        self.addCleanup(sem_captcha.stop)
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        repositorio = RepositorioContas(Path(self.pasta.name) / "contas.db")
        repositorio.definir_admin(EMAIL, SENHA)
        self.enviar = mock.MagicMock()
        for nome, valor in {
            "contas": repositorio,
            "limite_login": LimiteTentativas(maximo=5, bloqueio_segundos=900),
            "limite_compartilhamento": LimiteTentativas(maximo=3, bloqueio_segundos=3600),
            "enviar_email": self.enviar,
            "smtp_configurado": lambda: True,
        }.items():
            patcher = mock.patch.object(main, nome, valor)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cliente = TestClient(main.app)

    def entrar(self):
        self.cliente.post("/api/auth/login", json={"email": EMAIL, "password": SENHA})

    def compartilhar(self, **extra):
        dados = {"destinatario": "colega@exemplo.com", "mensagem": "Olha isso", "registro": REGISTRO, "imagem": JPEG}
        dados.update(extra)
        return self.cliente.post("/api/historico/enviar", json=dados)

    def test_exige_login(self):
        self.assertEqual(self.compartilhar().status_code, 401)
        self.enviar.assert_not_called()

    def test_envia_relatorio_e_imagem(self):
        self.entrar()
        resposta = self.compartilhar()
        self.assertEqual(resposta.status_code, 200, resposta.text)
        destinatario, assunto, corpo, anexos = self.enviar.call_args.args
        self.assertEqual(destinatario, "colega@exemplo.com")
        self.assertIn("apostila.png", assunto)
        self.assertIn("Olha isso", corpo)
        self.assertIn("Livro sugerido: Cálculo", corpo)
        self.assertIn("1. Defina limite.", corpo)
        self.assertEqual([a[0] for a in anexos], ["apostila-relatorio.txt", "apostila.jpg"])
        self.assertEqual(anexos[1][1][:2], b"\xff\xd8")
        self.assertEqual(self.enviar.call_args.kwargs["responder_para"], EMAIL)

    def test_sem_imagem_envia_so_relatorio(self):
        self.entrar()
        self.assertEqual(self.compartilhar(imagem=None).status_code, 200)
        self.assertEqual(len(self.enviar.call_args.args[3]), 1)

    def test_valida_entrada(self):
        self.entrar()
        self.assertEqual(self.compartilhar(destinatario="sem-arroba").status_code, 400)
        self.assertEqual(self.compartilhar(imagem="data:text/html;base64,PGI+").status_code, 400)
        self.assertEqual(self.compartilhar(mensagem="x" * 1001).status_code, 422)
        self.enviar.assert_not_called()

    def test_limite_de_envios(self):
        self.entrar()
        for _ in range(3):
            self.assertEqual(self.compartilhar().status_code, 200)
        self.assertEqual(self.compartilhar().status_code, 429)
        self.assertEqual(self.enviar.call_count, 3)

    def test_sem_smtp_configurado(self):
        self.entrar()
        with mock.patch.object(main, "smtp_configurado", lambda: False):
            self.assertEqual(self.compartilhar().status_code, 503)
        self.enviar.assert_not_called()

    def test_falha_no_smtp_nao_conta_no_limite(self):
        self.entrar()
        self.enviar.side_effect = OSError("smtp fora")
        self.assertEqual(self.compartilhar().status_code, 502)
        self.enviar.side_effect = None
        for _ in range(3):
            self.assertEqual(self.compartilhar().status_code, 200)


if __name__ == "__main__":
    unittest.main()
