"""Treina e avalia o classificador de matérias do Assistente de Estudos.

Dados: datasets/materias_wikipedia.jsonl (gerado por tools/montar_dataset_materias.py).
Modelo: TF-IDF (palavras + n-gramas de caracteres, que toleram erros do OCR) com
Regressão Logística, comparado a Naive Bayes, SVM linear e às regras de palavras-chave
usadas antes. A separação treino/teste é por ARTIGO: trechos do mesmo artigo nunca ficam
dos dois lados, para a nota não ser inflada.

Saídas:
* backend/modelos/classificador_materias.joblib (modelo final, treinado com todos os dados)
* docs/classificador/resultados.json e matriz_confusao.png

Uso: python tools/treinar_classificador.py
"""
from __future__ import annotations

import json
import random
import sys
import unicodedata
from pathlib import Path
from unittest import mock

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from backend.classificador import normalizar_para_modelo as normalizar  # noqa: E402
from backend import processamento  # noqa: E402
from backend.processamento import DISCIPLINAS, detectar_conteudo_assistente  # noqa: E402

DATASET = RAIZ / "datasets" / "materias_wikipedia.jsonl"
MODELO = RAIZ / "backend" / "modelos" / "classificador_materias.joblib"
PASTA_RESULTADOS = RAIZ / "docs" / "classificador"
SEMENTE = 42


def vetorizador() -> FeatureUnion:
    return FeatureUnion([
        ("palavras", TfidfVectorizer(preprocessor=normalizar, ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=15000)),
        ("caracteres", TfidfVectorizer(preprocessor=normalizar, analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True, max_features=20000)),
    ])


def modelos() -> dict[str, Pipeline]:
    return {
        "Naive Bayes": Pipeline([("tfidf", vetorizador()), ("clf", ComplementNB(alpha=0.3))]),
        "SVM linear": Pipeline([("tfidf", vetorizador()), ("clf", CalibratedClassifierCV(LinearSVC(C=0.5), cv=3))]),
        "Regressão Logística": Pipeline([("tfidf", vetorizador()), ("clf", LogisticRegression(C=8, max_iter=3000))]),
    }


# Confusões típicas do OCR, usadas para simular texto lido de uma foto.
TROCAS_OCR = {"o": "0", "l": "1", "e": "c", "a": "o", "m": "rn", "i": "l", "s": "5", "n": "m", "u": "v", "t": "f"}


def ruido_ocr(texto: str, taxa: float, rng: random.Random) -> str:
    saida = []
    for c in texto:
        sorte = rng.random()
        if sorte < taxa / 2 and c.lower() in TROCAS_OCR:
            saida.append(TROCAS_OCR[c.lower()])
        elif sorte < taxa * 0.75 and c.isalpha():
            continue  # letra perdida
        elif sorte < taxa and c == " ":
            continue  # palavras grudadas
        else:
            saida.append(c)
    return "".join(saida)


def regras_atuais(texto: str) -> str:
    # Sem o classificador: mede só as regras de palavras-chave, como eram antes do modelo.
    with mock.patch.object(processamento, "classificar_materia", lambda _texto: None):
        titulo = detectar_conteudo_assistente(texto)["livro"]
    return next((chave for chave, dados in DISCIPLINAS.items() if dados["titulo"] == titulo), "nenhuma")


