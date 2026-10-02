"""Histórico no servidor (listar, miniatura, apagar) e envio de um registro por e-mail."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from fastapi.testclient import TestClient

from backend import main
from backend.contas import LimiteTentativas, RepositorioContas
from backend.historico import ArmazenamentoLocal, RepositorioHistoricoSQLite, gerar_miniatura, montar_registro

EMAIL = "admin@exemplo.com"
SENHA = "senha-segura-123"
OUTRA = ("bruno@exemplo.com", "jabuticaba-roxa-9")
ASSISTENTE = {"livro": "Cálculo", "autor": "Stewart", "resumo_estudo": "Limites", "exercicios_revisao": ["Defina limite."]}


def registro_exemplo(nome="apostila.png"):
    return montar_registro(nome, None, 800, 600, 1234, True, -2.5, "Limite de uma funcao quando x tende a a", ASSISTENTE)


class TestHistoricoECompartilhamento(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        banco = Path(self.pasta.name) / "contas.db"
        self.contas = RepositorioContas(banco)
        self.contas.definir_admin(EMAIL, SENHA)
        self.historico = RepositorioHistoricoSQLite(banco, ArmazenamentoLocal(Path(self.pasta.name) / "miniaturas"))
        self.enviar = mock.MagicMock()
        for nome, valor in {
            "contas": self.contas,
            "historico": self.historico,
            "limite_login": LimiteTentativas(maximo=5, bloqueio_segundos=900),
            "limite_cadastro": LimiteTentativas(maximo=5, bloqueio_segundos=3600),
            "limite_compartilhamento": LimiteTentativas(maximo=3, bloqueio_segundos=3600),
            "enviar_email": self.enviar,
            "smtp_configurado": lambda: True,
        }.items():
            patcher = mock.patch.object(main, nome, valor)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cliente = TestClient(main.app)
        self.admin_id = self.contas.buscar_por_email(EMAIL)["id"]
        miniatura = gerar_miniatura(np.full((60, 80, 3), 200, np.uint8))
        self.registro = self.historico.adicionar(self.admin_id, registro_exemplo(), miniatura)

    def entrar(self, cliente=None, email=EMAIL, senha=SENHA):
        (cliente or self.cliente).post("/api/auth/login", json={"email": email, "password": senha})

    def compartilhar(self, **extra):
        dados = {"destinatario": "colega@exemplo.com", "mensagem": "Olha isso", "historico_id": self.registro["id"], **extra}
        return self.cliente.post("/api/historico/enviar", json=dados)

    # --- histórico ---

    def test_historico_exige_login(self):
        self.assertEqual(self.cliente.get("/api/historico").status_code, 401)
        self.assertEqual(self.cliente.get(f"/api/historico/{self.registro['id']}/miniatura").status_code, 401)

    def test_lista_e_baixa_miniatura(self):
        self.entrar()
        registros = self.cliente.get("/api/historico").json()["registros"]
        self.assertEqual([r["id"] for r in registros], [self.registro["id"]])
        self.assertEqual(registros[0]["palavras"], 9)
        self.assertTrue(registros[0]["tem_miniatura"])
        imagem = self.cliente.get(f"/api/historico/{self.registro['id']}/miniatura")
        self.assertEqual(imagem.headers["content-type"], "image/jpeg")
        self.assertIsNotNone(cv2.imdecode(np.frombuffer(imagem.content, np.uint8), cv2.IMREAD_COLOR))

    def test_outra_conta_nao_ve_nem_envia_o_registro(self):
        bruno = TestClient(main.app)
        bruno.post("/api/auth/signup", json={"name": "Bruno", "email": OUTRA[0], "password": OUTRA[1], "accept_privacy": True})
        self.assertEqual(bruno.get("/api/historico").json()["registros"], [])
        self.assertEqual(bruno.get(f"/api/historico/{self.registro['id']}/miniatura").status_code, 404)
        resposta = bruno.post("/api/historico/enviar", json={"destinatario": "x@exemplo.com", "historico_id": self.registro["id"]})
        self.assertEqual(resposta.status_code, 404)
        self.enviar.assert_not_called()

    def test_apagar_historico_remove_registros_e_miniaturas(self):
        self.entrar()
        self.assertEqual(self.cliente.delete("/api/historico").json()["apagados"], 1)
        self.assertEqual(self.cliente.get("/api/historico").json()["registros"], [])
        self.assertEqual(list((Path(self.pasta.name) / "miniaturas").rglob("*.jpg")), [])

    def test_historico_guarda_no_maximo_50(self):
        for n in range(55):
            self.historico.adicionar(self.admin_id, registro_exemplo(f"pagina-{n}.png"), None)
        self.assertEqual(len(self.historico.listar(self.admin_id)), 50)

    def test_id_invalido_responde_404(self):
        self.entrar()
        self.assertEqual(self.cliente.get("/api/historico/nao-e-um-uuid/miniatura").status_code, 404)

    # --- envio por e-mail ---

    def test_envio_exige_login(self):
        self.assertEqual(self.compartilhar().status_code, 401)
        self.enviar.assert_not_called()

    def test_envia_relatorio_e_imagem_do_banco(self):
        self.entrar()
        resposta = self.compartilhar()
        self.assertEqual(resposta.status_code, 200, resposta.text)
        destinatario, assunto, corpo, anexos = self.enviar.call_args.args
        self.assertEqual(destinatario, "colega@exemplo.com")
        self.assertIn("apostila.png", assunto)
        self.assertIn("Olha isso", corpo)
        self.assertIn("Livro sugerido: Cálculo", corpo)
        self.assertIn("1. Defina limite.", corpo)
        self.assertIn("Trecho reconhecido:", corpo)
        self.assertEqual([a[0] for a in anexos], ["apostila-relatorio.txt", "apostila.jpg"])
        self.assertEqual(anexos[1][1][:2], b"\xff\xd8")
        self.assertEqual(self.enviar.call_args.kwargs["responder_para"], EMAIL)

    def test_sem_imagem_envia_so_relatorio(self):
        self.entrar()
        self.assertEqual(self.compartilhar(anexar_imagem=False).status_code, 200)
        self.assertEqual(len(self.enviar.call_args.args[3]), 1)

    def test_valida_entrada(self):
        self.entrar()
        self.assertEqual(self.compartilhar(destinatario="sem-arroba").status_code, 400)
        self.assertEqual(self.compartilhar(historico_id="00000000-0000-0000-0000-000000000000").status_code, 404)
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
