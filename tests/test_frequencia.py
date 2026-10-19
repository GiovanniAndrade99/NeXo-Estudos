import unittest

import cv2
import numpy as np

from backend.frequencia import DESTAQUE_MINIMO, destaque_do_pico, espectro_magnitude, filtro_homomorfico, medir_inclinacao_fft
from backend.processamento import _corrigir_inclinacao, segmentar_texto


def pagina_de_texto(graus: float = 0.0) -> np.ndarray:
    """Página binária (texto preto em fundo branco) com "palavras" em linhas regulares."""
    rng = np.random.default_rng(0)
    imagem = np.full((900, 700), 255, np.uint8)
    for y in range(80, 820, 34):
        x = 60
        while x < 600:
            largura = int(rng.integers(20, 70))
            cv2.rectangle(imagem, (x, y), (min(x + largura, 640), y + 14), 0, -1)
            x += largura + 14
    matriz = cv2.getRotationMatrix2D((350, 450), graus, 1.0)
    return cv2.warpAffine(imagem, matriz, (700, 900), flags=cv2.INTER_NEAREST, borderValue=255)


class InclinacaoPorFFTTest(unittest.TestCase):
    def test_mede_o_angulo_em_faixa_larga(self):
        for graus in (0, 3, -8, 20, -35):
            with self.subTest(graus=graus):
                correcao, _, _ = medir_inclinacao_fft(pagina_de_texto(graus))
                # Mesma convenção de cv2.getRotationMatrix2D: girar pela correção desfaz a inclinação.
                self.assertAlmostEqual(correcao, -graus, delta=0.5)

    def test_lado_impar_nao_desloca_o_centro_do_espectro(self):
        # Com lado ímpar, a frequência zero fica em lado // 2; usar lado / 2 desviava 0,2° a 0,3°.
        for graus in (-10, 20, -35):
            with self.subTest(graus=graus):
                pagina = pagina_de_texto(graus)[:899, :701]
                self.assertAlmostEqual(medir_inclinacao_fft(pagina)[0], -graus, delta=0.1)

    def test_pipeline_endireita_alem_de_15_graus(self):
        alinhada, correcao = _corrigir_inclinacao(pagina_de_texto(30))
        self.assertAlmostEqual(correcao, -30, delta=0.5)
        self.assertLess(abs(medir_inclinacao_fft(alinhada)[0]), 0.5)

    def test_imagem_sem_texto_nao_e_girada(self):
        rng = np.random.default_rng(1)
        manchas = cv2.resize(rng.normal(0, 1, (30, 25)), (700, 900), interpolation=cv2.INTER_CUBIC)
        binaria = segmentar_texto(cv2.normalize(manchas, None, 30, 230, cv2.NORM_MINMAX).astype(np.uint8))
        _, _, energia = medir_inclinacao_fft(binaria)
        self.assertLess(destaque_do_pico(energia), DESTAQUE_MINIMO)
        self.assertEqual(_corrigir_inclinacao(binaria)[1], 0.0)

    def test_texto_tem_pico_destacado(self):
        _, _, energia = medir_inclinacao_fft(pagina_de_texto(12))
        self.assertGreater(destaque_do_pico(energia), DESTAQUE_MINIMO)


class EspectroTest(unittest.TestCase):
    def test_linhas_horizontais_viram_energia_no_eixo_vertical(self):
        listras = np.zeros((256, 256), np.float32)
        listras[::16] = 1.0  # período de 16 px na vertical
        espectro = espectro_magnitude(listras, janela=False)
        # Harmônico fundamental: 256 / 16 = 16 posições acima/abaixo do centro, na coluna central.
        self.assertGreater(espectro[128 - 16, 128], 100 * espectro[128, 128 - 16])

    def test_homomorfico_atenua_sombra(self):
        _, x = np.mgrid[0:400, 0:400]
        papel = np.full((400, 400), 230.0)
        for deslocamento in range(3):
            papel[deslocamento::25, :] = 40  # linhas de "texto" de 3 px
        fundo = papel > 100
        entrada = (papel * (0.5 + 0.5 * x / 400)).astype(np.uint8)  # luz cai pela metade da direita para a esquerda

        def desnivel(img: np.ndarray) -> float:
            """Diferença de brilho do papel entre direita e esquerda, relativa ao contraste tinta × papel."""
            img = img.astype(np.float64)
            esquerda = img[:, 50:150][fundo[:, 50:150]].mean()
            direita = img[:, 250:350][fundo[:, 250:350]].mean()
            return (direita - esquerda) / (img[fundo].mean() - img[~fundo].mean())

        filtrada, filtro = filtro_homomorfico(entrada, corte=0.005, ganho_alto=1.0)
        self.assertLess(desnivel(filtrada), 0.6 * desnivel(entrada))
        self.assertAlmostEqual(float(filtro[200, 200]), 0.4, places=3)  # centro = iluminação, atenuada
        self.assertAlmostEqual(float(filtro[0, 0]), 1.0, places=3)      # bordas = detalhes, mantidos


if __name__ == "__main__":
    unittest.main()
