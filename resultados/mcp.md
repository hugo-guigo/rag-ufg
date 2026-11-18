# Busca no regulamento via MCP x busca direta

Gerado por `scripts/medir_mcp.py` em 17/11/2026. 50 perguntas de avaliação, cada uma pelos caminhos em sequência; uma conexão por caminho e uma chamada de aquecimento antes. Máquina: a mesma do resto do projeto (i3 de 4 núcleos, Windows, Postgres em Docker local).

| Caminho | p50 (ms) | p95 (ms) | Mesmos trechos e ordem da busca direta | Recall@5 (perguntas com trecho) |
| --- | --- | --- | --- | --- |
| Direto (mesmo processo) | 94,2 | 182,1 | 50/50 | 88% (34 perguntas) |
| MCP em stdio | 136,3 | 243,4 | 50/50 | 88% (34 perguntas) |
| MCP em HTTP local | 180,1 | 358,7 | 50/50 | 88% (34 perguntas) |

A latência do direto é a do embedding da pergunta mais o SQL. Os caminhos MCP somam a serialização JSON-RPC e a passagem entre processos (stdio) ou pela pilha HTTP local (http). No HTTP entram também, a cada chamada, a conferência do token e a contagem do limite (duas consultas ao banco) e a gravação do rastreio. Medido com o banco no Docker da mesma máquina; com o Neon, cada consulta ao banco atravessa a rede.
