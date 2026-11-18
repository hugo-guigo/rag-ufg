# Especificação: segundo motor do agente em LangGraph, com conversa e memória

Escrita antes do código (18/11/2026). O registro da revisão fica no fim e é preenchido durante o trabalho.

## Objetivo

Um segundo motor do agente, em LangGraph, com as mesmas ferramentas e o mesmo `RespostaAgente`,
escolhido por `AGENTE_MOTOR=manual|langgraph` (padrão `manual`). Duas entregas: uma comparação medida
entre os dois motores nos mesmos conjuntos e uma capacidade nova, a conversa com memória (perguntas de
acompanhamento na mesma conversa). O resultado esperado não é "LangGraph é melhor"; é saber, com números,
o que muda.

## Fora do escopo

- Mudar as ferramentas, a busca ou o prompt. Os dois motores usam exatamente as mesmas, para a
  comparação medir só o motor.
- Trocar o padrão da demo antes de você aprovar os resultados.
- O MCP: o servidor MCP expõe as buscas, não o agente, então o motor não muda nada nele.

## Versões (conferidas na API instalada, 18/11/2026)

`langgraph` 1.2.22, `langchain-core` 1.8.3, `langgraph-checkpoint-postgres` 3.2.1. Instalam sem mexer em
nenhuma versão fixada hoje.

## O grafo

```text
START -> modelo --(chamou responder)--------> END
           |  ^
           |  +--(sem ferramenta: pede para usar)--+
           |                                       |
           +--(pediu ferramentas)--> ferramentas --+
```

- **Estado** (`TypedDict`): `messages` com o redutor `add_messages` (cada nó devolve só as mensagens
  novas, o redutor junta); `passos` (chamadas ao LLM neste turno); `rotulados` (T1, E1... deste turno);
  `final` (a resposta validada, quando vier); contadores de tokens, tempos e erros, para montar o
  `RespostaAgente` igual ao de hoje.
- **Nó `modelo`**: chama o LLM com as ferramentas; na última volta, força a ferramenta `responder`, como o
  motor manual faz.
- **Nó `ferramentas`**: executa as chamadas pedidas e devolve um `ToolMessage` por chamada.
- **Aresta condicional** depois de `modelo`: `responder` válida vai para `END`; pedido de ferramenta vai
  para `ferramentas`; resposta em texto, sem ferramenta, volta para `modelo` com o lembrete de usar as
  ferramentas.

## Decisões (com a alternativa recusada)

1. **O nó `modelo` chama o `ClienteGroq` de hoje, não o `ChatGroq` do LangChain.** O mesmo cliente
   mantém o controle de ritmo do plano grátis, o conserto do nome de ferramenta do gpt-oss e a mesma
   contagem de tokens. Com o `ChatGroq` + `bind_tools`, que é o caminho comum, a comparação mudaria duas
   coisas ao mesmo tempo (o motor e o cliente HTTP) e não daria para atribuir a diferença. As mensagens
   do estado são do `langchain-core` (é o que o `add_messages` e o corte de histórico esperam) e viram o
   formato da API do Groq na chamada (`convert_to_openai_messages`).
2. **Nó de ferramentas próprio, não o `ToolNode` pronto nem o `create_react_agent`.** Os rótulos T1/E1
   estáveis entre passos, as mensagens de `ErroFerramenta` e a validação da `responder` são do projeto;
   o `ToolNode` espera ferramentas do LangChain e exigiria reembrulhar tudo isso. O `create_react_agent`
   esconde o grafo, que é justamente o que o projeto quer mostrar. Para não duplicar regra, a execução das
   ferramentas sai de dentro do `Agente` para uma função comum, usada pelos dois motores.
3. **Limite de passos no estado, e `recursion_limit` explícito como rede de segurança.** O contador
   `passos` reproduz o `MAX_PASSOS = 4` de hoje: na quarta chamada ao LLM a resposta é forçada, então o
   grafo sempre termina com uma resposta. O `recursion_limit` sozinho não serve: estourar levanta
   `GraphRecursionError`, sem resposta para o estudante. E o padrão dele nesta versão é 10.007 (era 25
   nas antigas), então ele é fixado em 10 (4 voltas de modelo e ferramentas, com folga) para pegar um bug
   que fizesse o contador não andar.
4. **Memória: `thread_id` por conversa e checkpointer.** O estado de cada conversa fica salvo por
   `thread_id`; a pergunta seguinte continua dali.
