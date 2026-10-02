# Datasets

## `materias_wikipedia.jsonl` — classificador de matérias

Trechos de texto em português rotulados por matéria, usados para treinar e avaliar o
classificador do Assistente de Estudos (`backend/classificador.py`, métricas em
[`docs/CLASSIFICADOR.md`](../docs/CLASSIFICADOR.md)).

- **Fonte:** introduções de artigos da [Wikipédia em português](https://pt.wikipedia.org/), obtidas pela
  [API pública do MediaWiki](https://pt.wikipedia.org/w/api.php) a partir de categorias ligadas a cada matéria
  (lista em `tools/montar_dataset_materias.py`).
- **Licença:** o texto da Wikipédia é distribuído sob a
  [Creative Commons Atribuição-CompartilhaIgual 4.0 (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/deed.pt_BR).
  Este arquivo é uma obra derivada (trechos de até 120 palavras) e segue a mesma licença. A autoria de cada
  trecho pertence aos editores do artigo indicado no campo `artigo`, cujo histórico pode ser consultado em
  `https://pt.wikipedia.org/wiki/<artigo>`.
- **Formato:** uma linha JSON por trecho: `{"materia": "...", "artigo": "...", "texto": "..."}`.
- **Como gerar de novo:** `python tools/montar_dataset_materias.py` (o conteúdo da Wikipédia muda com o tempo,
  então uma nova coleta pode ter pequenas diferenças).

## `funsd/` — avaliação do OCR (não versionado)

O FUNSD é baixado da fonte oficial por `tools/avaliar_ocr.py`; a licença dele não permite redistribuição.
Detalhes em [`docs/AVALIACAO.md`](../docs/AVALIACAO.md).
