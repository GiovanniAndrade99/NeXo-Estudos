"""Resumo extrativo do texto reconhecido pelo OCR.

Técnica clássica de Processamento de Linguagem Natural (Luhn, 1958; base do TF-IDF):
as frases que concentram as palavras mais frequentes e significativas do texto são as
que melhor o representam. Passos:

1. Limpeza: descarta linhas de autor, números de página e ruído típico do OCR.
2. Reconstrução das frases: o OCR quebra o texto por linha da página, não por frase;
   linhas são juntadas até um ponto final, e títulos curtos ficam de fora.
3. Pontuação: cada palavra relevante (sem palavras vazias como "de", "que", "o") vale
   a sua frequência no texto; termos da matéria identificada recebem peso extra. A nota
   da frase é a média dos pesos das suas palavras, com penalidade para frases muito
   curtas ou muito longas.
4. Seleção: as frases de maior nota que cabem no limite, na ordem original do texto.

Não usa modelo treinado nem serviço externo: o resultado é determinístico e explicável.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

PALAVRAS_VAZIAS = set("""
a ao aos as à às até com como da das de dela dele deles do dos e é ela elas ele eles em entre era essa essas esse
esses esta está estão estas este estes eu foi foram há isso isto já la lá lhe mais mas me mesmo meu minha muito na
nas não nem no nos nós num numa o os ou para pela pelas pelo pelos por pois qual quando que quem se sem ser seu seus
só sua suas também te tem têm tu um uma umas uns você vocês sobre após cada pode podem ser são sendo foi assim onde
the of and to in is for on that with as by an are be this it from or at
""".split())
PADRAO_AUTOR = re.compile(r"^\s*(professor|professora|prof\.?|autor|autora|elaborado por|revisado por|by)\b", re.I)
PADRAO_PAGINA = re.compile(r"^\s*(p[aá]g(ina)?\.?\s*)?\d{1,4}\s*(/\s*\d{1,4})?\s*$", re.I)
FIM_DE_FRASE = re.compile(r"[.!?…:;]$")


def _sem_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def _palavras(frase: str) -> list[str]:
    return [p for p in re.findall(r"[a-z0-9]+", _sem_acentos(frase)) if len(p) >= 3 and p not in _VAZIAS_SEM_ACENTO]


_VAZIAS_SEM_ACENTO = {_sem_acentos(v) for v in PALAVRAS_VAZIAS}


def _linha_util(linha: str) -> bool:
    if PADRAO_AUTOR.match(linha) or PADRAO_PAGINA.match(linha):
        return False
    letras = sum(c.isalpha() for c in linha)
    # Linhas em que menos da metade dos caracteres são letras costumam ser ruído do OCR.
    return letras >= 4 and letras / max(1, len(linha.replace(" ", ""))) >= 0.6


def _e_titulo(linha: str) -> bool:
    # Linha terminada em hífen continua na próxima: é começo de frase, não título.
    return len(linha.split()) <= 6 and not FIM_DE_FRASE.search(linha) and not linha.endswith("-")


def extrair_frases(texto: str) -> list[str]:
    """Reconstrói as frases a partir das linhas do OCR, sem títulos, autor e ruído."""
    linhas = [re.sub(r"\s+", " ", l).strip() for l in (texto or "").splitlines()]
    linhas = [l for l in linhas if l and _linha_util(l)]
    blocos, atual = [], []
    for linha in linhas:
        if not atual and _e_titulo(linha):
            continue  # título ou rótulo solto: não é frase do conteúdo
        # Hifenização do fim de linha ("proces-" + "samento").
        if atual and atual[-1].endswith("-") and linha[:1].islower():
            atual[-1] = atual[-1][:-1] + linha
        else:
            atual.append(linha)
        if FIM_DE_FRASE.search(linha):
            blocos.append(" ".join(atual))
            atual = []
    if atual and len(" ".join(atual).split()) >= 5:
        blocos.append(" ".join(atual))
    frases = []
    for bloco in blocos:
        for frase in re.split(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9])", bloco):
            frase = frase.strip(" :;")
            if len(frase.split()) >= 5:
                frases.append(frase if FIM_DE_FRASE.search(frase) else frase + ".")
    return frases


def resumir(texto: str, termos_destaque: tuple[str, ...] = (), max_frases: int = 3, limite: int = 280) -> list[str]:
    """Escolhe as frases mais representativas do texto, na ordem em que aparecem."""
    frases = extrair_frases(texto)
    if not frases:
        return []
    palavras_por_frase = [_palavras(f) for f in frases]
    frequencia = Counter(p for palavras in palavras_por_frase for p in set(palavras))
    destaque = {p for termo in termos_destaque for p in _palavras(termo)}

    def nota(indice: int) -> float:
        palavras = palavras_por_frase[indice]
        if not palavras:
            return 0.0
        peso = sum(frequencia[p] + (2 if p in destaque else 0) for p in palavras) / len(palavras)
        tamanho = len(frases[indice].split())
        # Frases de 8 a 35 palavras tendem a ser completas e informativas.
        penalidade = 1.0 if 8 <= tamanho <= 35 else 0.75
        return peso * penalidade * math.log(1 + len(set(palavras)))

    ordem = sorted(range(len(frases)), key=lambda i: (-nota(i), i))
    escolhidas, total = [], 0
    for indice in ordem:
        tamanho = len(frases[indice]) + (1 if escolhidas else 0)
        if len(escolhidas) < max_frases and total + tamanho <= limite:
            escolhidas.append(indice)
            total += tamanho
    return [frases[i] for i in sorted(escolhidas)]
