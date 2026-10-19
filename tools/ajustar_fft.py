"""Escolha dos parâmetros da FFT usando só o conjunto de TREINO do FUNSD (e páginas sintéticas).

1. Medida de energia por direção: soma do log da magnitude × soma da magnitude linear.
2. Limiar do destaque do pico: páginas com texto × imagens sem texto.
3. Filtro homomórfico: grade de parâmetros, comparada à divisão pelo fundo pelo F1 do OCR.

O conjunto de teste não é usado aqui; ele fica para tools/avaliar_fft.py.
Uso: python tools/ajustar_fft.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
from avaliar_ocr import comparar, degradar, fotografar_em_perspectiva, palavras, texto_anotado  # noqa: E402
from backend.frequencia import (  # noqa: E402
    RAIO_MAXIMO, RAIO_MINIMO, _ajustar_tamanho, destaque_do_pico, espectro_magnitude, filtro_homomorfico, medir_inclinacao_fft,
)
from backend.perspectiva import corrigir_perspectiva  # noqa: E402
from backend.processamento import IDIOMAS_OCR, _ampliar_para_ocr, _configurar_tesseract, _corrigir_inclinacao, segmentar_texto  # noqa: E402

PASTA_TREINO = RAIZ / "datasets" / "funsd" / "dataset" / "training_data"
PALAVRAS = "processamento imagem sinal fourier frequencia texto linha pagina estudo prova aula nota de da o a e em para com que".split()


def _girar(imagem: np.ndarray, graus: float, cor=255) -> np.ndarray:
    altura, largura = imagem.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), graus, 1.0)
    return cv2.warpAffine(imagem, matriz, (largura, altura), flags=cv2.INTER_CUBIC, borderValue=cor)


def _binarizar(imagem_bgr: np.ndarray) -> np.ndarray:
    return segmentar_texto(_ampliar_para_ocr(cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY)))


def _texto_renderizado(semente: int) -> np.ndarray:
    """Página com 4 a 40 linhas de texto escrito pelo OpenCV, em tamanhos e espaçamentos variados."""
    rng = np.random.default_rng(semente)
    imagem = np.full((1100, 850), 255, np.uint8)
    escala = rng.uniform(0.6, 1.6)
    espaco, y = int(rng.uniform(1.4, 2.6) * 30 * escala), int(rng.integers(60, 150))
    for _ in range(int(rng.integers(4, 40))):
        if y > 1040:
            break
        fonte = cv2.FONT_HERSHEY_SIMPLEX if rng.random() < 0.5 else cv2.FONT_HERSHEY_COMPLEX
        cv2.putText(imagem, " ".join(rng.choice(PALAVRAS, size=12)), (int(rng.integers(30, 90)), y), fonte, escala, 0,
                    2 if escala > 1 else 1, cv2.LINE_AA)
        y += espaco
    return imagem


def _blocos_de_palavras(semente: int) -> np.ndarray:
    """Página muito regular: retângulos pretos no lugar das palavras, linhas igualmente espaçadas."""
    rng = np.random.default_rng(semente)
    imagem = np.full((900, 700), 255, np.uint8)
    periodo = int(rng.integers(24, 50))
    altura = int(periodo * rng.uniform(0.3, 0.5))
    for y in range(80, 820, periodo):
        x = 60
        while x < 600:
            largura = int(rng.integers(20, 70))
            cv2.rectangle(imagem, (x, y), (min(x + largura, 640), y + altura), 0, -1)
            x += largura + 14
    return imagem


def _sem_texto(rng: np.random.Generator, quantidade: int) -> list[np.ndarray]:
    imagens = []
    for _ in range(quantidade):
        escala = int(rng.choice([4, 8, 20, 50, 120]))
        campo = cv2.resize(rng.normal(0, 1, (1000 // escala + 2, 760 // escala + 2)), (760, 1000), interpolation=cv2.INTER_CUBIC)
        campo = cv2.normalize(campo, None, 30, 230, cv2.NORM_MINMAX) + rng.normal(0, 8, (1000, 760))
        imagens.append(segmentar_texto(np.clip(campo, 0, 255).astype(np.uint8)))
    foto = cv2.imread(str(RAIZ / "frontend" / "login" / "login-hero.jpg"))
    if foto is not None:
        for giro in (0, 15, 30):
            altura, largura = foto.shape[:2]
            matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), giro, 1.0)
            imagens.append(_binarizar(cv2.warpAffine(foto, matriz, (largura, altura), borderMode=cv2.BORDER_REFLECT)))
    return imagens


# ---------------------------------------------------------------- 1. medida de energia

def _energias(binaria: np.ndarray, limite: float = 45, passo: float = 0.1):
    """Magnitude amostrada nas mesmas retas de medir_inclinacao_fft, somada de dois jeitos."""
    tinta = _ajustar_tamanho(255 - binaria).astype(np.float32) / 255
    magnitude = espectro_magnitude(tinta).astype(np.float32)
    lado = magnitude.shape[0]
    centro = lado / 2
    raios = np.arange(max(2, int(RAIO_MINIMO * lado)), int(RAIO_MAXIMO * lado), dtype=np.float32)
    angulos = np.arange(-limite, limite + passo / 2, passo, dtype=np.float32)
    teta = np.deg2rad(angulos)[:, None]
    mapa_x = (centro + raios[None, :] * np.sin(teta)).astype(np.float32)
    mapa_y = (centro - raios[None, :] * np.cos(teta)).astype(np.float32)
    amostras = cv2.remap(magnitude, mapa_x, mapa_y, cv2.INTER_LINEAR)
    return angulos, {"soma do log da magnitude": np.log1p(amostras).sum(axis=1), "soma da magnitude (adotada)": amostras.sum(axis=1)}


def comparar_medidas() -> None:
    rng = np.random.default_rng(11)
    conjuntos = {"FUNSD treino, girado até ±40°": [], "texto renderizado (4 a 40 linhas)": [], "blocos de palavras (muito regular)": []}
    for caminho in sorted((PASTA_TREINO / "images").glob("*.png"))[::2]:
        giro = float(rng.uniform(-40, 40))
        conjuntos["FUNSD treino, girado até ±40°"].append((_binarizar(_girar(cv2.imread(str(caminho)), giro, (255, 255, 255))), -giro))
    for i in range(40):
        giro = float(rng.uniform(-40, 40))
        conjuntos["texto renderizado (4 a 40 linhas)"].append((segmentar_texto(_girar(_texto_renderizado(i), giro)), -giro))
        blocos = cv2.threshold(_girar(_blocos_de_palavras(100 + i), giro), 127, 255, cv2.THRESH_BINARY)[1]
        conjuntos["blocos de palavras (muito regular)"].append((blocos, -giro))
    print("1. Medida de energia por direção (erro do ângulo)")
    for nome, casos in conjuntos.items():
        erros = {}
        for binaria, certo in casos:
            angulos, energias = _energias(binaria)
            for medida, energia in energias.items():
                erros.setdefault(medida, []).append(abs(float(angulos[int(energia.argmax())]) - certo))
        print(f"\n  {nome} ({len(casos)} páginas)")
        for medida, lista in erros.items():
            e = np.array(lista)
            print(f"    {medida:30s} erro médio {e.mean():5.2f}°  máx {e.max():5.2f}°  até 1°: {100 * (e <= 1).mean():3.0f}%")


# ---------------------------------------------------------------- 2. limiar do destaque

def calibrar_limiar() -> None:
    rng = np.random.default_rng(5)
    com_texto = []
    for n, caminho in enumerate(sorted((PASTA_TREINO / "images").glob("*.png")), 1):
        imagem = cv2.imread(str(caminho))
        for entrada in (imagem, degradar(imagem, semente=500 + n), corrigir_perspectiva(fotografar_em_perspectiva(imagem, semente=500 + n))[0],
                        _girar(imagem, float(rng.uniform(-40, 40)), (255, 255, 255))):
            com_texto.append(destaque_do_pico(medir_inclinacao_fft(_binarizar(entrada))[2]))
    sem_texto = [destaque_do_pico(medir_inclinacao_fft(b)[2]) for b in _sem_texto(rng, 80)]
    com_texto, sem_texto = np.array(com_texto), np.array(sem_texto)
    print(f"\n2. Destaque do pico — {len(com_texto)} páginas de treino com texto (scan, foto, perspectiva, girada) "
          f"e {len(sem_texto)} imagens sem texto")
    print(f"  com texto: mínimo {com_texto.min():.2f}, mediana {np.median(com_texto):.2f}")
    print(f"  sem texto: máximo {sem_texto.max():.2f}, mediana {np.median(sem_texto):.2f}")
    escolhido = None
    for limiar in np.arange(3.0, 6.01, 0.5):
        aceitas = int((sem_texto >= limiar).sum())
        print(f"  limiar {limiar:.1f}: páginas com texto rejeitadas {int((com_texto < limiar).sum())}, imagens sem texto aceitas {aceitas}")
        escolhido = escolhido if escolhido is not None or aceitas else float(limiar)
    print(f"  menor limiar sem aceitar imagem sem texto: {escolhido}")


# ---------------------------------------------------------------- 3. homomórfico

def grade_homomorfica() -> None:
    config = f"--psm 6 {_configurar_tesseract()}".strip()

    def com_otsu(filtrar):
        def segmentar(cinza):
            _, binaria = cv2.threshold(cv2.medianBlur(filtrar(cinza), 3), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return binaria
        return segmentar

    variantes = {"divisão pelo fundo (adotada)": segmentar_texto}
    for corte, baixo, alto in ((0.002, 0.4, 1.0), (0.003, 0.4, 1.0), (0.005, 0.4, 1.0), (0.003, 0.2, 1.0), (0.003, 0.4, 1.5), (0.005, 0.4, 1.5)):
        variantes[f"homomórfico corte={corte} γL={baixo} γH={alto}"] = com_otsu(
            lambda cinza, c=corte, b=baixo, a=alto: filtro_homomorfico(cinza, c, b, a)[0])
    anotacoes = sorted((PASTA_TREINO / "annotations").glob("*.json"))[::7][:20]
    f1 = {(v, c): [] for v in variantes for c in ("scan", "foto")}
    for n, anotacao in enumerate(anotacoes, 1):
        imagem = cv2.imread(str(PASTA_TREINO / "images" / f"{anotacao.stem}.png"))
        esperadas = texto_anotado(anotacao)
        for condicao, entrada in (("scan", imagem), ("foto", degradar(imagem, semente=1000 + n))):
            ampliada = _ampliar_para_ocr(cv2.cvtColor(entrada, cv2.COLOR_BGR2GRAY))
            for nome, segmentar in variantes.items():
                alinhada, _ = _corrigir_inclinacao(segmentar(ampliada))
                texto = pytesseract.image_to_string(alinhada, lang=IDIOMAS_OCR, config=config)
                f1[(nome, condicao)].append(comparar(palavras(texto), esperadas)[2])
        print(f"  homomórfico: {n}/{len(anotacoes)}", end="\r")
    print(f"\n3. Iluminação — F1 do OCR em {len(anotacoes)} imagens de treino")
    for nome in variantes:
        print(f"  {nome:40s} scan {100 * np.mean(f1[(nome, 'scan')]):5.1f}%   foto {100 * np.mean(f1[(nome, 'foto')]):5.1f}%")


if __name__ == "__main__":
    comparar_medidas()
    calibrar_limiar()
    grade_homomorfica()
