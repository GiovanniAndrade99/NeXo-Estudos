# Funcionamento e pipeline do NeXo Estudos

## Visão geral

O NeXo Estudos reúne duas partes do projeto: o laboratório de processamento de imagens e OCR, e o **Assistente de Estudos**, que representa a integração com o projeto desenvolvido para a disciplina de Inteligência Artificial. O laboratório prepara imagens de materiais didáticos e extrai seu texto; esse conteúdo alimenta o Assistente de Estudos, que identifica temas e apresenta apoio à revisão na interface.

O processamento é feito localmente pelo servidor da aplicação. O projeto não treina um modelo próprio de aprendizado de máquina e não utiliza um dataset de treinamento próprio. A leitura de texto é realizada pelo Tesseract OCR, usando seus modelos de idioma português (`por`) e inglês (`eng`). A identificação de disciplinas e a geração de sugestões são feitas por regras e palavras-chave no código.

## Pipeline completo da aplicação

```text
Pessoa usuária
  → navegador envia imagem/PDF para a API
  → validação do arquivo
  → PDF: conversão de cada página para imagem
  → preparação da imagem
  → OCR com Tesseract
  → Assistente de Estudos analisa o texto reconhecido
  → resposta JSON com texto, sugestões e imagens
  → interface apresenta resultados e histórico
```

### 1. Seleção e envio

Na interface, a pessoa seleciona até dois arquivos por solicitação. São aceitos PNG, JPG/JPEG, BMP, TIFF, WEBP e PDF, com limite de 12 MB por arquivo. O navegador envia os arquivos para o endpoint `POST /api/processar`.

### 2. Validação da entrada

O backend confere a quantidade, o formato e o tamanho dos arquivos. Arquivos vazios, formatos não aceitos ou arquivos acima do limite são rejeitados com uma mensagem de erro. Imagens são decodificadas pelo OpenCV. Se algum lado da imagem ultrapassar 4000 pixels, ela é reduzida proporcionalmente para respeitar esse limite.

### 3. Conversão de PDF

Quando o arquivo é PDF, o PyMuPDF abre o documento e converte cada página em uma imagem. PDFs protegidos por senha, vazios ou com mais de 10 páginas são recusados. Depois da conversão, cada página segue individualmente pelas mesmas etapas de processamento de uma imagem enviada diretamente.

### 4. Conversão para tons de cinza

O OpenCV converte a imagem colorida para uma matriz de intensidades em tons de cinza. Isso reduz a informação a analisar e deixa o texto mais fácil de tratar sem depender das cores originais.

### 5. Ajuste local de contraste

O CLAHE (Contrast Limited Adaptive Histogram Equalization) ajusta o contraste em pequenas regiões da imagem. Esse ajuste pode destacar letras em páginas com iluminação ou fundo irregulares sem aumentar o contraste de toda a página de uma só vez.

### 6. Redução de ruído

Um filtro mediano de tamanho 3 × 3 reduz pequenos pontos e imperfeições. A intenção é limpar o fundo preservando bordas, como os contornos das letras.

### 7. Binarização adaptativa

O limiar adaptativo gaussiano transforma a imagem em preto e branco. Como o limiar é calculado localmente, ele pode lidar melhor com variações de iluminação do que um único limiar global. Essa imagem binária serve de entrada para o alinhamento e o OCR.

### 8. Correção de inclinação

O sistema identifica componentes conectados que provavelmente correspondem à tinta e estima a orientação predominante. Se o ângulo estiver dentro do intervalo aceito pelo código (até 15 graus), a imagem é rotacionada para alinhar as linhas. A correção estimada, em graus, também é incluída no resultado.

### 9. Reconhecimento óptico de caracteres (OCR)

O `pytesseract` chama o executável Tesseract instalado no sistema. Por padrão, são usados os idiomas `por+eng` e o modo de segmentação `--psm 6`, apropriado para texto organizado em blocos. O texto reconhecido é devolvido ao sistema. Se o executável ou os idiomas necessários não estiverem disponíveis, a API informa o aviso e o restante do resultado pode continuar sem texto OCR.

