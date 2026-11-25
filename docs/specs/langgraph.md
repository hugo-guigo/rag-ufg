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
START -> modelo --(pediu ferramentas)--> ferramentas --(resposta válida ou limite)--> memoria -> END
           ^  |                              |
           |  +--(texto, sem ferramenta)--+  |
           +------------------------------+--+  (volta enquanto houver passos)
```

(Desenho ajustado no bloco 1: a `responder` é executada no nó `ferramentas`, como no motor manual; ver o
registro da revisão.)

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
- 21/11/2026: projeto retomado pelo Hugo. Bloco 1 feito (função comum e grafo, com testes do LLM falso).
  Mudanças em relação à especificação, encontradas na implementação:
  - **`convert_to_openai_messages` recusado.** Conferido na versão instalada: ele descarta a chamada de
    ferramenta cujos argumentos não são JSON válido, mas mantém a `ToolMessage` dela; a API do Groq
    recusa uma resposta de ferramenta sem a chamada correspondente. O motor manual manda essas chamadas
    como vieram (e o modelo recebe "ERRO: argumentos não são JSON válido"). Agora as chamadas originais
    ficam em `additional_kwargs` da `AIMessage` e um conversor de 15 linhas (`para_api`) monta o formato
    da API; `tool_calls` e `invalid_tool_calls` continuam preenchidos para quem usa o langchain-core.
    `convert_to_messages` também não serve: levanta `JSONDecodeError` com argumentos inválidos.
  - **A `responder` é executada no nó `ferramentas`, não decidida na aresta depois do `modelo`.** No
    motor manual, a `responder` é processada junto com as outras chamadas da mesma rodada, e uma
    `responder` inválida volta para o modelo como erro. Fazer isso no mesmo nó mantém uma regra só.
  - **`recursion_limit = 2 * max_passos + 2`** (10 com o padrão), em vez de 10 fixo, para os testes com
    `max_passos` menor continuarem com a mesma folga.
  - Função comum: `executar_chamada`, `validar_final` e `concluir` saíram de dentro do `Agente` para o
    módulo; o laço manual e o grafo usam as mesmas. O cliente MCP passou a importar `validar_final`.
  - Teste de equivalência: para 6 roteiros (com ferramentas, mesmo trecho em duas buscas, argumentos
    inválidos, limite de passos, sem resposta válida, resposta em texto), os dois motores dão o mesmo
    `RespostaAgente` (sem os tempos) e mandam os mesmos pedidos ao LLM. Conferido que ele falha se o
    grafo não mandar o lembrete ou forçar a resposta um passo tarde.
  - Testes: 12 novos; 131 no total (123 passam, 8 de integração pulados sem o Postgres local; o CI roda
    os 8).
- 21/11/2026, revisão do Hugo no bloco 1: aprovado. Revisão de código automática (subagente do
  pr-review-toolkit) no commit do bloco 1: nenhum bug no bloco 1; dois avisos para o bloco 2 (tipos do
  estado no serializador do checkpointer e mensagens de turnos anteriores com rótulos antigos), os dois
  tratados abaixo; e um caso que só divergia em teoria (argumentos de ferramenta que não são texto),
  corrigido.
- 21/11/2026: bloco 2 feito (memória e API). Como ficou:
  - **Histórico fora de `messages`.** A entrada de cada turno apaga as mensagens do turno anterior
    (`RemoveMessage(REMOVE_ALL_MESSAGES)`); um campo `historico` guarda só pergunta e resposta final, até 3
    turnos, preenchido por um nó `memoria` no fim do grafo. Assim o checkpoint não acumula as saídas das
    ferramentas e o modelo nunca vê um rótulo T1 de outro turno. Um turno sem resposta válida entra com o
    "Não consegui concluir" que o estudante viu.
  - **Pergunta avulsa sem checkpoint.** O grafo é compilado duas vezes: sem checkpointer (pergunta avulsa,
    igual ao motor manual) e com checkpointer (conversa). Uma pergunta sem `thread_id` não grava nada.
  - **Serializador com lista fechada.** O checkpointer só reconstrói `Passo`, `Contagem`, `Resultado` e
    `Evento` (o padrão da biblioteca aceita qualquer classe, com aviso). Uma tupla volta como lista, sem
    efeito: só o histórico, de textos, passa de um turno para o outro.
  - **`recursion_limit`** continua `2 * max_passos + 2`: o nó `memoria` usa a folga (9 de 10 no pior caso).
  - **API:** quem cria a conversa é o cliente, gerando um UUID e mandando o mesmo `thread_id` em cada turno
    (o campo é validado como UUID: outro formato dá 422). A resposta devolve o `thread_id`. Com o motor
    `manual`, 400 antes de contar no limite e sem gravar no log. `AGENTE_MOTOR=manual|langgraph` em
    `api/servicos.py` (valor inválido derruba a subida). Até o bloco 4 a memória fica no processo
    (`InMemorySaver`) e some quando o app vai a zero réplicas; a demo continua no motor `manual`.
  - Limitação conhecida: dois turnos simultâneos na mesma conversa não são serializados (o segundo pode
    não ver o primeiro). Para um estudante digitando, não acontece; fica registrado.
  - Testes: 12 novos (8 do grafo, 4 da API); 143 no total (135 passam, 8 de integração pulados sem o
    Postgres local). Conferido que falham se a entrada não apagar as mensagens antigas, se o histórico
    não tiver limite ou se o checkpointer usar o serializador padrão.
- 24/11/2026, revisão do Hugo: bloco 2 aprovado. **Correção do registro do bloco 1:** ali está escrito que
  "o CI roda os 8" testes de integração. Não roda: o job de testes não define `RODAR_INTEGRACAO`, e o job
  da imagem só confere `/health` e o 401 do `/mcp`. Os 8 foram rodados localmente em 24/11/2026, com o
  Postgres do docker compose: 8 passam.
- 23 e 24/11/2026: bloco 3 em andamento. `--motor` nos scripts de avaliação (a rodada de 30/09 fica como
  registro), `scripts/avaliar_conversas.py`, `scripts/comparar_motores.py` e 11 conversas em
  `dados/conversas.json` (rascunho do Claude, aguardando a revisão do Hugo). Rodadas nas 60 perguntas, nos
  mesmos dias, no plano grátis do Groq:
  - 50 anotadas: correta 42/50 (manual) e 43/50 (langgraph); correta ou parcial 46/50 nos dois; fiel
    36/42 e 37/42; ferramenta certa 42/42 nos dois; 2,18 chamadas ao LLM por pergunta nos dois.
  - 10 em linguagem de aluno: correta 3/10 e 4/10; o conjunto continua fraco nos dois motores (a busca
    é o gargalo, como em 30/09).
  - As perguntas em que só um acertou (c04; r17, r24, t09) mostram a variação do modelo, não do motor:
    na c04, os dois mandaram o mesmo primeiro pedido e o modelo escolheu intervalos de datas diferentes.
- 24/11/2026: parte do bloco 4 adiantada a pedido do Hugo (não depende dos resultados): memória no
  Postgres (`rag/memoria.py`, `scripts/preparar_memoria.py`), limpeza das conversas com mais de 7 dias ao
  subir a API, `langgraph-checkpoint-postgres==3.2.1` no `requirements-api.txt` (faltava) e 3 testes de
  integração (a conversa continua depois de reiniciar o app; a limpeza apaga só as antigas; o app não
  cria tabelas), que passam a rodar no CI. O motor padrão continua `manual`; o Neon e o deploy esperam a
  aprovação dos resultados. Testes: 150 no total, todos passando com `RODAR_INTEGRACAO=1` no Postgres local.
- 25/11/2026, revisão do Hugo nas conversas: as 11 de `dados/conversas.json` (esboçadas pelo Claude)
  foram revisadas e aprovadas pelo Hugo sem mudanças.
- 25/11/2026: dia 3 feito (`scripts/avaliar_conversas.py`, os dois motores no mesmo dia, Postgres local
  desligado depois). 11 conversas, 24 turnos, 13 de acompanhamento. Relatório em `resultados/conversas.md`.

  | Métrica | manual | langgraph |
  |---|---|---|
  | Primeiro turno: correta | 10/11 | 10/11 |
  | Acompanhamento: correta | 7/13 | 8/13 |
  | Acompanhamento: correta ou parcial | 7/13 | 9/13 |
  | Acompanhamento: "não sei" | 3/13 | 2/13 |
  | Tokens de entrada por turno (acompanhamento) | 3.149 | 3.045 |

  - A memória acertou 3 turnos que dependem do turno anterior e que o manual errou (v04 e v05 corretas,
    v06 parcial com os 100% do estágio). Errou 1 que o manual acertou (v10: disse que havia feriado na
    semana; o manual acertou sem citar fonte). Os dois erraram v01, v07 e v09 t3.
  - O manual acertou 7 acompanhamentos sem memória: perguntas como "quantas vezes posso fazer isso?"
    levaram a busca ao mesmo assunto por acaso do texto. Por isso a diferença é menor que a esperada.
  - **Conclusão honesta:** com 13 turnos, 8 contra 7 (ou 9 contra 7 com parciais) é diferença de 1 ou 2
    turnos, dentro da variação do modelo vista nos dias 1 e 2. Não dá para afirmar que a memória melhora a
    taxa de acerto; dá para mostrar os 3 casos em que o contexto foi o que fez a diferença, e que a memória
    não aumentou o custo (o histórico tem só pergunta e resposta final). Juiz LLM (gpt-oss-120b), sem revisão manual
    das 48 decisões (24 turnos x 2 motores).
