# Especificação: servidor e cliente MCP do assistente

Escrita antes do código (17/11/2026). O registro da revisão, com o que foi recusado ou corrigido,
fica no fim e é atualizado durante o trabalho.

## Objetivo

Expor a busca no regulamento e no calendário pelo Model Context Protocol (MCP) e mostrar os dois
lados do protocolo: um servidor que qualquer cliente MCP usa (Claude Code, por exemplo) e um cliente
próprio que conecta ao servidor, descobre as ferramentas e responde perguntas com o LLM, com
autenticação, limite de uso e rastreio de cada chamada.

## Fora do escopo

- Novas fontes ou mudanças na busca. O servidor reaproveita `rag.busca` como está; a meta é devolver
  exatamente os mesmos trechos que a API devolve hoje.
- Servidor de autorização OAuth próprio (ver decisão 4).

## Peças

| Peça | Onde | O que faz |
|---|---|---|
| Servidor MCP | `mcp_ufg/servidor.py` | `MCPServer` do SDK oficial com 2 ferramentas e 1 recurso |
| Ferramentas | `mcp_ufg/ferramentas.py` | validação dos argumentos e conversão dos resultados de `rag.busca` em modelos Pydantic |
| Transporte stdio | `python -m mcp_ufg` | uso local (Claude Code, testes) |
| Transporte HTTP | `/mcp` na API FastAPI | Streamable HTTP, com Bearer token e limite no banco |
| Rastreio | `mcp_ufg/rastreio.py` | middleware que registra cada chamada de ferramenta |
| Cliente | `mcp_ufg/cliente.py` e `scripts/cliente_mcp.py` | conecta, lista as ferramentas e conduz pergunta, ferramentas e resposta |
| Tokens | tabela `clientes_mcp` e `scripts/token_mcp.py` | cria, lista e revoga tokens |

## Ferramentas e recurso

Todas são só leitura (`readOnlyHint`), com entrada e saída tipadas em Pydantic. O schema de saída é
anunciado pelo servidor (`outputSchema`), e o resultado vai como conteúdo estruturado.

- `buscar_regulamento(pergunta: str, k: int = 5)` com `k` de 1 a 10. Devolve a lista de trechos, cada
  um com `id`, `rotulo` (ex.: "RGCG, Art. 82, p. 25"), `artigos`, `paginas`, `texto` e
  `similaridade`. Mesma busca da API: vetorial, estratégia `artigo_secao`, modelo int8.
- `consultar_calendario(termo: str = "", data_inicio: date | None, data_fim: date | None)`. Devolve
  até 8 eventos com `id`, `rotulo`, `data_inicio`, `data_fim`, `descricao` e `pagina`. Mesma busca
  híbrida e mesma normalização de semestre ("segundo semestre de 2026" vira "2026/2") do agente.
- Recurso `ufg://fontes`: os documentos indexados (título, URL, SHA-256) e quantos trechos e eventos
  cada um tem.

Erros que o modelo pode corrigir (data mal escrita, intervalo invertido, nem termo nem intervalo,
pergunta vazia) voltam como erro de ferramenta com mensagem que diz o que mudar. Erro interno volta
como "falha interna", sem detalhe do banco. Cada ferramenta tem timeout (padrão 10 s).

## Decisões (com a alternativa recusada)

1. **SDK oficial `mcp` 2.3 e `MCPServer`.** O prompt fala em FastMCP; na versão 2 do SDK, o FastMCP
   foi renomeado para `MCPServer` (o módulo antigo só levanta um erro com o link da migração). Usar
   a 1.x só para manter o nome seria começar com uma versão parada.
2. **Ferramentas finas sobre `rag.busca`.** O servidor não reimplementa a busca: chama as mesmas
   funções que a API chama. A validação das datas e a normalização de semestre saem do agente para
   um lugar comum, usado pelos dois.
3. **Streamable HTTP sem estado (`stateless_http`).** O Container App pode ir a zero réplicas e voltar;
   com sessão em memória, uma reconexão depois do cold start perderia a sessão. As ferramentas não
   precisam de estado entre chamadas.
4. **Bearer token pré-emitido por cliente, não OAuth.** A especificação MCP descreve o servidor HTTP
   como servidor de recursos OAuth 2.1, com um servidor de autorização separado. As opções sem custo
   eram: (a) escrever um servidor de autorização com o SDK, que é autenticação artesanal, o tipo de
   código que mais dá errado; (b) Keycloak ou outro IdP em container, que no Azure precisaria de uma
   réplica sempre ligada e sairia do plano grátis; (c) Entra ID, que não tem o registro dinâmico de
   clientes que os clientes MCP usam. Como os dados são públicos e o risco é abuso da cota, um token
   por cliente resolve: guardado só como SHA-256, revogável e conferido em toda requisição. O ponto de troca fica explícito: um `TokenVerifier` de JWT do SDK no lugar da consulta
   ao banco, se um IdP entrar.
5. **Middleware próprio para o Bearer, não o do SDK.** O SDK só liga a conferência de token junto com
   a URL de um servidor de autorização, que ele publica no metadata OAuth. Publicar uma URL que não
   existe faria clientes tentarem um fluxo OAuth que não há. O middleware responde 401 com
   `WWW-Authenticate: Bearer` e guarda o cliente para o rastreio e o limite.
6. **Limite no banco, como na API.** Contar chamadas por cliente na tabela de chamadas vale para todas
   as instâncias; contador em memória só vê a própria. Limites próprios do MCP (as ferramentas não
   gastam cota do Groq, então podem ser mais altos que os 50 por dia da API), mesma classe `Limites`.
