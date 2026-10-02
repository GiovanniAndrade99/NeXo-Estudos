import unittest

import cv2
import numpy as np

from backend.perspectiva import corrigir_perspectiva
from backend.processamento import _medir_inclinacao


def pagina(largura=600, altura=800) -> np.ndarray:
    """Folha branca com linhas de "texto" e uma tabela, como uma apostila."""
    img = np.full((altura, largura, 3), 245, np.uint8)
    for y in range(80, altura - 80, 40):
        cv2.line(img, (60, y), (largura - 60 - (y % 120), y), (40, 40, 40), 4)
    cv2.rectangle(img, (40, 40), (largura - 40, altura - 40), (60, 60, 60), 2)  # borda impressa
    return img


def sobre_a_mesa(folha: np.ndarray, cantos) -> np.ndarray:
    altura, largura = folha.shape[:2]
    mesa = np.full((1000, 1100, 3), (60, 80, 105), np.uint8)
    matriz = cv2.getPerspectiveTransform(np.float32([[0, 0], [largura, 0], [largura, altura], [0, altura]]), np.float32(cantos))
    deformada = cv2.warpPerspective(folha, matriz, (1100, 1000))
    dentro = cv2.warpPerspective(np.ones((altura, largura), np.uint8), matriz, (1100, 1000)) > 0
    mesa[dentro] = deformada[dentro]
    return mesa


class TestPerspectiva(unittest.TestCase):
    def test_endireita_folha_fotografada_de_lado(self):
        foto = sobre_a_mesa(pagina(), [[260, 120], [820, 170], [900, 900], [180, 840]])
        corrigida, aplicou = corrigir_perspectiva(foto)
        self.assertTrue(aplicou)
        cinza = cv2.cvtColor(corrigida, cv2.COLOR_BGR2GRAY)
        # Depois de recortada, a imagem é praticamente só folha clara: o fundo escuro da mesa sumiu.
        self.assertGreater(cinza.mean(), 180)
        # As linhas de texto voltam a ficar horizontais. (A proporção exata do papel não é recuperável
        # de uma foto sem conhecer a câmera; para o OCR o que importa é o texto reto.)
        _, binaria = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self.assertLess(abs(_medir_inclinacao(binaria)), 1.0)

    def test_nao_mexe_em_scan_sem_fundo(self):
        scan = pagina()
        resultado, aplicou = corrigir_perspectiva(scan)
        self.assertFalse(aplicou)
        self.assertIs(resultado, scan)

    def test_nao_mexe_em_imagem_sem_folha(self):
        ruido = np.random.default_rng(1).integers(0, 255, (500, 500, 3), dtype=np.uint8)
        self.assertFalse(corrigir_perspectiva(ruido)[1])

    def test_folha_pequena_demais_e_ignorada(self):
        foto = sobre_a_mesa(pagina(), [[500, 450], [560, 455], [565, 530], [495, 525]])
        self.assertFalse(corrigir_perspectiva(foto)[1])


if __name__ == "__main__":
    unittest.main()
