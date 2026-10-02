"""Histórico de processamentos guardado no servidor, separado por usuário.

Duas implementações com a mesma interface:
* RepositorioHistoricoSQLite + ArmazenamentoLocal: testes e uso sem Supabase.
* RepositorioHistoricoPostgres (em banco_postgres.py) + ArmazenamentoSupabase: produção.

Toda operação recebe o id do usuário da sessão; nunca um id vindo do navegador.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

import cv2
import numpy as np

MAXIMO_REGISTROS = 50
LADO_MAXIMO_MINIATURA = 1400
TAMANHO_TRECHO = 400


def gerar_miniatura(imagem_bgr: np.ndarray) -> bytes:
    """JPEG reduzido da imagem original, usado na comparação e no envio por e-mail."""
    altura, largura = imagem_bgr.shape[:2]
    escala = min(1.0, LADO_MAXIMO_MINIATURA / max(altura, largura))
    if escala < 1:
        imagem_bgr = cv2.resize(imagem_bgr, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", imagem_bgr, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not ok:
        raise ValueError("Não foi possível gerar a miniatura.")
    return buffer.tobytes()


def montar_registro(nome_arquivo: str, pagina: int | None, largura: int, altura: int, tempo_ms: float,
                    ocr_disponivel: bool, inclinacao: float | None, texto: str, assistente: dict) -> dict:
    texto = (texto or "").strip()
    return {
        "nome_arquivo": nome_arquivo[:300],
        "pagina": pagina,
        "largura": largura,
        "altura": altura,
        "tempo_ms": tempo_ms,
        "ocr_disponivel": bool(ocr_disponivel),
        "inclinacao_graus": inclinacao,
        "palavras": len(texto.split()),
        "trecho": texto[:TAMANHO_TRECHO],
        "assistente": assistente or {},
    }


def caminho_miniatura(usuario_id: int | str, registro_id: str) -> str:
    return f"{int(usuario_id)}/{registro_id}.jpg"


class ArmazenamentoLocal:
    """Guarda as miniaturas numa pasta do servidor (equivalente local ao bucket do Supabase)."""

    def __init__(self, pasta: Path | str):
        self.pasta = Path(pasta)

    def _arquivo(self, caminho: str) -> Path:
        destino = (self.pasta / caminho).resolve()
        if self.pasta.resolve() not in destino.parents:
            raise ValueError("Caminho de miniatura inválido.")
        return destino

    def enviar(self, caminho: str, conteudo: bytes) -> None:
        arquivo = self._arquivo(caminho)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(conteudo)

    def baixar(self, caminho: str) -> bytes | None:
        arquivo = self._arquivo(caminho)
        return arquivo.read_bytes() if arquivo.exists() else None

    def apagar(self, caminhos: list[str]) -> None:
        for caminho in caminhos:
            self._arquivo(caminho).unlink(missing_ok=True)


class RepositorioHistoricoSQLite:
    def __init__(self, caminho_banco: Path | str, armazenamento: ArmazenamentoLocal):
        self.caminho = Path(caminho_banco)
        self.armazenamento = armazenamento
        with self._conectar() as banco:
            banco.execute("""
                CREATE TABLE IF NOT EXISTS processamentos (
                    id TEXT PRIMARY KEY,
                    usuario_id INTEGER NOT NULL,
                    dados TEXT NOT NULL,
                    miniatura_caminho TEXT,
                    criado_em REAL NOT NULL
                )
            """)

    def _conectar(self):
        banco = sqlite3.connect(self.caminho)
        banco.row_factory = sqlite3.Row
        return _Transacao(banco)

    @staticmethod
    def _publico(linha: sqlite3.Row) -> dict:
        return {"id": linha["id"], **json.loads(linha["dados"]), "criado_em": linha["criado_em"],
                "tem_miniatura": bool(linha["miniatura_caminho"])}

    def adicionar(self, usuario_id: int | str, registro: dict, miniatura: bytes | None) -> dict:
        registro_id = str(uuid.uuid4())
        caminho = caminho_miniatura(usuario_id, registro_id) if miniatura else None
        if miniatura:
            self.armazenamento.enviar(caminho, miniatura)
        with self._conectar() as banco:
            banco.execute(
                "INSERT INTO processamentos (id, usuario_id, dados, miniatura_caminho, criado_em) VALUES (?, ?, ?, ?, ?)",
                (registro_id, int(usuario_id), json.dumps(registro, ensure_ascii=False), caminho, time.time()),
            )
            excedentes = banco.execute(
                "SELECT id, miniatura_caminho FROM processamentos WHERE usuario_id = ? ORDER BY criado_em DESC LIMIT -1 OFFSET ?",
                (int(usuario_id), MAXIMO_REGISTROS),
            ).fetchall()
            banco.executemany("DELETE FROM processamentos WHERE id = ?", [(l["id"],) for l in excedentes])
            linha = banco.execute("SELECT * FROM processamentos WHERE id = ?", (registro_id,)).fetchone()
        self.armazenamento.apagar([l["miniatura_caminho"] for l in excedentes if l["miniatura_caminho"]])
        return self._publico(linha)

    def listar(self, usuario_id: int | str, limite: int = MAXIMO_REGISTROS) -> list[dict]:
        with self._conectar() as banco:
            linhas = banco.execute(
                "SELECT * FROM processamentos WHERE usuario_id = ? ORDER BY criado_em DESC LIMIT ?", (int(usuario_id), limite)
            ).fetchall()
        return [self._publico(l) for l in linhas]

    def obter(self, usuario_id: int | str, registro_id: str) -> dict | None:
        with self._conectar() as banco:
            linha = banco.execute(
                "SELECT * FROM processamentos WHERE id = ? AND usuario_id = ?", (registro_id, int(usuario_id))
            ).fetchone()
        return self._publico(linha) if linha else None

    def miniatura(self, usuario_id: int | str, registro_id: str) -> bytes | None:
        with self._conectar() as banco:
            linha = banco.execute(
                "SELECT miniatura_caminho FROM processamentos WHERE id = ? AND usuario_id = ?", (registro_id, int(usuario_id))
            ).fetchone()
        return self.armazenamento.baixar(linha["miniatura_caminho"]) if linha and linha["miniatura_caminho"] else None

    def apagar_tudo(self, usuario_id: int | str) -> int:
        with self._conectar() as banco:
            caminhos = [l["miniatura_caminho"] for l in banco.execute(
                "SELECT miniatura_caminho FROM processamentos WHERE usuario_id = ?", (int(usuario_id),))]
            apagados = banco.execute("DELETE FROM processamentos WHERE usuario_id = ?", (int(usuario_id),)).rowcount
        self.armazenamento.apagar([c for c in caminhos if c])
        return apagados


class _Transacao:
    """Abre a transação e sempre fecha a conexão (o "with" do sqlite3 não fecha)."""

    def __init__(self, banco: sqlite3.Connection):
        self.banco = banco

    def __enter__(self) -> sqlite3.Connection:
        return self.banco.__enter__()

    def __exit__(self, *erro):
        with closing(self.banco):
            return self.banco.__exit__(*erro)
