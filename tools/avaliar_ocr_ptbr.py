"""Avalia OCR no conjunto BRESSAY sem copiar os dados para o repositório.

Baixe e extraia o BRESSAY por conta própria; veja docs/AVALIACAO_PTBR.md.
O script usa somente a partição indicada (por padrão, test) e compara Tesseract
direto com o pipeline do NeXo em nível de página.
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import statistics
import sys
import unicodedata
from pathlib import Path

import cv2
import pytesseract

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import backend.processamento as processamento  # noqa: E402
from backend.processamento import IDIOMAS_OCR, _configurar_tesseract  # noqa: E402

IGNORAR = re.compile(r"(?:##\s*@@\?\?\?@@\s*##|\$\$\s*@@\?\?\?@@\s*\$\$|@@\?\?\?@@|##\s*--xxx--\s*##|\$\$\s*--xxx--\s*\$\$|--xxx--)", re.I)
MARCADORES = re.compile(r"(?:##|\$\$|--)")


def normalizar(texto: str) -> str:
    texto = IGNORAR.sub(" ", texto or "")
    texto = MARCADORES.sub("", texto)
    texto = unicodedata.normalize("NFC", texto).casefold()
    return " ".join(texto.split())


def distancia(a: str, b: str) -> int:
    """Distância de Levenshtein com memória O(min(len(a), len(b)))."""
    if len(a) < len(b):
        a, b = b, a
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(atual[-1] + 1, anterior[j] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def cer(reconhecido: str, referencia: str) -> float:
    referencia = normalizar(referencia)
    return distancia(normalizar(reconhecido), referencia) / max(1, len(referencia))


def wer(reconhecido: str, referencia: str) -> float:
    a, b = normalizar(reconhecido).split(), normalizar(referencia).split()
    if not b:
        return 0.0 if not a else 1.0
    anterior = list(range(len(b) + 1))
    for i, palavra_a in enumerate(a, 1):
        atual = [i]
        for j, palavra_b in enumerate(b, 1):
            atual.append(min(atual[-1] + 1, anterior[j] + 1, anterior[j - 1] + (palavra_a != palavra_b)))
        anterior = atual
    return anterior[-1] / len(b)


def intervalo_bootstrap(valores: list[float], repeticoes: int = 2000) -> tuple[float, float]:
    rng = random.Random(20261019)
    medias = sorted(statistics.mean(rng.choices(valores, k=len(valores))) for _ in range(repeticoes))
    return medias[int(0.025 * repeticoes)], medias[min(repeticoes - 1, int(0.975 * repeticoes))]


def _achar_arquivo(pasta: Path, nome: str, extensoes: tuple[str, ...]) -> Path | None:
    nome = Path(nome.strip()).stem
    for extensao in extensoes:
        candidato = pasta / f"{nome}{extensao}"
        if candidato.is_file():
            return candidato
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    fonte = parser.add_mutually_exclusive_group(required=True)
    fonte.add_argument("--dataset-root", type=Path, help="Pasta raiz extraída do BRESSAY")
    fonte.add_argument("--manifest-csv", type=Path, help="Manifesto local com colunas arquivo_imagem e arquivo_transcricao")
    parser.add_argument("--split", choices=("test", "validation", "training"), default="test")
    parser.add_argument("--limit", type=int, default=None, help="Avalia somente as primeiras N páginas (piloto)")
    parser.add_argument("--languages", default=IDIOMAS_OCR, help="Idiomas Tesseract; padrão: por+eng")
    parser.add_argument("--output", type=Path, default=None, help="CSV de saída; padrão: <dataset-root>/resultados_nexo.csv")
    args = parser.parse_args()

    if args.dataset_root:
        raiz = args.dataset_root.resolve()
        conjunto = raiz / "sets" / f"{args.split}.txt"
        pasta_paginas = raiz / "data" / "pages"
        if not conjunto.is_file() or not pasta_paginas.is_dir():
            parser.error("Estrutura esperada: <raiz>/sets/<split>.txt e <raiz>/data/pages/")
        nomes = [linha.strip() for linha in conjunto.read_text(encoding="utf-8-sig").splitlines() if linha.strip()]
        pares = []
        for nome in nomes:
            imagem = _achar_arquivo(pasta_paginas, nome, (".png", ".jpg", ".jpeg"))
            referencia = _achar_arquivo(pasta_paginas, nome, (".txt",))
            pares.append((Path(nome).stem, imagem, referencia))
        raiz_saida = raiz
    else:
        manifesto = args.manifest_csv.resolve()
        if not manifesto.is_file():
            parser.error("Manifesto CSV não encontrado.")
        with manifesto.open(encoding="utf-8-sig", newline="") as arquivo:
            leitor = csv.DictReader(arquivo)
            obrigatorias = {"arquivo_imagem", "arquivo_transcricao", "split"}
            if not obrigatorias.issubset(leitor.fieldnames or []):
                parser.error("O manifesto precisa ter as colunas arquivo_imagem, arquivo_transcricao e split.")
            pares = []
            for indice, linha in enumerate(leitor, 1):
                if (linha.get("split") or "").strip().lower() != args.split:
                    continue
                base = manifesto.parent
                imagem = (base / linha["arquivo_imagem"]).resolve() if linha.get("arquivo_imagem") else None
                referencia = (base / linha["arquivo_transcricao"]).resolve() if linha.get("arquivo_transcricao") else None
                identificador = (linha.get("id_anonimo") or f"pagina-{indice}").strip()
                pares.append((identificador, imagem, referencia))
        raiz_saida = manifesto.parent
    if args.limit:
        pares = pares[:args.limit]
    if not pares:
        parser.error("A partição/manifesto não contém páginas para o split solicitado.")

    config = _configurar_tesseract()
    processamento.IDIOMAS_OCR = args.languages
    resultados = []
    for numero, (identificador, imagem_path, texto_path) in enumerate(pares, 1):
        if not imagem_path or not texto_path or not imagem_path.is_file() or not texto_path.is_file():
            print(f"Ignorada: imagem ou transcrição ausente para {identificador}", file=sys.stderr)
            continue
        imagem = cv2.imread(str(imagem_path), cv2.IMREAD_COLOR)
        if imagem is None:
            print(f"Ignorada: não foi possível abrir {imagem_path.name}", file=sys.stderr)
            continue
        referencia = texto_path.read_text(encoding="utf-8-sig")
        cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
        direto = pytesseract.image_to_string(cinza, lang=args.languages, config=f"--psm 6 {config}".strip()).strip()
        pipeline = processamento.processar(imagem)
        resultados.append({
            "pagina": identificador,
            "cer_direto": cer(direto, referencia), "wer_direto": wer(direto, referencia),
            "cer_pipeline": cer(pipeline.texto, referencia), "wer_pipeline": wer(pipeline.texto, referencia),
            "palavras_referencia": len(normalizar(referencia).split()),
        })
        print(f"[{numero}/{len(pares)}] {identificador}: CER direto {resultados[-1]['cer_direto']:.3f}; pipeline {resultados[-1]['cer_pipeline']:.3f}")

    if not resultados:
        parser.error("Nenhuma página pôde ser avaliada; confira os nomes e extensões dos arquivos.")
    saida = args.output or raiz_saida / "resultados_nexo.csv"
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=resultados[0].keys())
        escritor.writeheader()
        escritor.writerows(resultados)
    recorte = args.split if args.dataset_root else f"manifesto/{args.split}"
    print(f"\nPáginas avaliadas: {len(resultados)} (partição {recorte})")
    for campo in ("cer_direto", "wer_direto", "cer_pipeline", "wer_pipeline"):
        valores = [r[campo] for r in resultados]
        baixo, alto = intervalo_bootstrap(valores)
        print(f"{campo}: média {statistics.mean(valores):.4f}; IC95% bootstrap [{baixo:.4f}, {alto:.4f}]")
    for metrica in ("cer", "wer"):
        diferencas = [r[f"{metrica}_pipeline"] - r[f"{metrica}_direto"] for r in resultados]
        baixo, alto = intervalo_bootstrap(diferencas)
        print(f"diferença pareada {metrica} (pipeline - direto): {statistics.mean(diferencas):+.4f}; IC95% [{baixo:+.4f}, {alto:+.4f}]")
    print(f"Resultados por página: {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
