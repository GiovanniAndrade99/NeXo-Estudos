"""Avalia o ganho do pré-processamento no OCR usando o dataset público FUNSD.

Para cada imagem do conjunto de teste do FUNSD (50 formulários digitalizados com o
texto de cada palavra anotado manualmente), o OCR é executado:

  * sem pré-processamento: Tesseract direto na imagem;
  * com o pipeline do projeto: a mesma função backend.processamento.processar() usada pela API.

As duas situações são testadas nos scans originais e em versões degradadas para simular
uma foto de celular (iluminação desigual, tom amarelado, ruído e inclinação).

A métrica compara o multiconjunto de palavras reconhecidas com o das palavras anotadas
(precisão, revocação e F1), sem depender da ordem de leitura.

Uso (na raiz do projeto, com o ambiente virtual ativo):
    python tools/avaliar_ocr.py            # baixa o FUNSD se necessário e avalia as 50 imagens
    python tools/avaliar_ocr.py --limite 10
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import cv2
import numpy as np
import pytesseract

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from backend.processamento import IDIOMAS_OCR, _configurar_tesseract, processar  # noqa: E402

URL_FUNSD = "https://guillaumejaume.github.io/FUNSD/dataset.zip"
PASTA_DATASET = RAIZ / "datasets" / "funsd"
PASTA_TESTE = PASTA_DATASET / "dataset" / "testing_data"
PASTA_SAIDA = RAIZ / "docs" / "avaliacao"


def baixar_funsd() -> None:
    if PASTA_TESTE.exists():
        return
    print(f"Baixando o FUNSD de {URL_FUNSD} ...")
    PASTA_DATASET.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL_FUNSD, timeout=120) as resposta:
        dados = resposta.read()
    with zipfile.ZipFile(io.BytesIO(dados)) as arquivo:
        arquivo.extractall(PASTA_DATASET)


def palavras(texto: str) -> list[str]:
    """Minúsculas, sem acentos, só letras e números: compara palavras sem ruído de pontuação."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", texto)


def texto_anotado(caminho_json: Path) -> list[str]:
    dados = json.loads(caminho_json.read_text(encoding="utf-8"))
    return [p for bloco in dados["form"] for w in bloco["words"] for p in palavras(w["text"])]


def comparar(reconhecidas: list[str], esperadas: list[str]) -> tuple[float, float, float]:
    acertos = sum((Counter(reconhecidas) & Counter(esperadas)).values())
    precisao = acertos / len(reconhecidas) if reconhecidas else 0.0
    revocacao = acertos / len(esperadas) if esperadas else 0.0
    f1 = 2 * precisao * revocacao / (precisao + revocacao) if precisao + revocacao else 0.0
    return precisao, revocacao, f1


def degradar(imagem: np.ndarray, semente: int) -> np.ndarray:
    """Simula uma foto de celular: tom amarelado, sombra num canto, ruído de sensor e inclinação."""
    rng = np.random.default_rng(semente)
    altura, largura = imagem.shape[:2]
    foto = imagem.astype(np.float32) * np.array([0.80, 0.93, 1.0], np.float32)  # BGR: papel amarelado
    yy, xx = np.mgrid[0:altura, 0:largura].astype(np.float32)
    canto_x, canto_y = rng.choice([0.0, 1.0], size=2)
    distancia = np.hypot(np.abs(xx / largura - canto_x), np.abs(yy / altura - canto_y)) / np.sqrt(2)
    foto *= (0.45 + 0.6 * distancia)[..., None]
    foto += rng.normal(0, 7, foto.shape)
    foto = np.clip(foto, 0, 255).astype(np.uint8)
    angulo = float(rng.uniform(3, 6) * rng.choice([-1, 1]))
    matriz = cv2.getRotationMatrix2D((largura / 2, altura / 2), angulo, 1.0)
    return cv2.warpAffine(foto, matriz, (largura, altura), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def ocr_direto(imagem: np.ndarray) -> str:
    rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)
    config = f"--psm 6 {_configurar_tesseract()}".strip()
    return pytesseract.image_to_string(rgb, lang=IDIOMAS_OCR, config=config)


def ocr_pipeline(imagem: np.ndarray) -> tuple[str, float]:
    with redirect_stdout(io.StringIO()):
        resultado = processar(imagem)
    return resultado.texto, resultado.inclinacao_corrigida_graus


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limite", type=int, default=0, help="avaliar só as N primeiras imagens")
    args = parser.parse_args()

    baixar_funsd()
    anotacoes = sorted((PASTA_TESTE / "annotations").glob("*.json"))
    if args.limite:
        anotacoes = anotacoes[: args.limite]
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)

    linhas = []
    inicio = time.time()
    for n, anotacao in enumerate(anotacoes, 1):
        imagem = cv2.imread(str(PASTA_TESTE / "images" / f"{anotacao.stem}.png"))
        esperadas = texto_anotado(anotacao)
        for condicao, entrada in (("scan original", imagem), ("foto simulada", degradar(imagem, semente=n))):
            texto_pipeline, angulo = ocr_pipeline(entrada)
            for metodo, texto in (("sem pré-processamento", ocr_direto(entrada)), ("pipeline do projeto", texto_pipeline)):
                precisao, revocacao, f1 = comparar(palavras(texto), esperadas)
                linhas.append({
                    "imagem": anotacao.stem, "condicao": condicao, "metodo": metodo,
                    "palavras_anotadas": len(esperadas), "precisao": round(precisao, 4),
                    "revocacao": round(revocacao, 4), "f1": round(f1, 4),
                    "angulo_corrigido": angulo if metodo == "pipeline do projeto" else "",
                })
        print(f"[{n}/{len(anotacoes)}] {anotacao.stem}  ({time.time() - inicio:.0f}s)")

    with (PASTA_SAIDA / "resultados.csv").open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)

    print(f"\nFUNSD (teste), {len(anotacoes)} imagens — médias por imagem\n")
    print("| Condição | Método | Precisão | Revocação | F1 |")
    print("|---|---|---|---|---|")
    for condicao in ("scan original", "foto simulada"):
        for metodo in ("sem pré-processamento", "pipeline do projeto"):
            grupo = [l for l in linhas if l["condicao"] == condicao and l["metodo"] == metodo]
            media = {k: 100 * sum(l[k] for l in grupo) / len(grupo) for k in ("precisao", "revocacao", "f1")}
            print(f"| {condicao} | {metodo} | {media['precisao']:.1f}% | {media['revocacao']:.1f}% | {media['f1']:.1f}% |")

    # Figura de exemplo para o relatório: foto simulada ao lado da saída do pipeline.
    exemplo = cv2.imread(str(PASTA_TESTE / "images" / f"{anotacoes[0].stem}.png"))
    degradada = degradar(exemplo, semente=1)
    with redirect_stdout(io.StringIO()):
        tratada = cv2.cvtColor(processar(degradada).tratada, cv2.COLOR_GRAY2BGR)
    # O pipeline amplia imagens pequenas; volta ao tamanho da entrada para montar a figura lado a lado.
    tratada = cv2.resize(tratada, (degradada.shape[1], degradada.shape[0]), interpolation=cv2.INTER_AREA)
    separador = np.full((degradada.shape[0], 12, 3), 255, np.uint8)
    cv2.imwrite(str(PASTA_SAIDA / "exemplo_foto_simulada.webp"), np.hstack([degradada, separador, tratada]),
                [cv2.IMWRITE_WEBP_QUALITY, 80])
    print(f"\nResultados por imagem: {PASTA_SAIDA / 'resultados.csv'}")


if __name__ == "__main__":
    main()
