"""Monta o dataset de treino do classificador de matérias a partir da Wikipédia em português.

Para cada matéria do Assistente de Estudos, baixa a introdução dos artigos de algumas
categorias da Wikipédia (API pública do MediaWiki) e divide cada introdução em trechos
de até 120 palavras, parecidos com o texto de uma página de apostila.

Saída: datasets/materias_wikipedia.jsonl, uma linha por trecho:
    {"materia": "biologia", "artigo": "Mitocôndria", "texto": "..."}

Licença do conteúdo: CC BY-SA 4.0 (Wikipédia). Ver datasets/README.md.

Uso: python tools/montar_dataset_materias.py
"""
from __future__ import annotations

import json
import re
import time
from itertools import zip_longest
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "datasets" / "materias_wikipedia.jsonl"
API = "https://pt.wikipedia.org/w/api.php"
CABECALHOS = {"User-Agent": "NeXoEstudos/1.0 (projeto academico; classificador de materias)"}
MAXIMO_ARTIGOS_POR_MATERIA = 70
PALAVRAS_POR_TRECHO = 120

# Categorias da Wikipédia usadas para cada matéria (chaves iguais às de DISCIPLINAS).
CATEGORIAS = {
    "algoritmos": ["Algoritmos", "Estruturas de dados", "Algoritmos de ordenação", "Teoria dos grafos"],
    "banco_de_dados": ["Bancos de dados", "SQL", "Sistemas de gerenciamento de banco de dados"],
    "redes": ["Redes de computadores", "Protocolos Internet", "Protocolos de rede"],
    "ia": ["Inteligência artificial", "Aprendizado de máquina", "Redes neurais artificiais"],
    "matematica": ["Álgebra linear", "Matrizes", "Geometria analítica"],
    "programacao": ["Programação orientada a objetos", "Paradigmas de programação", "Estruturas de controle", "Tipos de dados", "Linguagens de programação"],
    "engenharia_software": ["Engenharia de software", "Desenvolvimento de software", "Metodologias de desenvolvimento de software"],
    "seguranca": ["Segurança da informação", "Criptografia", "Segurança de computadores"],
    "sistemas_operacionais": ["Sistemas operativos", "Núcleos de sistemas operativos", "Gerenciamento de memória"],
    "geografia": ["Cartografia", "Geomorfologia", "Climatologia", "Geografia humana"],
    "portugues": ["Gramática da língua portuguesa", "Figuras de linguagem", "Sintaxe", "Morfologia linguística"],
    "literatura": ["Movimentos literários", "Gêneros literários", "Teoria da literatura", "Literatura do Brasil"],
    "biologia": ["Biologia celular", "Genética", "Organelos", "Biologia molecular"],
    "quimica": ["Ligações químicas", "Reações químicas", "Química geral", "Tabela periódica"],
    "historia": ["Brasil Colônia", "Império do Brasil", "História do Brasil", "República Velha"],
    "fisica": ["Mecânica clássica", "Termodinâmica", "Eletromagnetismo", "Óptica"],
}


def pedir(cliente: httpx.Client, params: dict) -> dict:
    """GET na API respeitando o limite de velocidade da Wikipédia (espera e tenta de novo no erro 429)."""
    for tentativa in range(6):
        resposta = cliente.get(API, params={**params, "maxlag": 5})
        if resposta.status_code == 429 or "maxlag" in resposta.text[:200]:
            time.sleep(int(resposta.headers.get("Retry-After", 0)) or 5 * (tentativa + 1))
            continue
        resposta.raise_for_status()
        time.sleep(1)  # espaçamento entre pedidos, como pede a política da API
        return resposta.json()
    raise RuntimeError("A Wikipédia continuou limitando os pedidos; tente mais tarde.")


def membros(cliente: httpx.Client, categoria: str) -> list[str]:
    dados = pedir(cliente, {
        "action": "query", "list": "categorymembers", "cmtitle": f"Categoria:{categoria}",
        "cmnamespace": 0, "cmtype": "page", "cmlimit": 100, "format": "json",
    })
    return [m["title"] for m in dados["query"]["categorymembers"]]


def introducoes(cliente: httpx.Client, titulos: list[str]) -> dict[str, str]:
    textos = {}
    for inicio in range(0, len(titulos), 20):  # a API devolve até 20 introduções por pedido
        dados = pedir(cliente, {
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "exlimit": 20,
            "titles": "|".join(titulos[inicio:inicio + 20]), "format": "json", "redirects": 1,
        })
        for pagina in dados["query"]["pages"].values():
            if pagina.get("extract"):
                textos[pagina["title"]] = pagina["extract"]
    return textos


def trechos(texto: str) -> list[str]:
    palavras = re.sub(r"\s+", " ", texto).strip().split(" ")
    pedacos = [" ".join(palavras[i:i + PALAVRAS_POR_TRECHO]) for i in range(0, len(palavras), PALAVRAS_POR_TRECHO)]
    return [p for p in pedacos if len(p.split()) >= 40]


def main() -> None:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    vistos, linhas = set(), []
    with httpx.Client(headers=CABECALHOS, timeout=30) as cliente:
        for materia, categorias in CATEGORIAS.items():
            por_categoria = []
            for categoria in categorias:
                try:
                    novos = membros(cliente, categoria)
                except (httpx.HTTPError, KeyError, RuntimeError):
                    novos = []
                print(f"  {materia:22s} Categoria:{categoria}: {len(novos)} artigos")
                por_categoria.append([t for t in novos if t not in vistos])
            # Intercala as categorias (1º de cada, depois 2º de cada...): nenhuma domina a matéria.
            # Sem isso, a primeira categoria (ex.: a lista alfabética de linguagens) enchia o limite sozinha.
            titulos = []
            for rodada in zip_longest(*por_categoria):
                titulos += [t for t in rodada if t and t not in titulos]
            titulos = titulos[:MAXIMO_ARTIGOS_POR_MATERIA]
            vistos.update(titulos)  # um artigo pertence a uma só matéria
            total = 0
            for titulo, texto in introducoes(cliente, titulos).items():
                for trecho in trechos(texto):
                    linhas.append({"materia": materia, "artigo": titulo, "texto": trecho})
                    total += 1
            print(f"{materia}: {total} trechos")
    with SAIDA.open("w", encoding="utf-8") as arquivo:
        for linha in linhas:
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")
    print(f"\n{len(linhas)} trechos gravados em {SAIDA}")


if __name__ == "__main__":
    main()