### 10. Análise do texto para sugestões de estudo

O texto do OCR é normalizado para comparação (minúsculas e remoção de acentos) e confrontado com conjuntos de palavras-chave associados a disciplinas. As disciplinas com mais correspondências são priorizadas. A partir da categoria selecionada, o código monta uma descrição, um resumo de estudo e exercícios de revisão predefinidos. Algumas linhas extraídas também podem ser aproveitadas como tópicos/figuras, e há uma tentativa simples de identificar o autor.

Essa etapa é baseada em regras determinísticas: não há treinamento de classificador nem chamada a um modelo generativo. Por isso, erros do OCR podem afetar as sugestões, e a saída deve ser entendida como apoio, não como classificação garantida.

### 11. Montagem e apresentação do resultado

O backend mede o tempo gasto no processamento de cada imagem/página e monta uma resposta JSON com dimensões, ângulo corrigido, estado do OCR, texto, sugestões e imagens codificadas em PNG (original, tons de cinza e processada). A interface apresenta os resultados, permite consultar comparações e mantém o histórico no navegador conforme a implementação do frontend.

## Integração com a disciplina de Inteligência Artificial: Assistente de Estudos

A integração com a disciplina é o **Assistente de Estudos**: o resultado do processamento da imagem vira material de entrada para uma funcionalidade que organiza o conteúdo para revisão. A visão computacional e o OCR fazem a ponte entre o material visual e o assistente. O pipeline integrado é:

1. **Entrada:** imagem ou página de PDF com material de estudo.
2. **Preparação:** conversão para cinza, contraste, redução de ruído, binarização e alinhamento.
3. **Extração de conteúdo:** o Tesseract OCR reconhece o texto em português e inglês.
4. **Preparação para o assistente:** o backend limpa e normaliza o texto para comparar termos sem diferença de maiúsculas ou acentos.
5. **Análise e identificação do tema:** o Assistente de Estudos compara o texto com palavras-chave de disciplinas e ordena os temas por correspondências encontradas.
6. **Organização para aprendizagem:** com base no tema predominante, o assistente associa uma descrição e um conceito e seleciona um resumo e exercícios de revisão definidos para aquele assunto. Também tenta extrair linhas que possam servir como tópicos e identificar o autor.
7. **Apresentação:** o backend envia os resultados à interface, que mostra o material reconhecido junto às sugestões do Assistente de Estudos.

Na implementação atual, a análise do Assistente de Estudos usa regras e conteúdo predefinido no código; não há treinamento de modelo próprio nem chamada a um serviço generativo. Para o relatório da disciplina, descreva essa implementação como um assistente de apoio aos estudos baseado em OCR e regras de identificação temática. Essa descrição registra o que o projeto efetivamente faz e permite explicar a integração sem atribuir ao sistema um modelo que não está implementado.

## Dataset e recursos externos

O código atual não carrega um conjunto de imagens rotuladas para treinamento ou avaliação e não declara um dataset externo. Portanto, para a versão atual, a documentação correta é: **não foi utilizado dataset próprio/de treinamento**.

Os arquivos `por.traineddata` e `eng.traineddata` citados no README são modelos de idioma do Tesseract usados para OCR; não são o dataset de treinamento do classificador temático do projeto. A origem recomendada desses arquivos é o repositório oficial [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast).

## Componentes relacionados

- `backend/main.py`: endpoints, validação de upload, conversão de PDF, medição de tempo e resposta da API.
- `backend/processamento.py`: pré-processamento, correção de inclinação, OCR e regras do assistente de estudos.
- `frontend/`: interface de envio e apresentação dos resultados.
- `requirements.txt`: dependências Python. O executável Tesseract e seus modelos de idioma são requisitos externos instalados separadamente.
