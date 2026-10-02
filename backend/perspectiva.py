"""Correção de perspectiva: endireita uma folha fotografada de lado.

1. Detecta bordas (Canny) numa versão reduzida da imagem e procura o maior contorno
   que, simplificado (approxPolyDP), vire um quadrilátero convexo.
2. Só aceita o quadrilátero se ele ocupar boa parte da foto, não for a própria moldura
   da imagem e a folha for bem mais clara que o fundo ao redor. Isso evita "corrigir"
   um scan comum, em que o maior retângulo costuma ser a borda de uma tabela impressa.
3. Ordena os cantos e aplica uma transformação de perspectiva (warpPerspective) que leva
   a folha para um retângulo do tamanho dos seus lados.
"""
from __future__ import annotations

import cv2
import numpy as np

LADO_ANALISE = 900
AREA_MINIMA = 0.20       # a folha precisa ocupar pelo menos 20% da foto
AREA_MAXIMA = 0.97       # acima disso é a própria moldura da imagem: nada a corrigir
CONTRASTE_MINIMO = 25    # folha pelo menos 25 níveis de cinza mais clara que o fundo


def _ordenar_cantos(pontos: np.ndarray) -> np.ndarray:
    """Superior esquerdo, superior direito, inferior direito, inferior esquerdo."""
    pontos = pontos.reshape(4, 2).astype(np.float32)
    soma, diferenca = pontos.sum(axis=1), np.diff(pontos, axis=1).ravel()
    return np.array([pontos[soma.argmin()], pontos[diferenca.argmin()], pontos[soma.argmax()], pontos[diferenca.argmax()]], np.float32)


def _encontrar_folha(cinza: np.ndarray) -> np.ndarray | None:
    altura, largura = cinza.shape
    area_total = altura * largura
    suave = cv2.GaussianBlur(cinza, (5, 5), 0)
    bordas = cv2.Canny(suave, 40, 120)
    bordas = cv2.morphologyEx(bordas, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    contornos, _ = cv2.findContours(bordas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contorno in sorted(contornos, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(contorno)
        if not AREA_MINIMA * area_total <= area <= AREA_MAXIMA * area_total:
            continue
        aproximado = cv2.approxPolyDP(contorno, 0.02 * cv2.arcLength(contorno, True), True)
        if len(aproximado) != 4 or not cv2.isContourConvex(aproximado):
            continue
        dentro = np.zeros_like(cinza)
        cv2.fillConvexPoly(dentro, aproximado.reshape(4, 2), 255)
        anel = cv2.dilate(dentro, np.ones((31, 31), np.uint8)) & ~dentro  # faixa de fundo logo fora da folha
        if anel.any() and cv2.mean(cinza, dentro)[0] - cv2.mean(cinza, anel)[0] >= CONTRASTE_MINIMO:
            return _ordenar_cantos(aproximado)
    return None


def corrigir_perspectiva(imagem_bgr: np.ndarray) -> tuple[np.ndarray, bool]:
    """Devolve (imagem endireitada, True) quando acha a folha; senão (imagem original, False)."""
    altura, largura = imagem_bgr.shape[:2]
    escala = min(1.0, LADO_ANALISE / max(altura, largura))
    pequena = cv2.resize(imagem_bgr, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA) if escala < 1 else imagem_bgr
    cantos = _encontrar_folha(cv2.cvtColor(pequena, cv2.COLOR_BGR2GRAY))
    if cantos is None:
        return imagem_bgr, False
    cantos /= escala
    tl, tr, br, bl = cantos
    largura_folha = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    altura_folha = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if min(largura_folha, altura_folha) < 100:
        return imagem_bgr, False
    destino = np.array([[0, 0], [largura_folha - 1, 0], [largura_folha - 1, altura_folha - 1], [0, altura_folha - 1]], np.float32)
    matriz = cv2.getPerspectiveTransform(cantos, destino)
    return cv2.warpPerspective(imagem_bgr, matriz, (largura_folha, altura_folha), flags=cv2.INTER_CUBIC), True
