# Nexo Estudos - Laboratorio de processamento de imagens

Aplicacao academica de processamento digital de imagens e reconhecimento optico de caracteres (OCR). O laboratorio aceita imagens e PDFs, prepara cada pagina para leitura e apresenta o texto e os resultados do processamento.

## Recursos

- Upload de ate dois arquivos por processamento: PNG, JPG/JPEG, BMP, TIFF, WEBP ou PDF.
- Conversao das paginas do PDF em imagens para processamento; cada PDF pode ter ate 10 paginas.
- Pre-processamento com tons de cinza, ajuste de contraste, reducao de ruido, binarizacao e correcao de inclinacao.
- OCR em portugues e ingles via Tesseract.
- Tempo de processamento individual de cada imagem ou pagina, mostrado em milissegundos ou segundos.
- Laboratório protegido por login em `/login`, com criação de conta, recuperação de senha e bloqueio após 5 tentativas erradas.
- Menu **Comparar imagens**, logo abaixo de **Historico**, com tempos por item e comparacao de quaisquer duas imagens salvas no historico.
- Ajustes manuais, historico local e sugestoes de estudo.

## Funcionamento e pipeline

A documentação detalhada do funcionamento, das etapas de processamento de imagens e da integração com IA está em [docs/PIPELINE.md](docs/PIPELINE.md). Ela também esclarece o papel do OCR e das regras de classificação temática.

## Dataset e avaliação

O pipeline de processamento de imagens foi ajustado e avaliado com o dataset público **FUNSD** (formulários digitalizados com o texto anotado manualmente): <https://guillaumejaume.github.io/FUNSD/>. O projeto não treina modelo próprio; o FUNSD é usado para medir o ganho do pré-processamento no OCR.

| Condição (50 imagens de teste) | Sem pré-processamento | Com o pipeline |
|---|---|---|
| Scan original | 61,3% | **72,1%** |
| Foto simulada (sombra, ruído e inclinação) | 32,4% | **67,6%** |

*F1 das palavras reconhecidas pelo OCR em relação ao texto anotado.* Metodologia, resultados por imagem e instruções para reproduzir: [docs/AVALIACAO.md](docs/AVALIACAO.md).

## Requisitos

- Python 3.11 ou superior.
- Tesseract OCR instalado no sistema (o executavel padrao em `C:\Program Files\Tesseract-OCR` e detectado automaticamente).
- Modelos de idioma `por` e `eng` na pasta local `%LOCALAPPDATA%\Tesseract-OCR\tessdata`.
- Dependencias Python de `requirements.txt`, incluindo PyMuPDF para converter PDFs.

## Instalacao e execucao no Windows

No PowerShell, entre na pasta do projeto e execute:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

O comando chama o Python do ambiente virtual diretamente e funciona mesmo quando o PowerShell bloqueia scripts de ativacao. Abra [http://127.0.0.1:8000](http://127.0.0.1:8000) no navegador. A documentacao interativa da API fica em [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Se o Tesseract estiver fora do caminho padrao, configure `TESSERACT_CMD` com o caminho do executavel. O idioma padrao de OCR e `por+eng`; use `OCR_LANGUAGES` para alterar essa configuracao.

Para instalar os modelos de idioma em uma maquina nova, execute no PowerShell:

```powershell
$dadosOCR = Join-Path $env:LOCALAPPDATA 'Tesseract-OCR\tessdata'
New-Item -ItemType Directory -Force -Path $dadosOCR | Out-Null
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata' -OutFile (Join-Path $dadosOCR 'eng.traineddata')
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/por.traineddata' -OutFile (Join-Path $dadosOCR 'por.traineddata')
```

O projeto procura esses modelos nessa pasta do usuario e usa o conjunto rapido oficial do Tesseract.

## Login e contas

O laboratório só abre depois do login: sem sessão, qualquer página redireciona para `/login` e a API responde `401`. As contas ficam no banco SQLite `contas.db` (fora do Git), com senhas guardadas apenas como hash scrypt.

- **Entrar:** após 5 tentativas erradas seguidas, o login fica bloqueado por 15 minutos, contando por IP e por e-mail. Um login certo zera a contagem.
- **Manter conectado:** sem marcar, a sessão termina em 8 horas; marcado, dura 30 dias.
- **Criar conta:** cadastra um usuário comum (nome, e-mail e senha com pelo menos 8 caracteres) e já entra no laboratório.
- **Esqueceu a senha?:** envia um link válido por 30 minutos e de uso único. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` e `SMTP_FROM` no `.env` (veja `.env.example`). Sem SMTP, o link aparece no terminal do servidor.

Para criar o administrador ou trocar a senha dele, execute na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m backend.contas
```

Para produção, configure `SESSION_SECRET` com um segredo longo, publique o site por HTTPS e defina `COOKIE_HTTPS_ONLY=true`. O limite de tentativas fica na memória do servidor e é zerado quando ele reinicia.

## Como usar

1. Abra a tela Processamento no menu Laboratorio.
2. Selecione ou arraste uma ou duas imagens/PDFs (ate 12 MB cada).
3. Clique em **Processar imagem**. PDFs sao processados pagina por pagina, com limite de 10 paginas por arquivo.
4. Veja o tempo gasto no cartao **Tempo de processamento**. No caso de PDF, cada pagina aparece com seu tempo no historico.
5. No menu do Laboratorio, abra **Comparar imagens** abaixo de **Historico**. Escolha dois itens do historico para comparar os originais lado a lado.
6. Use as abas de resumo, detalhes e antes/depois para consultar o resultado.

## Capturas de tela

Salve as capturas da interface em `docs/screenshots/` e atualize esta secao com as imagens do Laboratorio e da comparacao. Neste ambiente nao havia uma janela de navegador disponivel para capturar a interface; por isso, as imagens ainda precisam ser adicionadas.

## Estrutura

```text
backend/
  main.py             # API FastAPI, conversao de PDF e servidor do frontend
  contas.py           # contas, login e recuperacao de senha
  processamento.py    # processamento de imagem e OCR
frontend/
  index.html
  app.js
  style.css
  fundamentos/        # imagens de exemplo da aba Fundamentos
docs/
  PIPELINE.md         # funcionamento, pipeline e integracao com IA
  AVALIACAO.md        # avaliacao com o dataset FUNSD
  avaliacao/          # resultados por imagem e figura de exemplo
tools/
  avaliar_ocr.py                # avaliacao do pipeline com o FUNSD
  gerar_imagens_fundamentos.py  # gera as imagens da aba Fundamentos
tests/
  test_assistente_estudos.py
  test_autenticacao.py
  test_processamento.py
requirements.txt
README.md
```

## Limites de upload

Cada arquivo pode ter no maximo 12 MB. Sao aceitos ate dois arquivos por requisicao e ate 10 paginas por PDF. PDFs protegidos por senha nao sao processados. As imagens sao processadas localmente pelo servidor deste projeto. Miniaturas JPEG para comparacao ficam no IndexedDB deste navegador junto ao historico; os registros antigos sem miniatura precisam ser processados novamente para entrar na comparacao.
