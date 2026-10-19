"""Análise da página no domínio da frequência (FFT 2D).

O que as frequências significam numa página de texto:
* Baixas frequências (centro do espectro): variações lentas de brilho, como o papel, sombras
  e iluminação desigual.
* Frequências médias: a repetição das linhas de texto. Linhas igualmente espaçadas formam
  um padrão periódico, que no espectro vira uma faixa de pontos brilhantes passando pelo
  centro, perpendicular às linhas e girada no mesmo ângulo do texto.
* Altas frequências: bordas finas das letras, ruído do sensor e pontos de sujeira.

Usos no projeto:
1. medir_inclinacao_fft (usada no pipeline): encontra o ângulo da faixa das linhas de texto
   no espectro de magnitude, ou seja, a inclinação da página. destaque_do_pico diz se essa
   faixa existe de fato (página com texto) antes de girar a imagem.
2. filtro_homomorfico (avaliado, não usado): separa iluminação (baixa frequência) de conteúdo
   (alta frequência) no logaritmo da imagem e atenua a primeira. É o equivalente, em
   frequência, da divisão pelo fundo usada no pipeline (_normalizar_iluminacao), que se saiu
   melhor nas fotos; ver docs/FFT.md.
"""
from __future__ import annotations

import cv2
import numpy as np

LADO_ANALISE = 1024
# Faixa de ângulos procurada. No espectro, testar um ângulo a mais custa só uma reta a mais;
# por isso a faixa é larga (a projeção, que gira a imagem a cada ângulo, ficava em ±15°).
INCLINACAO_MAXIMA = 45.0
# Pico mínimo para aceitar o ângulo, em intervalos interquartis acima da mediana da energia.
# No treino do FUNSD, páginas com texto ficaram acima de 7,0 e imagens sem texto abaixo de 3,7.
# O limiar fica perto do lado "sem texto": não endireitar uma página custa OCR; girar uma
# imagem sem texto não custa nada. (5,0, o meio da faixa, rejeitou uma página esparsa do teste.)
DESTAQUE_MINIMO = 4.0
# Faixa de raios do espectro analisada, como fração do lado da imagem quadrada.
# Abaixo de RAIO_MINIMO está a iluminação; acima de RAIO_MAXIMO, ruído e detalhes das letras.
RAIO_MINIMO = 0.01
RAIO_MAXIMO = 0.25


def _ajustar_tamanho(imagem: np.ndarray, lado: int = LADO_ANALISE) -> np.ndarray:
    escala = lado / max(imagem.shape[:2])
    return cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA) if escala < 1 else imagem


def espectro_magnitude(sinal: np.ndarray, janela: bool = True) -> np.ndarray:
    """Espectro de magnitude centralizado (fftshift) de uma imagem quadrada.

    A imagem é posta num quadrado com zeros, para um ângulo no espectro corresponder ao mesmo
    ângulo na página, e multiplicada por uma janela de Hann, que evita a "cruz" falsa criada
    pelas bordas da imagem.
    """
    sinal = sinal.astype(np.float32)
    altura, largura = sinal.shape
    if janela:
        sinal = sinal * np.outer(np.hanning(altura), np.hanning(largura)).astype(np.float32)
    lado = max(altura, largura)
    quadrado = np.zeros((lado, lado), np.float32)
    topo, esquerda = (lado - altura) // 2, (lado - largura) // 2
    quadrado[topo:topo + altura, esquerda:esquerda + largura] = sinal
    return np.abs(np.fft.fftshift(np.fft.fft2(quadrado)))


