# Conversa com memória: motor langgraph x motor manual

Gerado por scripts/avaliar_conversas.py com dados/conversas.json (conversas esboçadas pelo Claude e revisadas pelo Hugo). O manual recebe cada pergunta sozinha; o langgraph, a conversa inteira (até 3 turnos anteriores, só pergunta e resposta final). Juiz: openai/gpt-oss-120b, com a conversa anterior nas respostas de referência.

| Métrica | manual | langgraph |
|---|---|---|
| Conversas | 11 | 11 |
| Primeiro turno: correta | 10/11 (91%) | 10/11 (91%) |
| Acompanhamento: correta | 7/13 (54%) | 8/13 (62%) |
| Acompanhamento: correta ou parcial | 7/13 (54%) | 9/13 (69%) |
| Acompanhamento: "não sei" | 3/13 (23%) | 2/13 (15%) |
| Tokens de entrada por turno (acompanhamento) | 3149 | 3045 |

## Turnos de acompanhamento

- **v01, turno 2**: E quando ele termina?
  - manual: correta=nao, cobertura=total. A resposta não fornece a data de término solicitada, embora as informações citadas estejam corretas segundo o regulamento.
  - langgraph: correta=nao, cobertura=nenhuma. A resposta contradiz a referência que indica 12 de dezembro de 2026 como data de término.
- **v02, turno 2**: E quantas vezes posso fazer isso durante o curso?
  - manual: correta=sim, cobertura=total. A resposta repete exatamente a informação da referência e está totalmente sustentada pelo artigo citado.
  - langgraph: correta=sim, cobertura=total. A resposta repete exatamente a informação da referência e está respaldada pelo Art. 73 citado.
- **v02, turno 3**: Posso fazer isso logo no meu primeiro semestre?
  - manual: correta=sim, cobertura=parcial. A resposta reproduz exatamente a restrição do Art. 75 e não contradiz a referência.
  - langgraph: correta=sim, cobertura=total. A resposta reproduz corretamente a exceção do Art. 75 e os períodos do calendário citados.
- **v03, turno 2**: E para pedir revisão da nota dela, depois que eu fizer?
  - manual: correta=sim, cobertura=total. Fornece a informação essencial (7 dias) e acrescenta detalhes corretos suportados pelos trechos citados.
  - langgraph: correta=sim, cobertura=total. A resposta traz o prazo correto de 7 dias e está respaldada pelos artigos 85 e 86 citados.
- **v04, turno 2**: E se eu perder esse prazo, ainda tem jeito?
  - manual: correta=nao, cobertura=parcial. O assistente omite a possibilidade de trancamento até 30 dias antes do fim das aulas e afirma que não há chance após os períodos, contradizendo a referência.
  - langgraph: correta=sim, cobertura=parcial. A resposta repete a informação essencial da referência e está sustentada pelo trecho citado do Art. 66.
- **v05, turno 2**: E até quando tenho que pedir matrícula para esse semestre?
  - manual: correta=nao, cobertura=total. A resposta não corresponde ao período correto (21 a 28 de janeiro de 2027) e não tem suporte nas fontes citadas.
  - langgraph: correta=sim, cobertura=total. A resposta repete exatamente a informação da referência e está sustentada pelo trecho do calendário citado.
- **v06, turno 2**: E qual a frequência exigida nele?
  - manual: correta=nao, cobertura=total. A referência indica 100% de frequência para estágio obrigatório, mas o assistente afirma 75% e não menciona a exceção de 100% prevista no §1 do Art. 87.
  - langgraph: correta=parcial, cobertura=total. O assistente indica corretamente a frequência de 100%, mas omite a informação sobre reposição de faltas justificadas presente na referência.
- **v07, turno 2**: Dá para pedir isso para o TCC?
  - manual: correta=nao, cobertura=nenhuma. A resposta do assistente contradiz a referência, que afirma que a dispensa não é permitida, e não apresenta suporte nas fontes.
  - langgraph: correta=nao, cobertura=total. A resposta contradiz a referência e o artigo citado não sustenta a afirmação de que é possível pedir extraordinário domínio para o TCC.
- **v08, turno 2**: E até quando tenho que protocolar o pedido depois do atestado?
  - manual: correta=sim, cobertura=parcial. A resposta repete exatamente a informação da referência e está sustentada pelo § 2º do art. 117.
  - langgraph: correta=sim, cobertura=total. A resposta reproduz exatamente a informação da referência e está sustentada pelo § 2º do art. 117.
- **v09, turno 2**: E quantas faltas posso ter?
  - manual: correta=sim, cobertura=total. A resposta repete a frequência mínima de 75% (Art. 87) e menciona o mesmo requisito para cursos a distância (Art. 88), estando em concordância com a referência.
  - langgraph: correta=sim, cobertura=total. A resposta traz a informação essencial (75% frequência, até 25% de faltas) sem contradizer a referência e todas as afirmações são sustentadas pelos trechos citados.
- **v09, turno 3**: Isso vale para o estágio obrigatório também?
  - manual: correta=nao, cobertura=total. A resposta contradiz a referência, que afirma frequência 100% no estágio obrigatório, e as citações fornecidas não sustentam a afirmação sobre frequência.
  - langgraph: correta=nao, cobertura=total. Respondeu que a regra vale para estágio obrigatório, mas a referência indica que não se aplica, embora a informação de 100% esteja correta.
- **v10, turno 2**: Tem algum feriado nessa semana?
  - manual: correta=sim, cobertura=nenhuma. A resposta contém a informação correta, mas não apresenta suporte nas fontes citadas.
  - langgraph: correta=nao, cobertura=total. A resposta contradiz a referência ao dizer que há feriados na semana do evento, enquanto a referência afirma que não há feriados nesse período.
- **v11, turno 2**: E a de monitoria, quanto paga?
  - manual: correta=sim, cobertura=nenhuma. A resposta repete corretamente a informação da referência de que o regulamento e o calendário não tratam do pagamento de monitoria.
  - langgraph: correta=sim, cobertura=nenhuma. A resposta repete a informação da referência de que o regulamento e o calendário não tratam do assunto.
