"""Resume dados de sessão do protocolo sem incluir linhas individuais na saída."""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from pathlib import Path


def numero(linha: dict[str, str], campo: str) -> float | None:
    try:
        texto = (linha.get(campo) or "").strip()
        return float(texto) if texto else None
    except ValueError:
        return None


def media_ic(valores: list[float]) -> dict | None:
    if not valores:
        return None
    rng = random.Random(20261019)
    medias = sorted(statistics.mean(rng.choices(valores, k=len(valores))) for _ in range(3000))
    return {
        "n": len(valores),
        "media": round(statistics.mean(valores), 3),
        "ic95_bootstrap": [round(medias[74], 3), round(medias[2924], 3)],
    }


def pontuacao_sus(linha: dict[str, str]) -> float | None:
    respostas = [numero(linha, f"sus_{i}") for i in range(1, 11)]
    if any(valor is None or valor < 1 or valor > 5 for valor in respostas):
        return None
    total = sum((valor - 1) if i % 2 else (5 - valor) for i, valor in enumerate(respostas, 1))
    return total * 2.5


def taxa_conclusao(linhas: list[dict[str, str]], campo: str) -> float | None:
    valores = [(linha.get(campo) or "").strip().lower() for linha in linhas]
    valores = [valor for valor in valores if valor in {"sim", "nao", "não", "1", "0", "true", "false"}]
    if not valores:
        return None
    concluidas = sum(valor in {"sim", "1", "true"} for valor in valores)
    return round(concluidas / len(valores), 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arquivo_csv", type=Path, help="CSV preenchido conforme docs/modelos/registro_sessao.csv")
    parser.add_argument("--output", type=Path, default=None, help="JSON agregado; padrão: resumo_estudo.json ao lado do CSV")
    args = parser.parse_args()
    if not args.arquivo_csv.is_file():
        parser.error("Arquivo de respostas não encontrado.")
    with args.arquivo_csv.open(encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    if not linhas:
        parser.error("O CSV não contém sessões.")

    sus = [p for linha in linhas if (p := pontuacao_sus(linha)) is not None]
    ganhos_nexo = []
    ganhos_comparacao = []
    diferencas_pareadas = []
    retencao_nexo = []
    retencao_comparacao = []
    diferencas_retencao = []
    for linha in linhas:
        pre_nexo, pos_nexo = numero(linha, "pre_neixo"), numero(linha, "pos_neixo")
        pre_comp, pos_comp = numero(linha, "pre_comparacao"), numero(linha, "pos_comparacao")
        ganho_nexo = pos_nexo - pre_nexo if pre_nexo is not None and pos_nexo is not None else None
        ganho_comp = pos_comp - pre_comp if pre_comp is not None and pos_comp is not None else None
        if ganho_nexo is not None:
            ganhos_nexo.append(ganho_nexo)
        if ganho_comp is not None:
            ganhos_comparacao.append(ganho_comp)
        if ganho_nexo is not None and ganho_comp is not None:
            diferencas_pareadas.append(ganho_nexo - ganho_comp)
        ret_nexo = numero(linha, "retencao_neixo_7d")
        ret_comp = numero(linha, "retencao_comparacao_7d")
        if ret_nexo is not None:
            retencao_nexo.append(ret_nexo)
        if ret_comp is not None:
            retencao_comparacao.append(ret_comp)
        if ret_nexo is not None and ret_comp is not None:
            diferencas_retencao.append(ret_nexo - ret_comp)

    tasks = ("upload", "conferir_ocr", "exercicio")
    saida = {
        "sessoes": len(linhas),
        "participantes_codificados": len({(linha.get("codigo_participante") or "").strip() for linha in linhas if (linha.get("codigo_participante") or "").strip()}),
        "sus": media_ic(sus),
        "ganho_pre_pos_neixo": media_ic(ganhos_nexo),
        "ganho_pre_pos_comparacao": media_ic(ganhos_comparacao),
        "diferenca_pareada_dos_ganhos_neixo_menos_comparacao": media_ic(diferencas_pareadas),
        "retencao_neixo_7d": media_ic(retencao_nexo),
        "retencao_comparacao_7d": media_ic(retencao_comparacao),
        "diferenca_pareada_retencao_neixo_menos_comparacao": media_ic(diferencas_retencao),
        "conclusao_tarefas": {tarefa: taxa_conclusao(linhas, f"tarefa_{tarefa}_concluida") for tarefa in tasks},
        "mediana_tempo_tarefas_segundos": {
            tarefa: round(statistics.median(valores), 1) if (valores := [x for linha in linhas if (x := numero(linha, f"tarefa_{tarefa}_seg")) is not None]) else None
            for tarefa in tasks
        },
        "nota": "Resumo descritivo. Intervalos bootstrap não substituem análise inferencial; verifique dados ausentes, desenho, protocolo e pressupostos antes de concluir.",
    }
    destino = args.output or args.arquivo_csv.with_name("resumo_estudo.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    print(f"\nResumo agregado salvo em: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
