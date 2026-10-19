# Avaliação do OCR em português brasileiro

Este protocolo acrescenta uma avaliação com páginas reais em português ao estudo já feito com o FUNSD. O conjunto escolhido é o **BRESSAY**, de ensaios manuscritos brasileiros: são 1.000 páginas escaneadas, com transcrições e partições de treino, validação e teste. A página do conjunto informa que as imagens têm estilos de escrita e condições variadas. O arquivo completo tem cerca de 1,5 GB.

- [Página e descrição do BRESSAY/ICDAR 2024](https://icdar2024.ecomp.poli.br/dataset)
- [Registro do conjunto no Zenodo](https://zenodo.org/records/11637681)
- Referência: NETO, Arthur F. S. et al. *BRESSAY: A Brazilian Portuguese Dataset for Offline Handwritten Text Recognition*. ICDAR 2024.

**Limite de escopo:** o BRESSAY é manuscrito. Ele testa português brasileiro e imagens de páginas reais, mas não representa diretamente apostilas impressas. Como o NeXo usa Tesseract, os resultados servem como avaliação externa de estresse, não como estimativa de desempenho em material impresso de estudo. O registro consultado não deixa clara uma licença de redistribuição; confirme os direitos e as condições de uso com os autores antes de publicar ou redistribuir dados. Este repositório não inclui as imagens nem as transcrições do BRESSAY.

## Reproduzir

1. Baixe o arquivo `bressay.zip` pelo registro oficial e extraia em uma pasta fora do repositório. Não é necessário instalar o projeto pySarah.
2. Confirme a estrutura abaixo e instale os requisitos do projeto, o Tesseract e o modelo de idioma `por`.
3. Rode primeiro um piloto com poucas páginas; o conjunto completo pode levar bastante tempo no Tesseract.

```text
<pasta BRESSAY>/
  sets/test.txt
  data/pages/<id>.png
  data/pages/<id>.txt
```

```powershell
python tools/avaliar_ocr_ptbr.py --dataset-root "D:\datasets\bressay" --split test --limit 20
python tools/avaliar_ocr_ptbr.py --dataset-root "D:\datasets\bressay" --split test
```

O script usa a partição `test` do BRESSAY ou todas as linhas do manifesto local, compara OCR direto e pipeline do NeXo com os mesmos idiomas e `--psm 6`, e grava CER/WER por página ao lado dos dados ou no caminho definido por `--output`. Também imprime intervalo de confiança bootstrap de 95% para as médias e para a diferença pareada (pipeline menos OCR direto). Os resultados gerados não devem ser incluídos no Git se revelarem transcrições protegidas ou contrariem os termos do conjunto.

O CER (taxa de erro de caracteres) e WER (taxa de erro de palavras) usam distância de Levenshtein; valores menores são melhores. A comparação ignora maiúsculas/minúsculas, normaliza Unicode e espaços e remove marcadores de trechos ilegíveis documentados pelo BRESSAY. Palavras riscadas legíveis permanecem na referência. A agregação reportada é a média simples por página; publique também os valores por página e descreva qualquer exclusão.

## Coleta complementar de material impresso de estudo

Para medir o caso de uso principal, o BRESSAY deve ser acompanhado por um pequeno conjunto próprio de páginas impressas em português. Colete de preferência 30 ou mais páginas de fontes e disciplinas variadas, com autorização do titular dos direitos e sem nomes, notas, e-mails ou outros dados pessoais visíveis. Fotografe ou digitalize cada página e faça uma transcrição manual corrigida por uma segunda leitura. Separe por **documento** antes de escolher parâmetros: páginas do mesmo documento não podem cair em treino e teste.

Antes de coletar trabalhos de estudantes, obtenha autorização do responsável pela disciplina e siga o procedimento ético exigido pela instituição. Use o [termo de participação](modelos/termo_participacao_estudo.md) como rascunho, não como aprovação ética. O modelo de planilha é [manifesto_ptbr.csv](modelos/manifesto_ptbr.csv). Guarde imagens e transcrições fora do Git, com acesso restrito, e publique apenas estatísticas agregadas quando houver autorização.

Para comparar condições, use a mesma imagem e a mesma configuração de OCR. Reporte número de páginas, origem/tipo (impresso/manuscrito), condições de captura, idioma do Tesseract, CER e WER por página e média com intervalo de confiança obtido por reamostragem pareada de páginas. Não ajuste parâmetros no conjunto de teste.


Para páginas impressas coletadas com autorização, copie o modelo `docs/modelos/manifesto_ptbr.csv` para a pasta privada do conjunto e preencha `arquivo_imagem` e `arquivo_transcricao` com caminhos relativos ao CSV e `split` com `training`, `validation` ou `test`. Distribua documentos inteiros por partição (campo `documento_grupo`) e não ajuste parâmetros com o split `test`. Rode um piloto com `python tools/avaliar_ocr_ptbr.py --manifest-csv D:\estudo-privado\manifesto.csv --limit 10`. O manifesto e os dados individuais devem ficar fora do Git.
