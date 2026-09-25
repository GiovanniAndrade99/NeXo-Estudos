import unittest

import cv2
import numpy as np

from backend.processamento import _corrigir_inclinacao


def bloco_inclinado(graus: float) -> np.ndarray:
    imagem = np.full((600, 600), 255, np.uint8)
    cv2.rectangle(imagem, (150, 250), (450, 350), 0, -1)
    matriz = cv2.getRotationMatrix2D((300, 300), graus, 1.0)
    return cv2.warpAffine(imagem, matriz, (600, 600), borderValue=255)


def inclinacao_restante(binaria: np.ndarray) -> float:
    angulo = cv2.minAreaRect(cv2.findNonZero(255 - binaria))[-1]
    return min(abs(angulo), abs(abs(angulo) - 90))


class CorrecaoInclinacaoTest(unittest.TestCase):
    def test_endireita_nos_dois_sentidos(self):
        for graus in (5, -5, 12, -12):
            with self.subTest(graus=graus):
                alinhada, correcao = _corrigir_inclinacao(bloco_inclinado(graus))
                self.assertAlmostEqual(abs(correcao), abs(graus), delta=0.5)
                self.assertLess(inclinacao_restante(alinhada), 0.5)

    def test_ignora_pontos_de_ruido_nos_cantos(self):
        imagem = bloco_inclinado(5)
        for x, y in ((3, 3), (596, 3), (3, 596), (596, 596), (40, 520)):
            imagem[y, x] = 0
        _, correcao = _corrigir_inclinacao(imagem)
        self.assertAlmostEqual(abs(correcao), 5, delta=0.5)

    def test_pagina_reta_nao_gira(self):
        _, correcao = _corrigir_inclinacao(bloco_inclinado(0))
        self.assertAlmostEqual(correcao, 0.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
