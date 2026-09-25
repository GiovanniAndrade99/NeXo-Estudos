"""Gera as imagens de exemplo da aba Fundamentos usando o mesmo pipeline do backend.

Uso: python tools/gerar_imagens_fundamentos.py
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from backend.processamento import (  # noqa: E402
    _configurar_tesseract, _corrigir_inclinacao, _normalizar_iluminacao,
)

SAIDA = RAIZ / "frontend" / "fundamentos"
SAIDA.mkdir(exist_ok=True)
W, H = 360, 400  # cada metade do quadro
rng = np.random.default_rng(7)

# 1) Página "fotografada": papel amarelado, luz desigual, texto, ruído e leve inclinação.
pw, ph = 900, 1000
pagina = np.full((ph, pw, 3), (205, 228, 240), np.uint8)  # BGR, papel creme
linhas = [
    ("Processamento Digital", 1.6, 3),
    ("de Imagens", 1.6, 3),
    ("", 0, 0),
    ("O pre-processamento melhora", 1.05, 2),
    ("a leitura do texto antes do", 1.05, 2),
    ("reconhecimento por OCR.", 1.05, 2),
    ("", 0, 0),
    ("Cada pixel guarda uma", 1.05, 2),
    ("intensidade de luz.", 1.05, 2),
    ("", 0, 0),
    ("Contraste, ruido e angulo", 1.05, 2),
    ("mudam o resultado final.", 1.05, 2),
]
y = 150
for texto, escala, esp in linhas:
    if texto:
        cv2.putText(pagina, texto, (80, y), cv2.FONT_HERSHEY_DUPLEX, escala, (70, 52, 40), esp, cv2.LINE_AA)
    y += 70 if escala > 1.2 else 62
# sublinhado azul de caneta
cv2.line(pagina, (80, 245), (520, 250), (170, 90, 40), 3, cv2.LINE_AA)

# iluminação desigual (sombra no canto inferior direito)
yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
luz = 1.05 - 0.55 * ((xx / pw) * 0.6 + (yy / ph) * 0.8) ** 1.6
pagina = np.clip(pagina.astype(np.float32) * luz[..., None], 0, 255)
# ruído de sensor + pontos
pagina += rng.normal(0, 5, pagina.shape)
pagina = np.clip(pagina, 0, 255).astype(np.uint8)
pontos = rng.random((ph, pw)) < 0.0015
pagina[pontos] = rng.integers(40, 120, (pontos.sum(), 1)).astype(np.uint8)
# inclinação de ~5 graus
M = cv2.getRotationMatrix2D((pw / 2, ph / 2), 5, 1.0)
foto = cv2.warpAffine(pagina, M, (pw, ph), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

# 2) Mesmas etapas do backend.processar. A ampliação é omitida: as letras desta página já são
#    grandes, e manter o tamanho original deixa os recortes das figuras alinhados.
cinza = cv2.cvtColor(foto, cv2.COLOR_BGR2GRAY)
iluminacao_uniforme = _normalizar_iluminacao(cinza)
sem_ruido = cv2.medianBlur(iluminacao_uniforme, 3)
_, binaria = cv2.threshold(sem_ruido, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
alinhada, angulo = _corrigir_inclinacao(binaria)
print("inclinacao corrigida:", round(angulo, 2))

CROP = (slice(60, 60 + 800), slice(20, 20 + 720))  # recorte comum com o texto


def bgr(img):
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img


def metade(img, crop=CROP):
    return cv2.resize(bgr(img)[crop], (W, H), interpolation=cv2.INTER_AREA)


def quadro(esq, dir_):
    sep = np.full((H, 6, 3), (52, 34, 23), np.uint8)  # cor do card (#172234 em BGR)
    return np.hstack([esq, sep, dir_])


def salvar(nome, img):
    cv2.imwrite(str(SAIDA / nome), img, [cv2.IMWRITE_WEBP_QUALITY, 82])
    print(nome, (SAIDA / nome).stat().st_size // 1024, "KB")


# 01 Imagem digital: página + zoom nos pixels de uma letra, com grade e valores
zoom_src = cinza[CROP][146:164, 95:111]  # 16x18 pixels de um traço
cel = W // 16
zoom = cv2.resize(zoom_src, (16 * cel, 18 * cel), interpolation=cv2.INTER_NEAREST)
zoom = bgr(zoom)
for i in range(19):
    cv2.line(zoom, (i * cel, 0), (i * cel, 18 * cel), (90, 90, 90), 1)
    cv2.line(zoom, (0, i * cel), (16 * cel, i * cel), (90, 90, 90), 1)
for r in range(0, 18, 3):
    for c in range(0, 16, 3):
        v = int(zoom_src[r, c])
        cor = (20, 20, 20) if v > 120 else (235, 235, 235)
        cv2.putText(zoom, str(v), (c * cel + 2, r * cel + cel - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.28, cor, 1, cv2.LINE_AA)
zoom = cv2.copyMakeBorder(zoom, 0, H - zoom.shape[0], 0, W - zoom.shape[1], cv2.BORDER_CONSTANT, value=(52, 34, 23))
pag = metade(foto)
x0, y0 = int(95 * W / 720), int(146 * H / 800)
cv2.rectangle(pag, (x0 - 2, y0 - 2), (x0 + 10, y0 + 10), (107, 243, 185), 2)  # verde de destaque
salvar("01-imagem-digital.webp", quadro(pag, zoom))

# 02 Escala de cinza
salvar("02-escala-cinza.webp", quadro(metade(foto), metade(cinza)))
# 03 Contraste e ruído (recorte ampliado para o ruído ficar visível)
crop_zoom = (slice(420, 420 + 400), slice(300, 300 + 360))
salvar("03-contraste-ruido.webp", quadro(metade(cinza, crop_zoom), metade(sem_ruido, crop_zoom)))
# 04 Binarização
salvar("04-binarizacao.webp", quadro(metade(sem_ruido), metade(binaria)))


# 05 Inclinação: guias horizontais evidenciam o antes/depois
def com_guias(img):
    out = metade(img)
    for gy in range(40, H, 40):
        cv2.line(out, (0, gy), (W, gy), (240, 160, 90), 1, cv2.LINE_AA)
    return out


salvar("05-inclinacao.webp", quadro(com_guias(binaria), com_guias(alinhada)))

# 06 OCR: caixas das palavras reconhecidas + texto extraído
cfg = f"--psm 6 {_configurar_tesseract()}".strip()
dados = pytesseract.image_to_data(alinhada, lang="por+eng", config=cfg, output_type=pytesseract.Output.DICT)
caixas = bgr(alinhada.copy())
for i, palavra in enumerate(dados["text"]):
    if palavra.strip() and float(dados["conf"][i]) > 40:
        x, y_, w, h = dados["left"][i], dados["top"][i], dados["width"][i], dados["height"][i]
        cv2.rectangle(caixas, (x - 3, y_ - 3), (x + w + 3, y_ + h + 3), (60, 180, 60), 2)
texto = pytesseract.image_to_string(alinhada, lang="por+eng", config=cfg).strip()
print("OCR:\n" + texto)
painel = np.full((H, W, 3), (40, 26, 16), np.uint8)
yy_ = 34
for linha in [l for l in texto.splitlines() if l.strip()][:11]:
    linha = linha.encode("ascii", "ignore").decode()[:30]
    cv2.putText(painel, linha, (16, yy_), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 245, 205), 1, cv2.LINE_AA)
    yy_ += 32
salvar("06-ocr.webp", quadro(metade(caixas), painel))


