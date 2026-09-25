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

As etapas 4 a 8 foram ajustadas e validadas com o dataset público FUNSD; a metodologia e os resultados estão em [AVALIACAO.md](AVALIACAO.md).

### 4. Conversão para tons de cinza e ampliação

O OpenCV converte a imagem colorida para uma matriz de intensidades em tons de cinza. Isso reduz a informação a analisar e deixa o texto mais fácil de tratar sem depender das cores originais.

Em seguida, imagens cujo maior lado tem menos de 2000 pixels são ampliadas até 2 vezes, com interpolação bicúbica. O Tesseract erra muito quando as letras têm poucos pixels de altura; na avaliação, a ampliação foi a mudança de maior impacto no acerto do OCR.

### 5. Normalização de iluminação

Fotos de páginas costumam ter sombras e luz desigual: um canto fica mais escuro que o outro. Para corrigir isso, o sistema estima o fundo da página (o papel sem o texto) e divide a imagem por ele:

1. uma dilatação 7 × 7 "apaga" as letras, que são mais escuras que o papel;
2. um filtro mediano 31 × 31 suaviza o resultado, gerando uma estimativa da iluminação de cada região;
3. a imagem original é dividida por essa estimativa.

O resultado é um fundo uniforme, com as letras preservadas. Essa etapa substituiu o CLAHE (equalização adaptativa de histograma) usado nas primeiras versões, que realçava também o ruído do fundo.

### 6. Redução de ruído

Um filtro mediano de tamanho 3 × 3 reduz pequenos pontos e imperfeições. A intenção é limpar o fundo preservando bordas, como os contornos das letras.

### 7. Binarização (método de Otsu)

O método de Otsu escolhe automaticamente o limiar que melhor separa as intensidades da imagem em dois grupos (tinta e papel) e transforma a imagem em preto e branco. Um limiar global funciona bem aqui porque a etapa 5 já deixou a iluminação uniforme. Essa imagem binária serve de entrada para o alinhamento e o OCR.

### 8. Correção de inclinação

O sistema mede o ângulo do texto pelo **perfil de projeção horizontal**: para cada ângulo testado (de −15° a 15°, primeiro de 1 em 1 grau e depois de 0,1 em 0,1 grau perto do melhor), a imagem é girada e a tinta de cada linha de pixels é somada. Quando o texto está alinhado, linhas de texto e entrelinhas alternam entre somas altas e baixas, e a variância dessas somas é máxima. Esse critério quase não é afetado por bordas, linhas de formulário ou sujeira.

Se a inclinação medida for de pelo menos 0,2°, a imagem é rotacionada para alinhar as linhas. A correção estimada, em graus, também é incluída no resultado.

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
2. **Preparação:** conversão para cinza, ampliação, normalização de iluminação, redução de ruído, binarização e alinhamento.
3. **Extração de conteúdo:** o Tesseract OCR reconhece o texto em português e inglês.
4. **Preparação para o assistente:** o backend limpa e normaliza o texto para comparar termos sem diferença de maiúsculas ou acentos.
5. **Análise e identificação do tema:** o Assistente de Estudos compara o texto com palavras-chave de disciplinas e ordena os temas por correspondências encontradas.
6. **Organização para aprendizagem:** com base no tema predominante, o assistente associa uma descrição e um conceito e seleciona um resumo e exercícios de revisão definidos para aquele assunto. Também tenta extrair linhas que possam servir como tópicos e identificar o autor.
7. **Apresentação:** o backend envia os resultados à interface, que mostra o material reconhecido junto às sugestões do Assistente de Estudos.

Na implementação atual, a análise do Assistente de Estudos usa regras e conteúdo predefinido no código; não há treinamento de modelo próprio nem chamada a um serviço generativo. Para o relatório da disciplina, descreva essa implementação como um assistente de apoio aos estudos baseado em OCR e regras de identificação temática. Essa descrição registra o que o projeto efetivamente faz e permite explicar a integração sem atribuir ao sistema um modelo que não está implementado.

## Dataset e recursos externos

### Dataset utilizado: FUNSD

- **FUNSD — Form Understanding in Noisy Scanned Documents:** <https://guillaumejaume.github.io/FUNSD/>
- Download direto: <https://guillaumejaume.github.io/FUNSD/dataset.zip>
- Licença (uso não comercial, de pesquisa e educacional): <https://guillaumejaume.github.io/FUNSD/work/>

O FUNSD reúne 199 formulários reais digitalizados, com o texto de cada palavra anotado manualmente. O projeto o usa para **ajustar e avaliar** o pipeline de processamento de imagens: as 149 imagens de treino serviram para escolher os parâmetros, e as 50 de teste medem o ganho do pré-processamento no OCR, comparando o texto reconhecido com o anotado. O processo e os resultados estão em [AVALIACAO.md](AVALIACAO.md). No conjunto de teste, o pipeline elevou o F1 das palavras reconhecidas de 61,3% para 72,1% nos scans e de 32,4% para 67,6% em fotos simuladas.

O projeto **não treina** um modelo próprio: o FUNSD é usado como conjunto de validação do pré-processamento. O dataset não é redistribuído no repositório; o script `tools/avaliar_ocr.py` o baixa da fonte oficial.

### Modelos de idioma do OCR

Os arquivos `por.traineddata` e `eng.traineddata` citados no README são modelos de idioma do Tesseract já treinados pelos autores do Tesseract e usados para o OCR. A origem recomendada desses arquivos é o repositório oficial [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast).

## Componentes relacionados

- `backend/main.py`: endpoints, validação de upload, conversão de PDF, medição de tempo e resposta da API.
- `backend/processamento.py`: pré-processamento, correção de inclinação, OCR e regras do assistente de estudos.
- `frontend/`: interface de envio e apresentação dos resultados.
- `tools/avaliar_ocr.py`: avaliação do pipeline com o dataset FUNSD.
- `requirements.txt`: dependências Python. O executável Tesseract e seus modelos de idioma são requisitos externos instalados separadamente.
