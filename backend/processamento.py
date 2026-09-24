"""Pré-processamento de páginas e reconhecimento óptico de caracteres."""
from __future__ import annotations

import os
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

IDIOMAS_OCR = os.getenv("OCR_LANGUAGES", "por+eng")
LIMITE_LADO = 4000


@dataclass
class ResultadoProcessamento:
    original: np.ndarray
    tons_cinza: np.ndarray
    tratada: np.ndarray
    texto: str
    inclinacao_corrigida_graus: float
    ocr_disponivel: bool
    aviso: str | None = None


def _configurar_tesseract() -> None:
    executavel = os.getenv("TESSERACT_CMD")
    if executavel:
        pytesseract.pytesseract.tesseract_cmd = executavel


def tesseract_disponivel() -> tuple[bool, str | None]:
    _configurar_tesseract()
    try:
        pytesseract.get_tesseract_version()
        idiomas = set(pytesseract.get_languages(config=""))
        ausentes = {idioma for idioma in IDIOMAS_OCR.split("+") if idioma not in idiomas}
        if ausentes:
            return False, "Pacote(s) de idioma ausente(s) no Tesseract: " + ", ".join(sorted(ausentes)) + "."
        return True, None
    except (pytesseract.TesseractNotFoundError, OSError):
        return False, "Tesseract não encontrado. Instale o programa e os idiomas configurados para habilitar OCR."


def decodificar_imagem(conteudo: bytes) -> np.ndarray:
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise ValueError("O arquivo não parece ser uma imagem válida ou usa um formato não suportado.")
    altura, largura = imagem.shape[:2]
    if largura > LIMITE_LADO or altura > LIMITE_LADO:
        escala = LIMITE_LADO / max(largura, altura)
        imagem = cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    return imagem


def _corrigir_inclinacao(binaria: np.ndarray) -> tuple[np.ndarray, float]:
    pontos = cv2.findNonZero(255 - binaria)
    if pontos is None or len(pontos) < 20:
        return binaria, 0.0
    angulo = cv2.minAreaRect(pontos)[-1]
    if angulo < -45:
        angulo = 90 + angulo
    if abs(angulo) > 15:
        return binaria, 0.0
    correcao = -float(angulo)
    altura, largura = binaria.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), correcao, 1.0)
    alinhada = cv2.warpAffine(
        binaria, matriz, (largura, altura), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=255,
    )
    return alinhada, correcao


def processar(imagem: np.ndarray) -> ResultadoProcessamento:
    tons_cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    contraste = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(tons_cinza)
    sem_ruido = cv2.medianBlur(contraste, 3)
    binaria = cv2.adaptiveThreshold(
        sem_ruido, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 11,
    )
    alinhada, inclinacao = _corrigir_inclinacao(binaria)
    disponivel, aviso = tesseract_disponivel()
    texto = ""
    if disponivel:
        try:
            texto = pytesseract.image_to_string(alinhada, lang=IDIOMAS_OCR, config="--psm 6").strip()
        except pytesseract.TesseractError as erro:
            disponivel = False
            aviso = "O Tesseract não conseguiu processar esta imagem: " + str(erro)
    return ResultadoProcessamento(
        original=imagem, tons_cinza=tons_cinza, tratada=alinhada, texto=texto,
        inclinacao_corrigida_graus=round(inclinacao, 2),
        ocr_disponivel=disponivel, aviso=aviso,
    )


def codificar_png(imagem: np.ndarray) -> str:
    import base64
    sucesso, buffer = cv2.imencode(".png", imagem)
    if not sucesso:
        raise RuntimeError("Não foi possível gerar a imagem de visualização.")
    return base64.b64encode(buffer.tobytes()).decode("ascii")
