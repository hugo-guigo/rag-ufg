# Exemplo real: o servidor MCP no Claude Code

Rodado em 17/11/2026 com o Claude Code 2.1.296, em modo não interativo, com o servidor em stdio sobre o
banco local (o mesmo conteúdo do Neon). Só as duas ferramentas do servidor foram liberadas:

```bash
claude -p "Pelo regulamento da UFG, quantas vezes posso trancar a matrícula no curso? E qual é o prazo de \
trancamento em 2026/2? Use as ferramentas do servidor assistente-ufg e cite o artigo e a data." \
  --mcp-config .mcp.json --strict-mcp-config \
  --allowedTools mcp__assistente-ufg__buscar_regulamento mcp__assistente-ufg__consultar_calendario \
  --output-format stream-json --verbose
```

No `.mcp.json` usado, o `command` era o caminho do Python da `.venv`; o do repositório usa `python`, que
precisa ser o da `.venv` ativada.

## O que aconteceu

O Claude Code conectou ao servidor (`assistente-ufg`, status `connected`), encontrou as duas ferramentas
e fez estas chamadas:

1. `buscar_regulamento` com `{"pergunta": "quantas vezes posso trancar a matrícula no curso"}`: voltaram
   os trechos dos Art. 72, 73 e 74, entre outros, com rótulo e página.
2. `consultar_calendario` com `{"termo": "trancamento de matrícula 2026/2"}`: voltaram os eventos de
   trancamento do calendário, com datas e página.

4 turnos, 14,9 s no total.

## Resposta (como veio, sem edição)

> Consultei as duas ferramentas do servidor assistente-ufg.
>
> **Quantas vezes você pode trancar**
>
> No máximo **4 semestres letivos**, seguidos ou alternados (RGCG, Art. 73, p. 24). Cada trancamento
> vale por um semestre só, e esse semestre não entra na contagem do prazo de integralização do curso
> (RGCG, Art. 72, §§ 1º e 2º, p. 23-24).
>
> Ressalvas que o regulamento faz:
> - **Exceção ao limite:** se uma disciplina que você precisa para se formar não for oferecida naquele
>   semestre, você pode trancar mesmo já tendo usado os 4 (Art. 73, § 2º).
> - **Extensão:** no semestre trancado você não pode participar de ação de extensão, e as horas que já
>   fez nele não são validadas, nem em parte (Art. 73, § 1º).
> - **Turmas especiais:** em cursos oferecidos por convênio, o trancamento é proibido, a não ser que o
>   edital do processo seletivo permita (Art. 74, p. 24).
>
> **Prazo de trancamento em 2026/2**
>
> O pedido é feito pelo Portal do Discente, em dois momentos:
> 1. **15/07/2026 a 22/07/2026**, seguindo o escalonamento divulgado pela UFG (Calendário 2026, p. 13).
> 2. **27/07/2026 a 24/09/2026** (Calendário 2026, p. 14).
>
> Hoje é 17/11/2026, então **os dois prazos de 2026/2 já fecharam**. Para trancar agora, só no período
> de 2027/1, que posso buscar no calendário se você quiser.
>
> Um aviso honesto: essas respostas vêm só dos trechos que a busca devolveu. A busca não encontrou
> nenhum caso especial de trancamento fora do prazo. Antes de decidir, confirme com a coordenação do
> curso ou com a PROGRAD.

Uma execução só, com um modelo maior que o gpt-oss-20b do cliente próprio. Serve para mostrar o servidor
funcionando num cliente MCP de mercado, não como avaliação da qualidade das respostas.