def espectro_para_imagem(magnitude: np.ndarray) -> np.ndarray:
    """Escala logarítmica em 0-255, para visualizar o espectro."""
    log = np.log1p(magnitude)
    return cv2.normalize(log, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def medir_inclinacao_fft(binaria: np.ndarray, limite: float = INCLINACAO_MAXIMA, passo: float = 0.1) -> tuple[float, np.ndarray, np.ndarray]:
    """Inclinação da página pelo espectro: devolve (correção em graus, ângulos testados, energia por ângulo).

    Para cada ângulo, soma a magnitude ao longo de uma reta que sai do centro do espectro;
    a reta com mais energia é a das linhas de texto. A soma é feita na escala linear, não no
    logaritmo: assim pesam os picos (harmônicos do espaçamento entre linhas), e não o "piso"
    do espectro, que no logaritmo dominava e fazia páginas muito regulares errarem por 10° ou mais.
    A correção segue a convenção de cv2.getRotationMatrix2D: girar a página por esse ângulo
    deixa o texto na horizontal.
    """
    tinta = _ajustar_tamanho(255 - binaria).astype(np.float32) / 255
    magnitude = espectro_magnitude(tinta).astype(np.float32)
    lado = magnitude.shape[0]
    centro = float(lado // 2)  # posição da frequência zero após o fftshift, para lado par ou ímpar
    raios = np.arange(max(2, int(RAIO_MINIMO * lado)), int(RAIO_MAXIMO * lado), dtype=np.float32)
    angulos = np.arange(-limite, limite + passo / 2, passo, dtype=np.float32)
    teta = np.deg2rad(angulos)[:, None]
    # Texto horizontal concentra energia no eixo vertical do espectro; texto girado gira essa faixa.
    mapa_x = (centro + raios[None, :] * np.sin(teta)).astype(np.float32)
    mapa_y = (centro - raios[None, :] * np.cos(teta)).astype(np.float32)
    energia = cv2.remap(magnitude, mapa_x, mapa_y, cv2.INTER_LINEAR).sum(axis=1)
    return float(angulos[int(energia.argmax())]), angulos, energia


def destaque_do_pico(energia: np.ndarray) -> float:
    """Quanto a direção mais forte do espectro se destaca das demais (0 = espectro sem direção).

    Medido em intervalos interquartis acima da mediana, para não depender do brilho da imagem.
    Linhas de texto formam um pico estreito e alto; fotos e imagens sem texto, uma curva quase plana.
    """
    mediana = np.median(energia)
    q1, q3 = np.percentile(energia, (25, 75))
    return float((energia.max() - mediana) / max(q3 - q1, 1e-9))


def filtro_homomorfico(cinza: np.ndarray, corte: float = 0.003, ganho_baixo: float = 0.4, ganho_alto: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Filtro homomórfico: atenua a iluminação (baixas frequências) e preserva o conteúdo.

    imagem = iluminação × refletância. No logaritmo, o produto vira soma; a FFT separa a
    iluminação (varia devagar, baixa frequência) da refletância (letras, alta frequência).
    Um filtro gaussiano multiplica as frequências abaixo do corte (em ciclos por pixel) por
    ganho_baixo e as acima por ganho_alto; a imagem volta pela FFT inversa e pela exponencial.
    Os padrões foram escolhidos no treino do FUNSD (ganho_alto > 1 realçava ruído e piorava o OCR).
    Devolve (imagem filtrada, filtro H).
    """
    altura, largura = cinza.shape
    log = np.log1p(cinza.astype(np.float32))
    espectro = np.fft.fftshift(np.fft.fft2(log))
    v, u = np.meshgrid(np.arange(altura) - altura // 2, np.arange(largura) - largura // 2, indexing="ij")
    distancia2 = (u / largura) ** 2 + (v / altura) ** 2   # frequência normalizada (ciclos por pixel)
    filtro = (ganho_alto - ganho_baixo) * (1 - np.exp(-distancia2 / (2 * corte ** 2))) + ganho_baixo
    resultado = np.real(np.fft.ifft2(np.fft.ifftshift(espectro * filtro)))
    resultado = np.expm1(resultado)
    # Percentis em vez de mínimo/máximo: poucos pixels extremos não achatam o contraste do resto.
    baixo, alto = np.percentile(resultado, (0.5, 99.5))
    resultado = np.clip((resultado - baixo) / max(alto - baixo, 1e-6), 0, 1) * 255
    return resultado.astype(np.uint8), filtro.astype(np.float32)
