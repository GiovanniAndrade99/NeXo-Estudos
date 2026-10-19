# Protocolo de avaliação com estudantes

## Objetivo

Investigar se o NeXo Estudos é fácil de usar e se os recursos de OCR, resumo e exercícios apoiam uma sessão curta de revisão. Este documento é um protocolo e um conjunto de instrumentos: ainda não há participantes nem resultados coletados.

## Desenho recomendado

Faça um estudo piloto exploratório com 8 a 12 estudantes adultos que usem português como idioma de estudo. Esse tamanho ajuda a encontrar problemas de interface; não dá, por si só, poder estatístico para afirmar que o produto melhora a aprendizagem. Para uma conclusão confirmatória, defina antes a hipótese, o efeito mínimo relevante e o tamanho amostral com orientação do professor/orientador.

Use um desenho cruzado com dois tópicos de dificuldade semelhante. Sorteie a ordem das condições entre participantes:

| Condição | Atividade |
|---|---|
| NeXo | Enviar uma página autorizada, revisar o OCR, ler o resumo e responder aos exercícios. |
| Comparação | Estudar uma página equivalente pelo método habitual, durante o mesmo tempo, sem o assistente. |

Não use o mesmo conteúdo nas duas condições: isso mistura o efeito da ferramenta com memória do primeiro bloco. Alterne os tópicos e a ordem entre participantes. Use um pré-teste curto antes de cada bloco, um pós-teste equivalente logo depois e, se viável, um teste de retenção após sete dias. As perguntas e respostas devem ser preparadas por alguém com domínio do conteúdo e revisadas quanto à equivalência.

## Roteiro de sessão

1. Explique o estudo, a voluntariedade, a possibilidade de parar sem prejuízo e o que será registrado. Obtenha consentimento antes de começar.
2. Atribua um código aleatório ao participante. Não registre nome, e-mail, matrícula, senha ou imagem de documento pessoal.
3. Faça um bloco de familiarização de até dois minutos com um material de exemplo que não será avaliado.
4. Aplique pré-teste, atividade de estudo cronometrada (sugestão: 8 minutos) e pós-teste para cada condição.
5. Registre sucesso/erro nas tarefas e tempo. Após usar o NeXo, aplique o questionário SUS e as perguntas complementares.
6. Se fizer o teste de retenção, recolha somente o código aleatório e as respostas, sem dados de identificação.

## Tarefas observáveis no NeXo

- Enviar uma imagem de estudo e localizar o texto reconhecido.
- Identificar uma palavra sinalizada como incerta e conferir a imagem original.
- Localizar o resumo e responder aos exercícios sem consultar o gabarito primeiro.
- Explicar se o OCR ou o resumo apresentou algo que precisou de correção.

Registre conclusão, número de erros observáveis e tempo por tarefa. Não grave tela, voz ou imagem dos participantes sem autorização explícita e aprovação institucional aplicável.

## Instrumento SUS

Use as dez afirmações padrão do System Usability Scale (SUS), com respostas de 1 (discordo totalmente) a 5 (concordo totalmente), alternando afirmações positivas e negativas:

1. Eu gostaria de usar este sistema com frequência.
2. Achei o sistema desnecessariamente complexo.
3. Achei o sistema fácil de usar.
4. Acho que precisaria do apoio de uma pessoa técnica para conseguir usar este sistema.
5. Achei que as funções do sistema estavam bem integradas.
6. Achei que havia inconsistência demais neste sistema.
7. Imagino que a maioria das pessoas aprenderia a usar este sistema rapidamente.
8. Achei o sistema muito difícil de usar.
9. Senti confiança ao usar o sistema.
10. Precisei aprender muitas coisas antes de conseguir começar a usar o sistema.

Pontuação SUS: itens ímpares recebem resposta menos 1; itens pares recebem 5 menos a resposta. Some os dez valores e multiplique por 2,5. O resultado varia de 0 a 100 e **não é porcentagem de aprovação**. Descreva a média, dispersão e respostas por item; evite tratar um valor isolado como prova de usabilidade.

Perguntas complementares (escala de 1 a 5 e campo livre):

- O texto extraído foi fácil de conferir?
- O destaque de confiança ajudou a encontrar possíveis erros?
- O resumo representou as ideias centrais da página?
- Os exercícios ajudaram a lembrar o conteúdo?
- O que mais atrapalhou ou ajudou na atividade?

## Análise

- **Usabilidade:** pontuação SUS por participante, média e desvio-padrão; apresente também a distribuição e comentários sem identificação.
- **Aprendizagem imediata:** diferença pós-teste menos pré-teste por participante e condição. Compare condições de forma pareada, com intervalo de confiança e método estatístico definido antes de olhar os resultados.
- **Retenção:** repita a comparação no teste de sete dias, se coletado.
- **Uso:** taxa de conclusão e mediana do tempo de cada tarefa.

Não interprete diferenças de um piloto pequeno como evidência causal ou generalizável. Relate desistências, dados ausentes, ordem das condições e qualquer desvio do protocolo. Use [quiz_pre_pos.csv](modelos/quiz_pre_pos.csv) para preparar formas equivalentes e [registro_sessao.csv](modelos/registro_sessao.csv) para registrar os dados mínimos por código; mantenha a chave de códigos separada e não a crie se não for necessária. Depois da coleta, gere estatísticas agregadas com:

```powershell
python tools/analisar_estudo.py "D:\estudo-privado\registro_sessao.csv"
```

O script calcula pontuação SUS, ganhos pré/pós, diferença pareada e conclusão/tempo de tarefas, com intervalos bootstrap descritivos. Ele grava somente um resumo agregado em `resumo_estudo.json`; o CSV bruto e o resumo devem ficar na pasta privada do estudo e fora do Git.

## Ética, privacidade e armazenamento

Antes de recrutar pessoas ou publicar dados, consulte o professor/orientador e as regras de ética da instituição. O termo em [termo_participacao_estudo.md](modelos/termo_participacao_estudo.md) é apenas um rascunho para revisão institucional. Guarde formulários assinados separados das respostas, limite acesso, defina prazo de descarte e não suba dados individuais ao repositório. O estudo pode ser executado com contas de teste e materiais de domínio público/autorizados.

## O que falta para concluir o estudo

- Aprovação/orientação ética institucional, quando exigida.
- Recrutamento e consentimento de participantes.
- Materiais equivalentes e gabaritos revisados por docente.
- Aplicação do protocolo, análise e relato dos resultados reais.