7. **Rastreio em JSON no stdout e no banco.** Uma linha por chamada de ferramenta: id de rastreio,
   cliente, ferramenta, latência, ok ou erro, tamanho da resposta. Não grava o texto da pergunta no
   log, só o tamanho (a API grava a pergunta na tabela `consultas` e avisa na página; o MCP não precisa).
   O id de rastreio vem do cliente (header `X-Rastreio` no HTTP, `_meta` no stdio) ou é criado no
   servidor; assim o log do cliente e o do servidor se ligam pela mesma pergunta.
8. **Cliente descobre as ferramentas.** O cliente monta a lista de ferramentas do LLM a partir do que
   o servidor anuncia (`list_tools`), não de uma cópia local. Mudou o schema no servidor, o cliente
   acompanha. Ele acrescenta só a ferramenta `responder`, que é dele.
9. **Retry com backoff exponencial de verdade no cliente.** Espera `base × 2^tentativa` com jitter
   aleatório, teto por espera e limite de tentativas, só para erro transitório (conexão, timeout,
   429, 5xx). Erro de validação ou 401 não repete. O Triagem n8n tem retry fixo; este é o primeiro
   com backoff, e o teste confere as esperas.

## Testes

- Ferramentas: com fontes falsas (sem banco), resultados e erros.
- Contrato: nomes, descrições, `inputSchema` e `outputSchema` anunciados.
- Autenticação: sem token 401, token errado 401, token revogado 401, token certo passa.
- Integração cliente-servidor em stdio: subprocesso de verdade, protocolo de verdade, fontes falsas
  (roda no CI sem banco).
- Integração com o Postgres (marcados `integracao`): as ferramentas contra o banco ingerido.
- CI: os mesmos jobs de hoje; a imagem passa a responder `/mcp` com 401 sem token.

## Medição

- Latência por chamada: busca direta (`rag.busca` no mesmo processo), via MCP em stdio e via MCP em
  HTTP local. p50 e p95 nas 50 perguntas de avaliação.
- Equivalência: as 50 perguntas pela ferramenta MCP devolvem os mesmos trechos, na mesma ordem, que a
  busca direta, portanto o mesmo recall@5 (88%).
- Cliente com o LLM: algumas perguntas de ponta a ponta, sem rodar a avaliação inteira (cota do Groq).

## Riscos

- O SDK 2.x é recente e mudou bastante em relação à 1.x: ler o código instalado antes de usar cada
  parte, não escrever de memória.
- O deploy no Azure precisa do schema novo no Neon e mexe na demo pública: só com o OK do Hugo.

## Registro da revisão

O que mudou entre a especificação e o código, e o que a revisão pegou:

1. **Escopo por token, recusado.** A decisão 4 previa token "com escopo". As duas ferramentas e o recurso
   são de leitura e servem a qualquer cliente; um escopo único não protegeria nada. Ficou token por
   cliente, revogável. Escopo entra se aparecer uma ferramenta que escreve.
2. **Recurso com o erro errado.** O recurso `ufg://fontes` usava o mesmo tratamento das ferramentas, que
   levanta `ToolError`; para recurso, o SDK espera `ResourceError`. Corrigido antes do primeiro teste.
3. **`/mcp` respondia 307.** Montado em `/mcp`, o endpoint só casava com `/mcp/`, e o roteador do FastAPI
   redirecionava `/mcp`. A primeira tentativa (reescrever o caminho dentro do middleware de token) não
   funcionou, porque o redirecionamento acontece antes do middleware. A segunda precisou de uma classe,
   porque o `Route` do Starlette trata uma função como endpoint que recebe `Request`, não como app ASGI.
   Nem todo cliente MCP segue redirecionamento de POST, e `/mcp` é a URL que as pessoas digitam.
4. **401, 429 e 503 chegavam iguais ao cliente.** O cliente do SDK transforma qualquer resposta não 2xx
   num erro genérico, sem o status, a menos que o corpo seja um erro JSON-RPC. Sem o status, o retry não
   distinguia o que repetir. O middleware passou a responder em JSON-RPC (códigos -32001, -32002 e -32003)
   com o status HTTP e o Retry-After no `data`.
5. **Retry-After longo demais.** Com o banco fora, o middleware mandava Retry-After de 30 s, e o cliente
   desiste de esperas acima de 15 s: o retry nunca acontecia. Baixou para 5 s. O teste também estava
   errado: cada tentativa de conexão faz duas requisições (o SDK tenta o handshake novo e depois o
   antigo), então as falhas simuladas se esgotavam numa tentativa só.
6. **Imagem sem o pacote novo.** O Dockerfile copiava só `rag` e `api`; a imagem subiria sem `mcp_ufg` e
   a API quebraria na importação. Pego ao construir a imagem localmente antes do CI; o CI ganhou um passo
   que confere 401 em `/mcp` sem token.
7. **Contrato conferido por mutação.** O teste de contrato compara o que o servidor anuncia com um
   arquivo registrado. Para confirmar que ele pega mudança, a descrição de um parâmetro foi alterada: o
   teste falhou, e voltou a passar quando a mudança foi desfeita.
8. **Laço do cliente separado do agente.** Recusado reaproveitar a classe `Agente`: ela lê os argumentos
   pelo schema fixo dela (`consulta`), e o cliente usa o schema que o servidor anuncia (`pergunta`, `k`).
   O prompt, a ferramenta `responder` e a validação da resposta final vêm do agente.