def main() -> None:
    linhas = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines()]
    textos = [l["texto"] for l in linhas]
    rotulos = np.array([l["materia"] for l in linhas])
    grupos = np.array([l["artigo"] for l in linhas])
    treino, teste = next(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMENTE).split(textos, rotulos, grupos))
    assert not set(grupos[treino]) & set(grupos[teste]), "artigo repetido entre treino e teste"
    x_treino, x_teste = [textos[i] for i in treino], [textos[i] for i in teste]
    y_treino, y_teste = rotulos[treino], rotulos[teste]
    rng = random.Random(SEMENTE)
    x_ruido = [ruido_ocr(t, 0.08, rng) for t in x_teste]
    print(f"{len(textos)} trechos | treino {len(treino)} | teste {len(teste)} | {len(set(rotulos))} matérias\n")

    resultados = {}
    print(f"{'Método':22s} {'Acurácia':>9s} {'F1 macro':>9s} {'Acurácia c/ ruído OCR':>23s}")
    previsoes_regras = np.array([regras_atuais(t) for t in x_teste])
    previsoes_regras_ruido = np.array([regras_atuais(t) for t in x_ruido])
    resultados["Regras de palavras-chave (antes)"] = {
        "acuracia": accuracy_score(y_teste, previsoes_regras), "f1_macro": f1_score(y_teste, previsoes_regras, average="macro"),
        "acuracia_ruido": accuracy_score(y_teste, previsoes_regras_ruido),
    }
    for nome, modelo in modelos().items():
        modelo.fit(x_treino, y_treino)
        prev, prev_ruido = modelo.predict(x_teste), modelo.predict(x_ruido)
        resultados[nome] = {"acuracia": accuracy_score(y_teste, prev), "f1_macro": f1_score(y_teste, prev, average="macro"),
                            "acuracia_ruido": accuracy_score(y_teste, prev_ruido)}
    for nome, r in resultados.items():
        print(f"{nome:22.22s} {100 * r['acuracia']:8.1f}% {100 * r['f1_macro']:8.1f}% {100 * r['acuracia_ruido']:22.1f}%")

    escolhido = "Regressão Logística"
    final = modelos()[escolhido].fit(x_treino, y_treino)
    previsoes = final.predict(x_teste)
    relatorio = classification_report(y_teste, previsoes, output_dict=True, zero_division=0)
    print("\nPor matéria (Regressão Logística, conjunto de teste):")
    for materia in sorted(set(rotulos)):
        print(f"  {materia:22s} F1 {100 * relatorio[materia]['f1-score']:5.1f}%  (n={int(relatorio[materia]['support'])})")

    # Limiar de confiança: abaixo dele o assistente volta às regras (ex.: texto curto ou fora das matérias).
    probabilidades = final.predict_proba(x_teste).max(axis=1)
    acertos = previsoes == y_teste
    limiares = {}
    for limiar in (0.3, 0.4, 0.5, 0.6):
        cobertos = probabilidades >= limiar
        limiares[str(limiar)] = {"cobertura": float(cobertos.mean()), "acuracia_quando_confiante": float(acertos[cobertos].mean()) if cobertos.any() else None}
    print("\nConfiança mínima -> % dos textos classificados pelo modelo / acurácia nesses textos:")
    for limiar, dados in limiares.items():
        print(f"  {limiar}: {100 * dados['cobertura']:5.1f}% / {100 * (dados['acuracia_quando_confiante'] or 0):5.1f}%")

    PASTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    classes = sorted(set(rotulos))
    matriz = confusion_matrix(y_teste, previsoes, labels=classes)
    _desenhar_matriz(matriz, classes, PASTA_RESULTADOS / "matriz_confusao.png")
    (PASTA_RESULTADOS / "resultados.json").write_text(json.dumps({
        "dataset": {"trechos": len(textos), "treino": len(treino), "teste": len(teste),
                    "artigos": len(set(grupos)), "por_materia": {m: int((rotulos == m).sum()) for m in classes}},
        "comparacao": resultados, "por_materia": {m: relatorio[m] for m in classes}, "limiares": limiares,
        "matriz_confusao": {"classes": classes, "valores": matriz.tolist()},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # Modelo final para o app: mesmo método, treinado com todos os dados.
    MODELO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelos()[escolhido].fit(textos, rotulos), MODELO, compress=3)
    print(f"\nModelo salvo em {MODELO} ({MODELO.stat().st_size // 1024} KB)")


def _desenhar_matriz(matriz: np.ndarray, classes: list[str], destino: Path) -> None:
    import cv2
    celula, margem = 34, 170
    lado = margem + celula * len(classes)
    img = np.full((lado + 20, lado + 20, 3), 255, np.uint8)
    maximo = max(1, matriz.max())
    for i, linha in enumerate(matriz):
        for j, valor in enumerate(linha):
            intensidade = int(255 - 200 * valor / maximo)
            cor = (intensidade, 255, intensidade) if i == j else (intensidade, intensidade, 255)
            x, y = margem + j * celula, margem + i * celula
            cv2.rectangle(img, (x, y), (x + celula, y + celula), cor if valor else (250, 250, 250), -1)
            cv2.rectangle(img, (x, y), (x + celula, y + celula), (220, 220, 220), 1)
            if valor:
                cv2.putText(img, str(valor), (x + 7, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
    for k, nome in enumerate(classes):
        cv2.putText(img, nome[:20], (6, margem + k * celula + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (40, 40, 40), 1, cv2.LINE_AA)
        texto = np.full((celula, margem - 6, 3), 255, np.uint8)
        cv2.putText(texto, nome[:20], (2, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (40, 40, 40), 1, cv2.LINE_AA)
        rot = cv2.rotate(texto, cv2.ROTATE_90_COUNTERCLOCKWISE)
        img[0:rot.shape[0], margem + k * celula: margem + k * celula + rot.shape[1]] = rot
    cv2.putText(img, "linhas: materia real | colunas: prevista", (6, lado + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (90, 90, 90), 1, cv2.LINE_AA)
    cv2.imwrite(str(destino), img)


if __name__ == "__main__":
    main()
