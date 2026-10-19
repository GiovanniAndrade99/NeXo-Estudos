"""Avaliação do uso da FFT no pipeline (FUNSD, conjunto de teste) e figuras de docs/FFT.md.

1. Inclinação: compara a medida pelo espectro (backend.frequencia.medir_inclinacao_fft, usada
   no app) com o método anterior, o perfil de projeção horizontal. A resposta certa é conhecida
   porque a rotação é aplicada pelo próprio script. Mede também o F1 do OCR em páginas giradas
   de 15° a 40°, além do alcance do método anterior.
2. Confiança: o destaque do pico separa páginas com texto de imagens sem texto?
3. Iluminação: filtro homomórfico (FFT) contra a divisão pelo fundo usada no app, pelo F1 do OCR.
4. Figuras: espectro de uma página torta e reta, energia por ângulo, magnitude × fase,
   passa-baixa × passa-alta e o filtro homomórfico.

Uso: python tools/avaliar_fft.py [--sem-ocr]
Saídas: docs/fft/resultados.json e figuras em docs/fft/.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
from avaliar_ocr import PASTA_TESTE, baixar_funsd, comparar, degradar, palavras, texto_anotado  # noqa: E402
from backend.frequencia import (  # noqa: E402
    DESTAQUE_MINIMO, INCLINACAO_MAXIMA, destaque_do_pico, espectro_magnitude, espectro_para_imagem,
    filtro_homomorfico, medir_inclinacao_fft,
)
from backend.processamento import (  # noqa: E402
    IDIOMAS_OCR, _ampliar_para_ocr, _configurar_tesseract, _corrigir_inclinacao, _normalizar_iluminacao, segmentar_texto,
)

PASTA_SAIDA = RAIZ / "docs" / "fft"


def inclinacao_por_projecao(binaria: np.ndarray, limite: float) -> float:
    """Método usado antes da FFT: gira a imagem a cada ângulo e procura a maior variância das somas por linha."""
    tinta = 255 - binaria
    escala = 1000 / max(tinta.shape)
    if escala < 1:
        tinta = cv2.resize(tinta, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    altura, largura = tinta.shape

    def nitidez(angulo: float) -> float:
        matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), angulo, 1.0)
        girada = cv2.warpAffine(tinta, matriz, (largura, altura), flags=cv2.INTER_NEAREST, borderValue=0)
        return float(np.var(girada.sum(axis=1, dtype=np.float64)))

    grosso = max(np.arange(-limite, limite + 0.01, 1.0), key=nitidez)
    return float(max(np.arange(grosso - 1, grosso + 1.01, 0.1), key=nitidez))


METODOS = {
    "projeção ±15° (método anterior)": lambda b: inclinacao_por_projecao(b, 15),
    "projeção ±45°": lambda b: inclinacao_por_projecao(b, 45),
    f"FFT ±{INCLINACAO_MAXIMA:.0f}° (usado no app)": lambda b: medir_inclinacao_fft(b)[0],
}


def _girar(imagem: np.ndarray, graus: float) -> np.ndarray:
    altura, largura = imagem.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), graus, 1.0)
    return cv2.warpAffine(imagem, matriz, (largura, altura), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def _binarizar(imagem_bgr: np.ndarray) -> np.ndarray:
    return segmentar_texto(_ampliar_para_ocr(cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY)))


def avaliar_inclinacao(imagens: list[np.ndarray]) -> dict:
    rng = np.random.default_rng(2024)
    cenarios = {"foto simulada (giro de 3° a 6°)": [], "giro grande (até ±40°)": []}
    for n, imagem in enumerate(imagens, 1):
        foto, matriz = degradar(imagem, semente=n, com_transformacao=True)
        aplicado = float(np.degrees(np.arctan2(matriz[0, 1], matriz[0, 0])))
        cenarios["foto simulada (giro de 3° a 6°)"].append((_binarizar(foto), -aplicado))
        giro = float(rng.uniform(-40, 40))
        cenarios["giro grande (até ±40°)"].append((_binarizar(_girar(imagem, giro)), -giro))
    resultado = {}
    for cenario, casos in cenarios.items():
        resultado[cenario] = {}
        for metodo, medir in METODOS.items():
            inicio = time.perf_counter()
            erros = np.array([abs(medir(binaria) - certo) for binaria, certo in casos])
            ms = 1000 * (time.perf_counter() - inicio) / len(casos)
            resultado[cenario][metodo] = {
                "erro_medio": float(erros.mean()), "erro_mediano": float(np.median(erros)), "erro_maximo": float(erros.max()),
                "fracao_ate_1_grau": float((erros <= 1).mean()), "ms_por_pagina": ms,
            }
    return resultado


def _girar_sem_cortar(imagem: np.ndarray, graus: float) -> np.ndarray:
    """Gira a página numa tela branca maior, para nenhum canto do texto sair da imagem."""
    altura, largura = imagem.shape[:2]
    margem = int(np.hypot(altura, largura) - min(altura, largura)) // 2 + 1
    tela = cv2.copyMakeBorder(imagem, margem, margem, margem, margem, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    return _girar(tela, graus)


def _endireitar(binaria: np.ndarray, correcao: float) -> np.ndarray:
    """Mesma rotação de _corrigir_inclinacao, para aplicar o ângulo de outro método."""
    if abs(correcao) < 0.2:
        return binaria
    altura, largura = binaria.shape[:2]
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), correcao, 1.0)
    return cv2.warpAffine(binaria, matriz, (largura, altura), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def avaliar_ocr_paginas_tortas(anotacoes: list[Path]) -> dict:
    """F1 do OCR em páginas giradas de 15° a 40°: pipeline com a projeção ±15° (antes) × com a FFT (agora)."""
    config = f"--psm 6 {_configurar_tesseract()}".strip()
    rng = np.random.default_rng(77)
    f1 = {"projeção ±15° (antes)": [], "FFT ±45° (agora)": []}
    for n, anotacao in enumerate(anotacoes, 1):
        imagem = cv2.imread(str(PASTA_TESTE / "images" / f"{anotacao.stem}.png"))
        giro = float(rng.uniform(15, 40) * rng.choice([-1, 1]))
        binaria = _binarizar(_girar_sem_cortar(imagem, giro))
        esperadas = texto_anotado(anotacao)
        alinhadas = {"projeção ±15° (antes)": _endireitar(binaria, inclinacao_por_projecao(binaria, 15)),
                     "FFT ±45° (agora)": _corrigir_inclinacao(binaria)[0]}
        for metodo, alinhada in alinhadas.items():
            texto = pytesseract.image_to_string(alinhada, lang=IDIOMAS_OCR, config=config)
            f1[metodo].append(comparar(palavras(texto), esperadas)[2])
        print(f"  páginas tortas: {n}/{len(anotacoes)}", end="\r")
    return {metodo: float(np.mean(valores)) for metodo, valores in f1.items()}


def _sem_texto(quantidade: int) -> list[np.ndarray]:
    """Imagens sem texto: manchas aleatórias em várias escalas (como fotos) e a foto da tela de login."""
    rng = np.random.default_rng(99)
    imagens = []
    for _ in range(quantidade):
        escala = int(rng.choice([8, 20, 50, 120]))
        campo = cv2.resize(rng.normal(0, 1, (1000 // escala + 2, 760 // escala + 2)), (760, 1000), interpolation=cv2.INTER_CUBIC)
        campo = cv2.normalize(campo, None, 30, 230, cv2.NORM_MINMAX) + rng.normal(0, 8, (1000, 760))
        imagens.append(np.clip(campo, 0, 255).astype(np.uint8))
    foto = cv2.imread(str(RAIZ / "frontend" / "login" / "login-hero.jpg"), cv2.IMREAD_GRAYSCALE)
    if foto is not None:
        imagens.append(foto)
    return [segmentar_texto(imagem) for imagem in imagens]


def avaliar_confianca(imagens: list[np.ndarray]) -> dict:
    com_texto = [destaque_do_pico(medir_inclinacao_fft(_binarizar(imagem))[2]) for imagem in imagens]
    sem_texto = [destaque_do_pico(medir_inclinacao_fft(binaria)[2]) for binaria in _sem_texto(30)]
    return {
        "limiar": DESTAQUE_MINIMO,
        "paginas_com_texto": len(com_texto), "destaque_minimo_com_texto": float(min(com_texto)),
        "paginas_aceitas": int(sum(d >= DESTAQUE_MINIMO for d in com_texto)),
        "imagens_sem_texto": len(sem_texto), "destaque_maximo_sem_texto": float(max(sem_texto)),
        "imagens_sem_texto_giradas": int(sum(d >= DESTAQUE_MINIMO for d in sem_texto)),
    }


def avaliar_iluminacao(anotacoes: list[Path]) -> dict:
    config = f"--psm 6 {_configurar_tesseract()}".strip()

    def homomorfico(cinza):
        _, binaria = cv2.threshold(cv2.medianBlur(filtro_homomorfico(cinza)[0], 3), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binaria

    variantes = {"divisão pelo fundo (usada no app)": segmentar_texto, "filtro homomórfico (FFT)": homomorfico}
    f1 = {(v, c): [] for v in variantes for c in ("scan original", "foto simulada")}
    for n, anotacao in enumerate(anotacoes, 1):
        imagem = cv2.imread(str(PASTA_TESTE / "images" / f"{anotacao.stem}.png"))
        esperadas = texto_anotado(anotacao)
        for condicao, entrada in (("scan original", imagem), ("foto simulada", degradar(imagem, semente=n))):
            ampliada = _ampliar_para_ocr(cv2.cvtColor(entrada, cv2.COLOR_BGR2GRAY))
            for nome, segmentar in variantes.items():
                alinhada, _ = _corrigir_inclinacao(segmentar(ampliada))
                texto = pytesseract.image_to_string(alinhada, lang=IDIOMAS_OCR, config=config)
                f1[(nome, condicao)].append(comparar(palavras(texto), esperadas)[2])
        print(f"  iluminação: {n}/{len(anotacoes)}", end="\r")
    return {condicao: {nome: float(np.mean(f1[(nome, condicao)])) for nome in variantes}
            for condicao in ("scan original", "foto simulada")}


# ---------------------------------------------------------------- figuras

def _rotular(painel: np.ndarray, texto: str) -> np.ndarray:
    if painel.ndim == 2:
        painel = cv2.cvtColor(painel, cv2.COLOR_GRAY2BGR)
    faixa = np.full((34, painel.shape[1], 3), 255, np.uint8)
    cv2.putText(faixa, texto, (8, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
    return np.vstack([faixa, painel])


def _juntar(paineis: list[np.ndarray]) -> np.ndarray:
    altura = max(p.shape[0] for p in paineis)
    paineis = [np.vstack([p, np.full((altura - p.shape[0], p.shape[1], 3), 255, np.uint8)]) for p in paineis]
    separador = np.full((altura, 10, 3), 255, np.uint8)
    return np.hstack([p for painel in paineis for p in (painel, separador)][:-1])


def _quadrado(imagem: np.ndarray, lado: int = 420) -> np.ndarray:
    escala = lado / max(imagem.shape[:2])
    return cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)


def _espectro_com_reta(binaria: np.ndarray, angulo: float | None) -> np.ndarray:
    tinta = (255 - cv2.resize(binaria, None, fx=1024 / max(binaria.shape), fy=1024 / max(binaria.shape),
                              interpolation=cv2.INTER_AREA)).astype(np.float32) / 255
    espectro = cv2.cvtColor(espectro_para_imagem(espectro_magnitude(tinta)), cv2.COLOR_GRAY2BGR)
    lado = espectro.shape[0]
    zoom = espectro[lado // 4: 3 * lado // 4, lado // 4: 3 * lado // 4].copy()  # metade central: onde está a faixa
    if angulo is not None:
        # Mesma reta que medir_inclinacao_fft amostra (x = c + r·sen, y = c − r·cos), marcada só nas
        # pontas para não cobrir a faixa.
        c = zoom.shape[0] / 2
        seno, cosseno = np.sin(np.radians(angulo)), np.cos(np.radians(angulo))
        for sinal in (1, -1):
            inicio, fim = sinal * 0.72 * c, sinal * 0.98 * c
            cv2.line(zoom, (int(c + inicio * seno), int(c - inicio * cosseno)), (int(c + fim * seno), int(c - fim * cosseno)),
                     (40, 40, 230), 3, cv2.LINE_AA)
    return zoom


def _grafico(angulos, energia, pico, largura=720, altura=380) -> np.ndarray:
    img = np.full((altura, largura, 3), 255, np.uint8)
    margem_x, margem_y = 60, 40
    x = margem_x + (angulos - angulos[0]) / (angulos[-1] - angulos[0]) * (largura - margem_x - 20)
    e = (energia - energia.min()) / (energia.max() - energia.min())
    y = altura - margem_y - e * (altura - 2 * margem_y)
    cv2.line(img, (margem_x, altura - margem_y), (largura - 20, altura - margem_y), (90, 90, 90), 1)
    cv2.line(img, (margem_x, margem_y), (margem_x, altura - margem_y), (90, 90, 90), 1)
    for graus in range(int(angulos[0]), int(angulos[-1]) + 1, 15):
        gx = int(margem_x + (graus - angulos[0]) / (angulos[-1] - angulos[0]) * (largura - margem_x - 20))
        cv2.line(img, (gx, altura - margem_y), (gx, altura - margem_y + 5), (90, 90, 90), 1)
        cv2.putText(img, f"{graus}", (gx - 12, altura - margem_y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 60, 60), 1, cv2.LINE_AA)
    cv2.polylines(img, [np.int32(np.column_stack([x, y]))], False, (200, 90, 20), 2, cv2.LINE_AA)
    i = int(np.argmax(energia))
    cv2.circle(img, (int(x[i]), int(y[i])), 6, (40, 40, 230), -1)
    cv2.putText(img, f"pico: correcao de {pico:.1f} graus", (int(x[i]) + 10, int(y[i]) + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 230), 1, cv2.LINE_AA)
    cv2.putText(img, "energia do espectro por angulo (graus)", (margem_x, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
    return img


def _normalizar(imagem: np.ndarray) -> np.ndarray:
    baixo, alto = np.percentile(imagem, (1, 99))
    return (np.clip((imagem - baixo) / max(alto - baixo, 1e-9), 0, 1) * 255).astype(np.uint8)


def gerar_figuras(imagem: np.ndarray) -> dict:
    # 1. Página torta × reta e seus espectros.
    torta = _binarizar(_girar(imagem, 12))
    reta = _binarizar(imagem)
    correcao, angulos, energia = medir_inclinacao_fft(torta)
    cv2.imwrite(str(PASTA_SAIDA / "espectro_pagina.png"), _juntar([
        _rotular(_quadrado(torta), "Pagina girada 12 graus"),
        _rotular(_quadrado(_espectro_com_reta(torta, correcao)), "Espectro: faixa girada"),
        _rotular(_quadrado(reta), "Pagina reta"),
        _rotular(_quadrado(_espectro_com_reta(reta, medir_inclinacao_fft(reta)[0])), "Espectro: faixa vertical"),
    ]))
    # 2. Curva de energia por ângulo.
    cv2.imwrite(str(PASTA_SAIDA / "energia_por_angulo.png"), _grafico(angulos, energia, correcao))

    # 3. Magnitude × fase: reconstrução só com uma delas.
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY).astype(np.float32)
    espectro = np.fft.fft2(cinza)
    so_magnitude = np.real(np.fft.ifft2(np.abs(espectro)))
    so_fase = np.real(np.fft.ifft2(np.exp(1j * np.angle(espectro))))
    deslocada = np.roll(cinza, (150, 200), axis=(0, 1))
    mesma_magnitude = np.allclose(np.abs(np.fft.fft2(deslocada)), np.abs(espectro), rtol=1e-3, atol=1e-2 * np.abs(espectro).max())
    cv2.imwrite(str(PASTA_SAIDA / "magnitude_e_fase.png"), _juntar([
        _rotular(_quadrado(cinza.astype(np.uint8)), "Original"),
        _rotular(_quadrado(_normalizar(np.fft.fftshift(np.log1p(np.abs(so_magnitude))))), "So magnitude (fase = 0)"),
        _rotular(_quadrado(_normalizar(so_fase)), "So fase (magnitude = 1)"),
    ]))

    # 4. Passa-baixa × passa-alta (o que cada faixa de frequência carrega).
    foto = cv2.cvtColor(degradar(imagem, semente=1), cv2.COLOR_BGR2GRAY).astype(np.float32)
    altura, largura = foto.shape
    v, u = np.meshgrid(np.fft.fftfreq(altura), np.fft.fftfreq(largura), indexing="ij")
    baixa = np.exp(-(u ** 2 + v ** 2) / (2 * 0.01 ** 2))
    transformada = np.fft.fft2(foto)
    passa_baixa = np.real(np.fft.ifft2(transformada * baixa))
    passa_alta = np.real(np.fft.ifft2(transformada * (1 - baixa)))
    cv2.imwrite(str(PASTA_SAIDA / "baixa_e_alta_frequencia.png"), _juntar([
        _rotular(_quadrado(foto.astype(np.uint8)), "Foto simulada"),
        _rotular(_quadrado(_normalizar(passa_baixa)), "Baixas: luz e sombra"),
        _rotular(_quadrado(_normalizar(passa_alta)), "Altas: letras e ruido"),
    ]))

    # 5. Filtro homomórfico × divisão pelo fundo.
    filtrada, filtro = filtro_homomorfico(foto.astype(np.uint8))
    # O filtro só muda perto do centro; amplia o quarto central para o "buraco" aparecer.
    lado_y, lado_x = filtro.shape[0] // 8, filtro.shape[1] // 8
    centro = filtro[altura // 2 - lado_y: altura // 2 + lado_y, largura // 2 - lado_x: largura // 2 + lado_x]
    cv2.imwrite(str(PASTA_SAIDA / "homomorfico.png"), _juntar([
        _rotular(_quadrado(foto.astype(np.uint8)), "Foto simulada"),
        _rotular(_quadrado(cv2.resize(_normalizar(centro), (largura, altura), interpolation=cv2.INTER_CUBIC)), "Filtro H, centro (escuro = atenua)"),
        _rotular(_quadrado(filtrada), "Homomorfico (FFT)"),
        _rotular(_quadrado(_normalizar_iluminacao(foto.astype(np.uint8))), "Divisao pelo fundo (app)"),
    ]))
    return {"magnitude_invariante_a_deslocamento": bool(mesma_magnitude)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sem-ocr", action="store_true", help="pula a comparação de iluminação pelo OCR (a parte mais lenta)")
    parser.add_argument("--so-figuras", action="store_true", help="só refaz as figuras, sem medir nada nem alterar resultados.json")
    args = parser.parse_args()
    baixar_funsd()
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    anotacoes = sorted((PASTA_TESTE / "annotations").glob("*.json"))
    if args.so_figuras:
        gerar_figuras(cv2.imread(str(PASTA_TESTE / "images" / f"{anotacoes[0].stem}.png")))
        return
    imagens = [cv2.imread(str(PASTA_TESTE / "images" / f"{a.stem}.png")) for a in anotacoes]

    resultados = {"inclinacao": avaliar_inclinacao(imagens)}
    print("1. Inclinação (50 páginas de teste; o erro inclui a inclinação própria do scan, de até ~2°)")
    for cenario, metodos in resultados["inclinacao"].items():
        print(f"\n  {cenario}")
        for metodo, r in metodos.items():
            print(f"    {metodo:34s} erro médio {r['erro_medio']:5.2f}°  mediana {r['erro_mediano']:.2f}°  "
                  f"máx {r['erro_maximo']:5.2f}°  até 1°: {100 * r['fracao_ate_1_grau']:3.0f}%  {r['ms_por_pagina']:4.0f} ms")

    resultados["confianca"] = avaliar_confianca(imagens)
    print("\n2. Destaque do pico (limiar", DESTAQUE_MINIMO, ")")
    for chave, valor in resultados["confianca"].items():
        print(f"  {chave}: {valor}")

    if not args.sem_ocr:
        resultados["ocr_paginas_giradas_15_a_40_graus"] = avaliar_ocr_paginas_tortas(anotacoes)
        print("\n1b. OCR em páginas giradas de 15° a 40° — F1")
        for metodo, f1 in resultados["ocr_paginas_giradas_15_a_40_graus"].items():
            print(f"  {metodo:24s} {100 * f1:5.1f}%")
        resultados["iluminacao_f1_ocr"] = avaliar_iluminacao(anotacoes)
        print("\n3. Iluminação — F1 do OCR")
        for condicao, variantes in resultados["iluminacao_f1_ocr"].items():
            for nome, f1 in variantes.items():
                print(f"  {condicao:14s} {nome:36s} {100 * f1:5.1f}%")

    resultados["figuras"] = gerar_figuras(imagens[0])
    (PASTA_SAIDA / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFiguras e resultados em {PASTA_SAIDA}")


if __name__ == "__main__":
    main()
