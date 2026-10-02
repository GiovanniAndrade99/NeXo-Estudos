# Funcionamento e pipeline do NeXo Estudos

## Visão geral

O NeXo Estudos reúne duas partes do projeto: o laboratório de processamento de imagens e OCR, e o **Assistente de Estudos**, que representa a integração com o projeto desenvolvido para a disciplina de Inteligência Artificial. O laboratório prepara imagens de materiais didáticos e extrai seu texto; esse conteúdo alimenta o Assistente de Estudos, que identifica temas e apresenta apoio à revisão na interface.

O processamento é feito localmente pelo servidor da aplicação. A leitura de texto é realizada pelo Tesseract OCR, usando seus modelos de idioma português (`por`) e inglês (`eng`). A identificação da matéria usa um **classificador treinado** (TF-IDF + Regressão Logística, com dataset da Wikipédia em português), com regras de palavras-chave como reserva; o resumo é gerado por **sumarização extrativa** e os exercícios de lacuna são tirados das frases do próprio texto.

## Pipeline completo da aplicação

```text
Pessoa usuária
  → navegador envia imagem/PDF para a API
  → validação do arquivo
  → PDF: conversão de cada página para imagem
  → correção de perspectiva (foto tirada de lado)
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

As etapas 4 a 9 foram ajustadas e validadas com o dataset público FUNSD; a metodologia e os resultados estão em [AVALIACAO.md](AVALIACAO.md).

### 4. Correção de perspectiva

Quando a página é fotografada de lado, a folha aparece como um quadrilátero torto, com a mesa em volta. O sistema procura o contorno da folha e a "estica" de volta para um retângulo (`backend/perspectiva.py`):

1. Numa cópia reduzida da imagem, as bordas são detectadas com o filtro de Canny e fechadas com uma operação morfológica.
2. Entre os maiores contornos, procura o primeiro que, simplificado (`approxPolyDP`), forme um quadrilátero convexo ocupando entre 20% e 97% da foto.
3. O quadrilátero só é aceito se a área dentro dele for bem mais clara que uma faixa de fundo logo fora. Esse teste evita "corrigir" um scan comum, em que o maior retângulo costuma ser a borda de uma tabela impressa.
4. Os quatro cantos são ordenados e uma transformação de perspectiva (`getPerspectiveTransform` + `warpPerspective`) leva a folha para um retângulo do tamanho dos seus lados.

Se nenhuma folha for encontrada, a imagem segue sem alteração. A resposta da API informa se a correção foi aplicada (`perspectiva_corrigida`).

### 5. Conversão para tons de cinza e ampliação

O OpenCV converte a imagem colorida para uma matriz de intensidades em tons de cinza. Isso reduz a informação a analisar e deixa o texto mais fácil de tratar sem depender das cores originais.

Em seguida, imagens cujo maior lado tem menos de 2000 pixels são ampliadas até 2 vezes, com interpolação bicúbica. O Tesseract erra muito quando as letras têm poucos pixels de altura; na avaliação, a ampliação foi a mudança de maior impacto no acerto do OCR.

### 6. Normalização de iluminação

Fotos de páginas costumam ter sombras e luz desigual: um canto fica mais escuro que o outro. Para corrigir isso, o sistema estima o fundo da página (o papel sem o texto) e divide a imagem por ele:

1. uma dilatação 7 × 7 "apaga" as letras, que são mais escuras que o papel;
2. um filtro mediano 31 × 31 suaviza o resultado, gerando uma estimativa da iluminação de cada região;
3. a imagem original é dividida por essa estimativa.

O resultado é um fundo uniforme, com as letras preservadas. Essa etapa substituiu o CLAHE (equalização adaptativa de histograma) usado nas primeiras versões, que realçava também o ruído do fundo.

### 7. Redução de ruído

Um filtro mediano de tamanho 3 × 3 reduz pequenos pontos e imperfeições. A intenção é limpar o fundo preservando bordas, como os contornos das letras.

### 8. Binarização (método de Otsu)

O método de Otsu escolhe automaticamente o limiar que melhor separa as intensidades da imagem em dois grupos (tinta e papel) e transforma a imagem em preto e branco. Um limiar global funciona bem aqui porque a etapa 5 já deixou a iluminação uniforme. Essa imagem binária serve de entrada para o alinhamento e o OCR.

### 9. Correção de inclinação

O sistema mede o ângulo do texto pelo **perfil de projeção horizontal**: para cada ângulo testado (de −15° a 15°, primeiro de 1 em 1 grau e depois de 0,1 em 0,1 grau perto do melhor), a imagem é girada e a tinta de cada linha de pixels é somada. Quando o texto está alinhado, linhas de texto e entrelinhas alternam entre somas altas e baixas, e a variância dessas somas é máxima. Esse critério quase não é afetado por bordas, linhas de formulário ou sujeira.

Se a inclinação medida for de pelo menos 0,2°, a imagem é rotacionada para alinhar as linhas. A correção estimada, em graus, também é incluída no resultado.

### 10. Reconhecimento óptico de caracteres (OCR)

O `pytesseract` chama o executável Tesseract instalado no sistema. Por padrão, são usados os idiomas `por+eng` e o modo de segmentação `--psm 6`, apropriado para texto organizado em blocos. O texto reconhecido é devolvido ao sistema. Se o executável ou os idiomas necessários não estiverem disponíveis, a API informa o aviso e o restante do resultado pode continuar sem texto OCR.

### 11. Análise do texto para sugestões de estudo

O texto do OCR é normalizado para comparação (minúsculas e remoção de acentos) e confrontado com conjuntos de palavras-chave associados a disciplinas. As disciplinas com mais correspondências são priorizadas. A partir da categoria selecionada, o código associa uma descrição e exercícios de revisão predefinidos para o assunto.

O **resumo de estudo** é gerado a partir do próprio texto da página, por **sumarização extrativa** (`backend/resumo.py`), uma técnica clássica de Processamento de Linguagem Natural baseada na frequência de termos (Luhn, 1958, a mesma ideia do TF-IDF):

1. **Limpeza:** linhas de autor, números de página e ruído do OCR (linhas com poucas letras) são descartados.
2. **Reconstrução das frases:** o OCR devolve o texto quebrado por linha da página; as linhas são juntadas até um ponto final, a hifenização de fim de linha é desfeita e títulos curtos ficam de fora.
3. **Pontuação:** cada palavra relevante (excluindo palavras vazias como "de", "que", "o") vale a sua frequência no texto, e os termos da disciplina identificada recebem peso extra. A nota da frase é a média desses pesos, com penalidade para frases muito curtas ou muito longas.
4. **Seleção:** as frases com maior nota que cabem no limite (até 3 frases, 280 caracteres) são apresentadas na ordem original do texto.

Assim o resumo mostra frases inteiras e representativas do conteúdo, em vez de trechos cortados. Quando o OCR não fornece frases completas, o assistente usa o conceito associado à disciplina. Algumas linhas extraídas também podem ser aproveitadas como tópicos/figuras, e há uma tentativa simples de identificar o autor.

Desde a versão com classificador, a matéria é decidida por um modelo de aprendizado de máquina (TF-IDF de palavras e de n-gramas de caracteres + Regressão Logística) treinado com 1.635 trechos da Wikipédia em português. O modelo só decide quando a confiança é de pelo menos 0,4 e o texto tem 15 palavras ou mais; caso contrário, valem as regras de palavras-chave. Na avaliação, o modelo acertou 84,1% das matérias (contra 51,1% das regras) e 93,4% quando confiante, mantendo 82,9% com ruído de OCR simulado. Detalhes em [CLASSIFICADOR.md](CLASSIFICADOR.md). Não há chamada a modelo generativo: as saídas são apoio ao estudo, não classificação garantida.

### 12. Montagem e apresentação do resultado

O backend mede o tempo gasto no processamento de cada imagem/página e monta uma resposta JSON com dimensões, ângulo corrigido, estado do OCR, texto, sugestões e imagens codificadas em PNG (original, tons de cinza e processada). A interface apresenta os resultados, permite consultar comparações e mantém o histórico no navegador conforme a implementação do frontend.

## Integração com a disciplina de Inteligência Artificial: Assistente de Estudos

A integração com a disciplina é o **Assistente de Estudos**: o resultado do processamento da imagem vira material de entrada para uma funcionalidade que organiza o conteúdo para revisão. A visão computacional e o OCR fazem a ponte entre o material visual e o assistente. O pipeline integrado é:

1. **Entrada:** imagem ou página de PDF com material de estudo.
2. **Preparação:** correção de perspectiva, conversão para cinza, ampliação, normalização de iluminação, redução de ruído, binarização e alinhamento.
3. **Extração de conteúdo:** o Tesseract OCR reconhece o texto em português e inglês.
4. **Preparação para o assistente:** o backend limpa e normaliza o texto para comparar termos sem diferença de maiúsculas ou acentos.
5. **Análise e identificação do tema:** o Assistente de Estudos compara o texto com palavras-chave de disciplinas e ordena os temas por correspondências encontradas.
6. **Organização para aprendizagem:** com base no tema predominante, o assistente associa uma descrição, um conceito e exercícios de revisão definidos para aquele assunto, e gera o resumo escolhendo, por sumarização extrativa, as frases mais representativas do próprio texto reconhecido. Também tenta extrair linhas que possam servir como tópicos e identificar o autor.
7. **Apresentação:** o backend envia os resultados à interface, que mostra o material reconhecido junto às sugestões do Assistente de Estudos.

Na implementação atual, o Assistente de Estudos combina três técnicas de IA clássica, sem chamada a serviço generativo:

1. **Classificação supervisionada:** TF-IDF + Regressão Logística treinada com o dataset da Wikipédia identifica a matéria ([CLASSIFICADOR.md](CLASSIFICADOR.md)).
2. **Sumarização extrativa:** as frases mais representativas do texto, por frequência de termos, formam o resumo (`backend/resumo.py`).
3. **Geração de exercícios de lacuna:** o termo central de cada frase do resumo é escondido e vai para o gabarito (`backend/exercicios.py`).

As regras de palavras-chave continuam como reserva quando o modelo não está confiante. Para o relatório da disciplina, essa é a integração com IA: o processamento de imagens produz o texto, e as técnicas acima o transformam em material de estudo.

## Dataset e recursos externos

### Dataset utilizado: FUNSD

- **FUNSD — Form Understanding in Noisy Scanned Documents:** <https://guillaumejaume.github.io/FUNSD/>
- Download direto: <https://guillaumejaume.github.io/FUNSD/dataset.zip>
- Licença (uso não comercial, de pesquisa e educacional): <https://guillaumejaume.github.io/FUNSD/work/>

O FUNSD reúne 199 formulários reais digitalizados, com o texto de cada palavra anotado manualmente. O projeto o usa para **ajustar e avaliar** o pipeline de processamento de imagens: as 149 imagens de treino serviram para escolher os parâmetros, e as 50 de teste medem o ganho do pré-processamento no OCR, comparando o texto reconhecido com o anotado. O processo e os resultados estão em [AVALIACAO.md](AVALIACAO.md). No conjunto de teste, o pipeline elevou o F1 das palavras reconhecidas de 61,3% para 72,1% nos scans e de 32,4% para 67,6% em fotos simuladas.

O FUNSD é usado como conjunto de validação do pré-processamento (não há treino com ele). O dataset não é redistribuído no repositório; o script `tools/avaliar_ocr.py` o baixa da fonte oficial.

### Dataset do classificador de matérias: Wikipédia em português

- Arquivo versionado: [`datasets/materias_wikipedia.jsonl`](../datasets/materias_wikipedia.jsonl), 1.635 trechos em 16 matérias.
- Fonte: <https://pt.wikipedia.org/> (API pública do MediaWiki), licença CC BY-SA 4.0; atribuição em [`datasets/README.md`](../datasets/README.md).
- Uso: treinar e avaliar o classificador de matérias do Assistente de Estudos (TF-IDF + Regressão Logística). Acurácia de 84,1% contra 51,1% das regras de palavras-chave; detalhes em [CLASSIFICADOR.md](CLASSIFICADOR.md).

### Modelos de idioma do OCR

Os arquivos `por.traineddata` e `eng.traineddata` citados no README são modelos de idioma do Tesseract já treinados pelos autores do Tesseract e usados para o OCR. A origem recomendada desses arquivos é o repositório oficial [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast).

## Componentes relacionados

- `backend/main.py`: endpoints, validação de upload, conversão de PDF, medição de tempo e resposta da API.
- `backend/processamento.py`: pré-processamento, correção de inclinação, OCR e regras do assistente de estudos.
- `frontend/laboratorio/`: interface de envio e apresentação dos resultados.
- `tools/avaliar_ocr.py`: avaliação do pipeline com o dataset FUNSD.
- `requirements.txt`: dependências Python. O executável Tesseract e seus modelos de idioma são requisitos externos instalados separadamente.