5. **O que o modelo vê de turnos anteriores: só pergunta e resposta final, até 3 turnos.** As saídas
   das ferramentas de turnos passados não voltam ao modelo: cada busca devolve cerca de 1.200 tokens, e
   com o limite de 8 mil tokens por minuto do plano grátis do Groq a terceira pergunta já travaria. A
   resposta anterior carrega o que importa para o acompanhamento ("e no segundo semestre?"). Se o modelo
   precisar de um trecho de novo, ele busca de novo. Os rótulos recomeçam a cada turno (T1 é deste turno).
   Recusado: mandar o histórico inteiro; recusado também resumir com o LLM, que gastaria uma chamada a
   mais por turno.
6. **Checkpointer em memória nos testes e na avaliação; no Postgres (Neon) na demo.** Em memória a
   conversa se perde quando o app vai a zero réplicas (depois de uns 5 minutos parado), o que tornaria a
   memória inútil na demo. No Neon: conexão própria com `prepare_threshold=None` (o pooler não guarda
   comandos preparados, e o `from_conn_string` do pacote liga isso); as 4 tabelas do checkpointer criadas
   pelo admin com `setup()`, e o usuário `app` só com as permissões que o checkpointer usa. Os checkpoints
   crescem a cada turno: uma limpeza das conversas com mais de 7 dias entra junto. Se o Postgres complicar
   além disso, fica documentado e a demo fica sem memória.
7. **API: `thread_id` opcional no `POST /perguntar`.** Sem ele, o comportamento de hoje. Com ele, e motor
   `langgraph`, a conversa continua; com ele e motor `manual`, 400 dizendo que a conversa exige o outro
   motor (melhor que ignorar em silêncio). A resposta devolve o `thread_id` para o cliente mandar no turno
   seguinte. Cada turno conta no limite diário como uma pergunta.
8. **Avaliação com cache por motor e em lotes.** Os scripts ganham `--motor`; cada resposta fica em
   `resultados/agente/<motor>/<conjunto>.jsonl` e o script retoma de onde parou. A data de "hoje" continua
   fixa, como na avaliação atual.

## Avaliação

| Conjunto | O que mede |
|---|---|
| 50 perguntas anotadas | acerto pelo juiz (`rag/juiz.py`), tokens, latência p50/p95, passos, erros de ferramenta, ferramenta certa |
| 10 em linguagem de aluno | o mesmo |
| ~10 conversas de 2 a 3 turnos (novas) | a pergunta de acompanhamento respondida certo: LangGraph com memória x motor manual com a pergunta sozinha |

**Rodar o motor manual de novo, não reaproveitar a rodada de 30/09.** O modelo do Groq pode ter mudado
desde então; os dois motores precisam rodar nos mesmos dias para a diferença ser do motor.

**Cota do Groq (plano grátis).** O gpt-oss-20b tem 200 mil tokens por dia. Cada pergunta do agente gasta
cerca de 3 mil: as 60 perguntas são ~180 mil por motor, e as conversas mais ~100 mil. São cerca de 3 dias
de cota, rodando um lote por dia. A demo usa a mesma cota: nos dias de avaliação ela pode responder 503
depois do lote. O juiz (gpt-oss-120b) tem limite próprio.

## Testes (com LLM falso, sem cota)

Caminho com ferramenta; sem ferramenta (resposta em texto e o lembrete); erro de ferramenta; estouro do
limite de passos (resposta forçada); conversa de dois turnos com o checkpointer em memória (o segundo turno
vê a pergunta e a resposta do primeiro, e não as saídas de ferramenta); mesmo `RespostaAgente` dos dois
motores para o mesmo roteiro; API com e sem `thread_id`. Os 119 testes de hoje continuam passando.

## Blocos (com a sua revisão entre eles)

1. Função comum de execução das ferramentas e o grafo, com os testes do LLM falso.
2. Memória: checkpointer, histórico limitado, conversa de dois turnos; API com `thread_id`.
3. Avaliação: `--motor`, as conversas e as rodadas (cerca de 3 dias de cota).
4. Postgres no Neon, deploy (só com a sua aprovação dos resultados), README, guia de estudo, linha do CV e
   parágrafo de LinkedIn e portfólio.

## Riscos

- A API do LangGraph muda entre versões: tudo conferido no código instalado, versões fixadas.
- Cota do Groq: a avaliação leva dias, e a demo divide a cota.
- Conjunto de conversas pequeno: serve para mostrar a capacidade, não para medir com precisão.

## Registro da revisão

- 18/11/2026, revisão do Hugo: especificação aprovada. As conversas de teste serão esboçadas pelo Claude e
  revisadas pelo Hugo, e o arquivo vai dizer isso. Os cerca de 3 dias de cota do Groq, com a demo podendo
  responder 503 depois de cada lote, estão aceitos. Projeto pausado antes do bloco 1, por decisão do Hugo.
