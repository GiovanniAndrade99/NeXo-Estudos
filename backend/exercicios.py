"""Exercícios de revisão gerados a partir do próprio texto da página.

Cada exercício de lacuna usa uma das frases mais representativas do texto (as mesmas
escolhidas pelo resumo extrativo) e esconde o termo mais importante dela:
1. um termo característico da matéria identificada, se a frase tiver um;
2. senão, a palavra relevante (sem palavras vazias) mais frequente no texto todo.
As respostas ficam num gabarito separado, para o aluno conferir depois.
"""
from __future__ import annotations

import re
from collections import Counter

from .resumo import _VAZIAS_SEM_ACENTO, _palavras, _sem_acentos, resumir

LACUNA = "______"
MAXIMO_LACUNAS = 2


def _palavras_com_posicao(frase: str) -> list[re.Match]:
    return list(re.finditer(r"[A-Za-zÀ-ÿ0-9]+(?:-[A-Za-zÀ-ÿ0-9]+)*", frase))


def _termo_central(frase: str, frequencia: Counter, termos_materia: set[str]) -> re.Match | None:
    candidatas = []
    for indice, palavra in enumerate(_palavras_com_posicao(frase)):
        normal = _sem_acentos(palavra.group())
        sigla = palavra.group().isupper() and len(palavra.group()) >= 2
        if indice == 0 or normal in _VAZIAS_SEM_ACENTO or (len(normal) < 5 and not sigla) or normal.isdigit():
            continue  # a primeira palavra da frase dá pista demais e deixa a lacuna sem contexto
        nota = (3 if normal in termos_materia else 0) + frequencia[normal] + len(normal) / 20
        candidatas.append((nota, -indice, palavra))
    return max(candidatas, key=lambda c: (c[0], c[1]))[2] if candidatas else None


def gerar_lacunas(texto: str, termos_materia: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    """Devolve (exercícios de lacuna, respostas), na mesma ordem."""
    frases = resumir(texto, termos_materia, max_frases=MAXIMO_LACUNAS, limite=600)
    frequencia = Counter(p for frase in frases for p in _palavras(frase))
    frequencia.update(_palavras(texto))
    materia = {p for termo in termos_materia for p in _palavras(termo)}
    exercicios, respostas = [], []
    for frase in frases:
        termo = _termo_central(frase, frequencia, materia)
        if not termo:
            continue
        com_lacuna = frase[:termo.start()] + LACUNA + frase[termo.end():]
        exercicios.append(f"Complete a lacuna: “{com_lacuna}”")
        respostas.append(termo.group())
    return exercicios, respostas


def _radicais(texto: str) -> set[str]:
    # Radical simples (5 primeiras letras): "classe" e "classes", "encapsula" e "encapsulamento" se encontram.
    return {p[:5] for p in _palavras(texto)}


def perguntas_mais_relacionadas(texto: str, perguntas: list[str], quantidade: int) -> list[str]:
    """Ordena as perguntas da matéria pelo vocabulário em comum com a página (empate: ordem original)."""
    do_texto = _radicais(texto)
    ordem = sorted(range(len(perguntas)), key=lambda i: (-len(_radicais(perguntas[i]) & do_texto), i))
    return [perguntas[i] for i in ordem[:quantidade]]


def montar_exercicios(texto: str, disciplina: dict, perguntas_da_materia: list[str]) -> tuple[list[str], list[str]]:
    """Lacunas tiradas do texto + a pergunta discursiva da matéria mais ligada à página, até 3 exercícios.

    O gabarito tem uma resposta por exercício (as perguntas discursivas ficam como "Resposta pessoal").
    """
    lacunas, respostas = gerar_lacunas(texto, tuple(disciplina.get("palavras_chave", ())))
    discursivas = perguntas_mais_relacionadas(texto, perguntas_da_materia, 3 - len(lacunas))
    return lacunas + discursivas, respostas + ["Resposta pessoal."] * len(discursivas)
