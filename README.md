# Processamento de imagens para estudos

Projeto acadêmico voltado para o estudo de processamento digital de imagens e reconhecimento óptico de caracteres (OCR). A aplicação permite receber uma imagem, aplicar etapas de pré-processamento e extrair texto automaticamente para demonstração prática dos conceitos de visão computacional.

## Objetivo do projeto

O trabalho tem como objetivo aplicar técnicas de processamento de imagem para melhorar a legibilidade de documentos e facilitar a extração de texto. A interface foi criada para permitir a visualização das etapas do processo, além de mostrar resultados em um ambiente didático e de fácil compreensão.

## Funcionalidades

- Recebe imagens em formatos como PNG, JPG, BMP, TIFF e WEBP.
- Converte a imagem para escala de cinza e melhora o contraste.
- Reduz ruídos e corrige pequenas inclinações da página.
- Aplica binarização para separar melhor texto e fundo.
- Reconhece texto automaticamente com Tesseract OCR.
- Exibe imagem original, imagem processada e texto extraído.
- Mantém um histórico de imagens processadas dentro da interface.
- Apresenta detalhes técnicos como dimensões, pixels, qualidade, formato e cores utilizadas.

## Estrutura do projeto

    Processamento-Imagens-Estudos/
    ├── backend/
    │   ├── __init__.py
    │   ├── main.py             # API FastAPI e servidor do frontend
    │   └── processamento.py    # operações de visão computacional e OCR
    ├── frontend/
    │   ├── index.html
    │   ├── app.js
    │   └── style.css
    ├── requirements.txt
    └── README.md

## Requisitos e execução

É necessário ter Python 3.11+ e o Tesseract OCR instalado com os idiomas português (por) e inglês (eng). O pacote Python pytesseract não instala o programa Tesseract, então o executável precisa estar disponível no sistema.

No Windows:

    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    uvicorn backend.main:app --reload

Acesse http://127.0.0.1:8000.

## Fluxo do sistema

1. Upload da imagem.
2. Validação do arquivo.
3. Conversão para tons de cinza.
4. Ajuste de contraste e redução de ruído.
5. Correção de inclinação da página.
6. Binarização e extração do texto por OCR.
7. Exibição do resultado na interface.

## Fundamentos técnicos

Uma imagem digital é representada por uma matriz de pixels. A qualidade do resultado depende diretamente da qualidade da entrada e da forma como os dados visuais são tratados antes do reconhecimento. Técnicas como CLAHE, filtros de suavização, limiarização adaptativa e correção de alinhamento foram aplicadas para melhorar a leitura automática do conteúdo.

## Aplicações do projeto

- Documentos impressos com baixa qualidade de imagem.
- Páginas fotocopiadas ou com ruído visual.
- Documentos de estudo e apostilas.
- Extração de texto em ambientes acadêmicos e didáticos.

## Conclusão

O projeto demonstra de forma prática como a combinação entre processamento de imagem e OCR pode transformar uma imagem em texto legível. Além de funcionar como ferramenta experimental, ele também serve como base para apresentação de conceitos de visão computacional e de aplicação tecnológica em contextos acadêmicos.
