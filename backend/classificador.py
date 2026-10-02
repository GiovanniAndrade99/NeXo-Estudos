"""Classificador de matérias treinado (TF-IDF + Regressão Logística).

Treinado por tools/treinar_classificador.py com trechos da Wikipédia em português;
métricas em docs/CLASSIFICADOR.md. O modelo só decide quando está confiante: abaixo de
CONFIANCA_MINIMA, o Assistente de Estudos volta às regras de palavras-chave.
"""
from __future__ import annotations

import logging
import unicodedata
from functools import lru_cache
from pathlib import Path

ARQUIVO_MODELO = Path(__file__).resolve().parent / "modelos" / "classificador_materias.joblib"
# Na avaliação, com confiança >= 0,4 o modelo classificou ~74% dos textos de teste e acertou ~93% deles.
CONFIANCA_MINIMA = 0.4
PALAVRAS_MINIMAS = 15
logger = logging.getLogger(__name__)


def normalizar_para_modelo(texto: str) -> str:
    """Pré-processamento do TF-IDF: minúsculas e sem acentos (o OCR erra muito os acentos).

    Precisa ficar neste módulo: o modelo salvo guarda uma referência a esta função,
    e ela tem de ser importável pelo app ao carregar o arquivo.
    """
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


@lru_cache(maxsize=1)
def _modelo():
    try:
        import joblib
        return joblib.load(ARQUIVO_MODELO)
    except Exception:  # sem scikit-learn, sem o arquivo ou versão incompatível: o app segue só com as regras
        logger.warning("Classificador de matérias indisponível; usando apenas as regras de palavras-chave.", exc_info=True)
        return None


def classificar_materia(texto: str) -> tuple[str, float] | None:
    """Devolve (chave da matéria, confiança) quando o modelo está confiante; senão, None."""
    if len((texto or "").split()) < PALAVRAS_MINIMAS:
        return None  # texto curto demais para uma decisão estatística confiável
    modelo = _modelo()
    if modelo is None:
        return None
    probabilidades = modelo.predict_proba([texto])[0]
    indice = int(probabilidades.argmax())
    confianca = float(probabilidades[indice])
    return (str(modelo.classes_[indice]), confianca) if confianca >= CONFIANCA_MINIMA else None
