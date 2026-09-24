"""API e página web do demonstrador."""
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .processamento import codificar_png, decodificar_imagem, processar, tesseract_disponivel

RAIZ = Path(__file__).resolve().parent.parent
PASTA_FRONTEND = RAIZ / "frontend"
TAMANHO_MAXIMO_BYTES = 12 * 1024 * 1024
TIPOS_ACEITOS = {"image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp"}

app = FastAPI(
    title="Laboratório de Processamento de Imagens",
    description="Pré-processamento de imagens de estudo e reconhecimento de texto (OCR).",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=PASTA_FRONTEND), name="static")


@app.get("/", include_in_schema=False)
def pagina_inicial():
    return FileResponse(PASTA_FRONTEND / "index.html")


@app.get("/api/health")
def health():
    disponivel, aviso = tesseract_disponivel()
    return {"status": "ok", "ocr_disponivel": disponivel, "aviso": aviso}


@app.post("/api/processar")
async def processar_arquivo(arquivos: list[UploadFile] = File(...)):
    if not arquivos:
        raise HTTPException(400, "Nenhuma imagem foi enviada.")
    if len(arquivos) > 2:
        raise HTTPException(400, "Você pode enviar no máximo 2 imagens por vez.")

    resultados = []
    for arquivo in arquivos:
        if arquivo.content_type not in TIPOS_ACEITOS:
            raise HTTPException(415, f"Formato não aceito para {arquivo.filename or 'imagem'}.")
        conteudo = await arquivo.read(TAMANHO_MAXIMO_BYTES + 1)
        if not conteudo:
            raise HTTPException(400, f"O arquivo {arquivo.filename or 'imagem'} está vazio.")
        if len(conteudo) > TAMANHO_MAXIMO_BYTES:
            raise HTTPException(413, f"A imagem {arquivo.filename or 'imagem'} deve ter no máximo 12 MB.")
        try:
            imagem = decodificar_imagem(conteudo)
            resultado = processar(imagem)
        except ValueError as erro:
            raise HTTPException(400, str(erro)) from erro
        altura, largura = resultado.original.shape[:2]
        resultados.append({
            "nome_arquivo": Path(arquivo.filename or "imagem").name,
            "dimensoes": {"largura": largura, "altura": altura},
            "inclinacao_corrigida_graus": resultado.inclinacao_corrigida_graus,
            "ocr_disponivel": resultado.ocr_disponivel,
            "aviso": resultado.aviso,
            "texto": resultado.texto,
            "assistente_estudos": resultado.assistente_estudos,
            "descricao_processo": resultado.descricao_processo,
            "imagens": {
                "original": codificar_png(resultado.original),
                "tons_cinza": codificar_png(resultado.tons_cinza),
                "processada": codificar_png(resultado.tratada),
            },
        })

    if len(resultados) == 1:
        return resultados[0]
    return {"quantidade": len(resultados), "arquivos": resultados}
