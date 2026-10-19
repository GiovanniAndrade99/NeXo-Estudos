"""Avaliação direta das segmentações do pipeline, com gabarito por pixel (FUNSD, conjunto de teste).

Parte A — tinta × papel (backend.processamento.segmentar_texto):
  O gabarito é a tinta do scan limpo do FUNSD (limiar de Otsu no scan original). A imagem é
  degradada como uma foto de celular (sombra, tom amarelado, ruído e rotação) e o gabarito é
  levado à mesma geometria pela mesma matriz de rotação. Cada método segmenta a foto e é
  comparado ao gabarito por pixel (precisão, revocação, F1 = Dice, IoU) e por palavra
  (caixas anotadas do FUNSD: palavra "bem segmentada" quando o F1 dentro da caixa é >= 0,8).

Parte B — recorte da folha (backend.perspectiva.detectar_folha):
  Nas fotos em perspectiva a posição real da folha é conhecida (homografia aplicada). Mede a
  sobreposição (IoU) entre a folha detectada e a real, o erro dos cantos, e os falsos alarmes
  em scans e fotos sem perspectiva (onde não há folha a recortar).

Uso: python tools/avaliar_segmentacao.py
Saídas: docs/segmentacao/resultados.json e figuras de exemplo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
from avaliar_ocr import PASTA_TESTE, baixar_funsd, degradar, fotografar_em_perspectiva  # noqa: E402
from backend import perspectiva  # noqa: E402
from backend.frequencia import filtro_homomorfico  # noqa: E402
from backend.processamento import _ampliar_para_ocr, segmentar_texto  # noqa: E402

PASTA_SAIDA = RAIZ / "docs" / "segmentacao"
F1_PALAVRA_MINIMO = 0.8


# ---------------------------------------------------------------- métodos de segmentação

def _otsu(cinza: np.ndarray) -> np.ndarray:
    _, binaria = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binaria


def _pipeline_original(cinza: np.ndarray) -> np.ndarray:
    """Pipeline anterior à avaliação com o FUNSD: CLAHE + mediana + limiar adaptativo (sem ampliação)."""
    realce = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cinza)
    return cv2.adaptiveThreshold(cv2.medianBlur(realce, 3), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)


def _homomorfico(cinza: np.ndarray) -> np.ndarray:
    """Alternativa no domínio da frequência (parâmetros escolhidos no treino; ver docs/FFT.md)."""
    return _otsu(cv2.medianBlur(filtro_homomorfico(cinza)[0], 3))


def _como_no_app(funcao):
    """Segmenta como o app (imagem ampliada para o OCR) e volta à resolução original para comparar."""
    def segmentar(cinza: np.ndarray) -> np.ndarray:
        ampliada = _ampliar_para_ocr(cinza)
        binaria = funcao(ampliada)
        if ampliada.shape != cinza.shape:
            binaria = cv2.resize(binaria, (cinza.shape[1], cinza.shape[0]), interpolation=cv2.INTER_AREA)
        return binaria
    return segmentar


METODOS = {
    "Otsu direto (sem pré-processamento)": _otsu,
    "Pipeline original (CLAHE + limiar adaptativo)": _pipeline_original,
    "Homomórfico (FFT) + mediana + Otsu": _como_no_app(_homomorfico),
    "Pipeline atual (fundo + mediana + Otsu)": _como_no_app(segmentar_texto),
    "Pipeline atual, janela do fundo 15": _como_no_app(lambda c: segmentar_texto(c, 15)),
    "Pipeline atual, janela do fundo 61": _como_no_app(lambda c: segmentar_texto(c, 61)),
}


# ---------------------------------------------------------------- parte A

def _palavras(anotacao: Path) -> list[np.ndarray]:
    dados = json.loads(anotacao.read_text(encoding="utf-8"))
    caixas = []
    for bloco in dados["form"]:
        for palavra in bloco["words"]:
            x1, y1, x2, y2 = palavra["box"]
            if palavra["text"].strip() and x2 > x1 and y2 > y1:
                caixas.append(np.float32([[x1, y1], [x2, y1], [x2, y2], [x1, y2]]))
    return caixas


def _comparar(tinta: np.ndarray, gabarito: np.ndarray, valido: np.ndarray) -> dict:
    vp = np.count_nonzero(tinta & gabarito & valido)
    fp = np.count_nonzero(tinta & ~gabarito & valido)
    fn = np.count_nonzero(~tinta & gabarito & valido)
    precisao = vp / (vp + fp) if vp + fp else 0.0
    revocacao = vp / (vp + fn) if vp + fn else 0.0
    return {"precisao": precisao, "revocacao": revocacao,
            "f1": 2 * vp / (2 * vp + fp + fn) if vp + fp + fn else 1.0,
            "iou": vp / (vp + fp + fn) if vp + fp + fn else 1.0}


def _palavras_bem_segmentadas(tinta, gabarito, poligonos) -> tuple[int, int]:
    boas = total = 0
    for poligono in poligonos:
        x, y, w, h = cv2.boundingRect(poligono.astype(np.int32))
        x, y = max(x, 0), max(y, 0)
        recorte = np.zeros((h + 1, w + 1), np.uint8)
        cv2.fillConvexPoly(recorte, (poligono - [x, y]).astype(np.int32), 1)
        dentro = recorte[: gabarito.shape[0] - y, : gabarito.shape[1] - x].astype(bool)
        g = gabarito[y:y + dentro.shape[0], x:x + dentro.shape[1]] & dentro
        if not g.any():
            continue  # palavra sem tinta no gabarito (caixa vazia ou fora da imagem)
        t = tinta[y:y + dentro.shape[0], x:x + dentro.shape[1]] & dentro
        f1 = 2 * np.count_nonzero(t & g) / (np.count_nonzero(t) + np.count_nonzero(g))
        total += 1
        boas += f1 >= F1_PALAVRA_MINIMO
    return boas, total


def parte_a(anotacoes: list[Path]) -> dict:
    medidas = {(m, c): [] for m in METODOS for c in ("scan original", "foto simulada")}
    palavras = {(m, c): [0, 0] for m in METODOS for c in ("scan original", "foto simulada")}
    exemplo = None
    for n, anotacao in enumerate(anotacoes, 1):
        imagem = cv2.imread(str(PASTA_TESTE / "images" / f"{anotacao.stem}.png"))
        altura, largura = imagem.shape[:2]
        gabarito_scan = _otsu(cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)) == 0
        caixas = _palavras(anotacao)
        foto, matriz = degradar(imagem, semente=n, com_transformacao=True)
        condicoes = {
            "scan original": (imagem, gabarito_scan, np.ones_like(gabarito_scan), caixas),
            "foto simulada": (
                foto,
                cv2.warpAffine(gabarito_scan.astype(np.uint8), matriz, (largura, altura), flags=cv2.INTER_NEAREST, borderValue=0).astype(bool),
                # Só compara onde existe imagem real (fora disso a rotação repete as bordas).
                cv2.warpAffine(np.ones((altura, largura), np.uint8), matriz, (largura, altura), flags=cv2.INTER_NEAREST, borderValue=0).astype(bool),
                [cv2.transform(c[None], matriz)[0] for c in caixas],
            ),
        }
        for condicao, (entrada, gabarito, valido, poligonos) in condicoes.items():
            cinza = cv2.cvtColor(entrada, cv2.COLOR_BGR2GRAY)
            for metodo, segmentar in METODOS.items():
                if condicao == "scan original" and metodo.startswith("Otsu direto"):
                    continue  # no scan limpo o Otsu direto é o próprio gabarito
                tinta = (segmentar(cinza) < 128) & valido
                medidas[(metodo, condicao)].append(_comparar(tinta, gabarito, valido))
                boas, total = _palavras_bem_segmentadas(tinta, gabarito, poligonos)
                palavras[(metodo, condicao)][0] += boas
                palavras[(metodo, condicao)][1] += total
                if n == 1 and condicao == "foto simulada":
                    exemplo = exemplo or {"foto": entrada, "gabarito": gabarito, "valido": valido, "mascaras": {}}
                    exemplo["mascaras"][metodo] = tinta
        print(f"  parte A: {n}/{len(anotacoes)}", end="\r")
    resultados = {}
    for (metodo, condicao), lista in medidas.items():
        if lista:
            media = {k: float(np.mean([m[k] for m in lista])) for k in lista[0]}
            boas, total = palavras[(metodo, condicao)]
            media["palavras_bem_segmentadas"] = boas / total if total else 0.0
            resultados.setdefault(condicao, {})[metodo] = media
    _figura_tinta(exemplo)
    return resultados


# ---------------------------------------------------------------- parte B

def _iou_poligonos(a: np.ndarray, b: np.ndarray, forma: tuple[int, int]) -> float:
    ma, mb = np.zeros(forma, np.uint8), np.zeros(forma, np.uint8)
    cv2.fillConvexPoly(ma, a.astype(np.int32), 1)
    cv2.fillConvexPoly(mb, b.astype(np.int32), 1)
    return np.count_nonzero(ma & mb) / max(1, np.count_nonzero(ma | mb))


def _foto_mesa_dificil(imagem: np.ndarray, semente: int) -> tuple[np.ndarray, np.ndarray]:
    """Mesma perspectiva, mas sobre uma mesa clara com veios de madeira e luz desigual.

    A mesa clara deixa pouco contraste entre folha e fundo, e os veios criam bordas falsas:
    é o caso difícil para o recorte da folha.
    """
    _, homografia = fotografar_em_perspectiva(imagem, semente, com_transformacao=True)
    rng = np.random.default_rng(10_000 + semente)
    altura, largura = imagem.shape[:2]
    alto, largo = int(altura * 1.5), int(largura * 1.6)
    manchas = cv2.resize(rng.normal(0, 1, (alto // 40 + 1, largo // 40 + 1)), (largo, alto), interpolation=cv2.INTER_CUBIC)
    veios = 10 * np.sin(np.arange(alto)[:, None] / rng.uniform(6, 14) + 3 * manchas)
    tom = rng.uniform(170, 210)
    mesa = (tom + 15 * manchas + veios)[..., None] * np.float32([0.82, 0.92, 1.0]) + rng.normal(0, 6, (alto, largo, 3))
    folha = cv2.warpPerspective(imagem, homografia, (largo, alto), flags=cv2.INTER_LINEAR).astype(np.float32)
    dentro = cv2.warpPerspective(np.ones((altura, largura), np.uint8), homografia, (largo, alto)) > 0
    mesa[dentro] = folha[dentro]
    # Luz caindo de um lado: escurece até 30% no lado oposto, na folha e na mesa.
    direcao = rng.uniform(0, 2 * np.pi)
    y, x = np.mgrid[0:alto, 0:largo].astype(np.float32)
    rampa = (x / largo - 0.5) * np.cos(direcao) + (y / alto - 0.5) * np.sin(direcao)
    luz = 1 - rng.uniform(0.15, 0.30) * (rampa - rampa.min()) / (rampa.max() - rampa.min())
    return np.clip(mesa * luz[..., None], 0, 255).astype(np.uint8), homografia


CENARIOS_FOLHA = {
    "mesa escura uniforme": lambda imagem, n: fotografar_em_perspectiva(imagem, n, com_transformacao=True),
    "mesa clara com veios e luz desigual": _foto_mesa_dificil,
}
LIMIARES_CONTRASTE = (10, perspectiva.CONTRASTE_MINIMO, 40)


def _detectar(imagem: np.ndarray, contraste: float):
    original = perspectiva.CONTRASTE_MINIMO
    perspectiva.CONTRASTE_MINIMO = contraste
    try:
        return perspectiva.detectar_folha(imagem)
    finally:
        perspectiva.CONTRASTE_MINIMO = original


def parte_b(anotacoes: list[Path]) -> dict:
    medidas = {(c, cenario): {"iou": [], "erro": []} for c in LIMIARES_CONTRASTE for cenario in CENARIOS_FOLHA}
    alarmes = dict.fromkeys(LIMIARES_CONTRASTE, 0)
    exemplos = {}
    for n, anotacao in enumerate(anotacoes, 1):
        imagem = cv2.imread(str(PASTA_TESTE / "images" / f"{anotacao.stem}.png"))
        altura, largura = imagem.shape[:2]
        sem_folha = (imagem, degradar(imagem, semente=n))  # scan e foto sem perspectiva: nada a recortar
        for cenario, fotografar in CENARIOS_FOLHA.items():
            foto, homografia = fotografar(imagem, n)
            real = cv2.perspectiveTransform(np.float32([[[0, 0], [largura, 0], [largura, altura], [0, altura]]]), homografia)[0]
            for contraste in LIMIARES_CONTRASTE:
                cantos = _detectar(foto, contraste)
                if contraste == perspectiva.CONTRASTE_MINIMO and n == 1:
                    exemplos[cenario] = (foto, real, cantos)
                if cantos is None:
                    medidas[(contraste, cenario)]["iou"].append(0.0)
                    continue
                medidas[(contraste, cenario)]["iou"].append(_iou_poligonos(real, cantos, foto.shape[:2]))
                diagonal = np.linalg.norm(real[2] - real[0])
                medidas[(contraste, cenario)]["erro"].append(float(np.mean(np.linalg.norm(real - cantos, axis=1)) / diagonal))
        for contraste in LIMIARES_CONTRASTE:
            alarmes[contraste] += sum(_detectar(img, contraste) is not None for img in sem_folha)
        print(f"  parte B: {n}/{len(anotacoes)}", end="\r")
    _figura_folha(exemplos)

    resultado = {"limiar_do_app": perspectiva.CONTRASTE_MINIMO, "por_limiar": {}}
    for contraste in LIMIARES_CONTRASTE:
        linha = {"imagens_sem_folha": 2 * len(anotacoes), "falsos_alarmes": alarmes[contraste]}
        for cenario in CENARIOS_FOLHA:
            ious = np.array(medidas[(contraste, cenario)]["iou"])
            erros = medidas[(contraste, cenario)]["erro"]
            linha[cenario] = {
                "fotos": len(ious),
                "detectadas": int(np.count_nonzero(ious > 0)),
                "iou_medio": float(ious.mean()),
                "fracao_iou_acima_de_0_95": float((ious >= 0.95).mean()),
                "erro_medio_cantos_percentual_da_diagonal": 100 * float(np.mean(erros)) if erros else None,
            }
        resultado["por_limiar"][str(contraste)] = linha
    return resultado


# ---------------------------------------------------------------- figuras

def _sobreposicao(tinta, gabarito, valido):
    """Branco: papel certo. Preto: tinta certa. Vermelho: tinta inventada (falso positivo). Azul: tinta perdida."""
    img = np.full(tinta.shape + (3,), 255, np.uint8)
    img[tinta & gabarito] = (30, 30, 30)
    img[tinta & ~gabarito & valido] = (40, 40, 230)
    img[~tinta & gabarito & valido] = (230, 120, 30)
    img[~valido] = (200, 200, 200)
    return img


def _rotular(painel: np.ndarray, texto: str, altura: int = 34) -> np.ndarray:
    """Faixa branca com título acima do painel (fonte Hershey: só ASCII, por isso sem acentos)."""
    faixa = np.full((altura, painel.shape[1], 3), 255, np.uint8)
    cv2.putText(faixa, texto, (8, altura - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 1, cv2.LINE_AA)
    return np.vstack([faixa, painel])


def _juntar(paineis: list[np.ndarray], espaco: int = 8) -> np.ndarray:
    separador = np.full((paineis[0].shape[0], espaco, 3), 255, np.uint8)
    return np.hstack([p for painel in paineis for p in (painel, separador)][:-1])


def _figura_tinta(exemplo) -> None:
    foto, gabarito, valido = exemplo["foto"], exemplo["gabarito"], exemplo["valido"]
    altura, largura = gabarito.shape
    y0, x0 = altura // 2, largura // 4  # trecho com texto, longe das bordas giradas
    corte = (slice(y0, y0 + 300), slice(x0, x0 + 420))
    paineis = [_rotular(foto[corte], "Foto simulada (entrada)")]
    for nome, titulo in (("Otsu direto (sem pré-processamento)", "Otsu direto"),
                         ("Pipeline original (CLAHE + limiar adaptativo)", "Pipeline original (CLAHE + adaptativo)"),
                         ("Pipeline atual (fundo + mediana + Otsu)", "Pipeline atual (fundo + Otsu)")):
        paineis.append(_rotular(_sobreposicao(exemplo["mascaras"][nome], gabarito, valido)[corte], titulo))
    figura = _juntar(paineis)
    legenda = np.full((30, figura.shape[1], 3), 255, np.uint8)
    for x, cor, texto in ((8, (30, 30, 30), "tinta correta"), (190, (40, 40, 230), "tinta inventada (falso positivo)"),
                          (520, (230, 120, 30), "tinta perdida (falso negativo)")):
        cv2.rectangle(legenda, (x, 8), (x + 16, 24), cor, -1)
        cv2.putText(legenda, texto, (x + 24, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA)
    cv2.imwrite(str(PASTA_SAIDA / "tinta_antes_depois.png"), np.vstack([figura, legenda]))


def _figura_folha(exemplos: dict) -> None:
    """Contorno real da folha (verde) e o detectado (magenta), um painel por cenário."""
    paineis = []
    for cenario, (foto, real, detectada) in exemplos.items():
        escala = 640 / foto.shape[0]
        img = cv2.resize(foto, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
        cv2.polylines(img, [np.int32(real * escala)], True, (60, 200, 60), 7, cv2.LINE_AA)
        if detectada is not None:
            cv2.polylines(img, [np.int32(detectada * escala)], True, (220, 40, 220), 2, cv2.LINE_AA)
        titulo = {"mesa escura uniforme": "Mesa escura uniforme"}.get(cenario, "Mesa clara, veios e luz desigual")
        paineis.append(_rotular(img, titulo + ("" if detectada is not None else " - NAO DETECTADA")))
    cv2.imwrite(str(PASTA_SAIDA / "folha_detectada.png"), _juntar(paineis))


def main() -> None:
    baixar_funsd()
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    anotacoes = sorted((PASTA_TESTE / "annotations").glob("*.json"))
    resultado_a = parte_a(anotacoes)
    print("\nParte A — tinta × papel (média por imagem, conjunto de teste)")
    for condicao, metodos in resultado_a.items():
        print(f"\n  {condicao}")
        print(f"  {'Método':48s} {'Precisão':>9s} {'Revocação':>10s} {'F1/Dice':>8s} {'IoU':>6s} {'Palavras ok':>12s}")
        for metodo, r in metodos.items():
            print(f"  {metodo:48s} {100 * r['precisao']:8.1f}% {100 * r['revocacao']:9.1f}% {100 * r['f1']:7.1f}% "
                  f"{100 * r['iou']:5.1f}% {100 * r['palavras_bem_segmentadas']:11.1f}%")
    resultado_b = parte_b(anotacoes)
    print("\nParte B — recorte da folha (fotos em perspectiva do conjunto de teste)")
    for contraste, linha in resultado_b["por_limiar"].items():
        app = " (usado no app)" if int(contraste) == resultado_b["limiar_do_app"] else ""
        print(f"\n  contraste mínimo {contraste}{app}: falsos alarmes {linha['falsos_alarmes']}/{linha['imagens_sem_folha']} imagens sem folha")
        for cenario in CENARIOS_FOLHA:
            r = linha[cenario]
            erro = "—" if r["erro_medio_cantos_percentual_da_diagonal"] is None else f"{r['erro_medio_cantos_percentual_da_diagonal']:.2f}%"
            print(f"    {cenario:38s} detectadas {r['detectadas']}/{r['fotos']}  IoU médio {r['iou_medio']:.3f}  "
                  f"IoU>=0,95 {100 * r['fracao_iou_acima_de_0_95']:.0f}%  erro dos cantos {erro} da diagonal")
    (PASTA_SAIDA / "resultados.json").write_text(json.dumps({"tinta_papel": resultado_a, "folha": resultado_b},
                                                            ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
