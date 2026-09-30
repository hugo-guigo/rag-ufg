"""API do assistente: POST /perguntar, GET /health e uma página simples em GET /.

Toda pergunta que passa da validação vira uma linha em consultas, inclusive as bloqueadas pelo limite
(429) e as que falharam (500, 503). Assim o log mostra também o que deu errado, não só o que deu certo.

Rodar local: uvicorn api.app:app --port 8000   (precisa do .env com DATABASE_URL, GROQ_API_KEY e SAL_CLIENTE)
"""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from api.servicos import Servicos
from rag.llm import ErroLLM, ErroOcupado
from rag.registro import hash_cliente

log = logging.getLogger("api")
PAGINA = Path(__file__).parent / "estatico" / "index.html"


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=3, max_length=500, examples=["Quantas vezes posso trancar o curso?"])

    @field_validator("pergunta")
    @classmethod
    def sem_espacos_nas_pontas(cls, valor: str) -> str:
        valor = valor.strip()
        if len(valor) < 3:
            raise ValueError("a pergunta precisa ter pelo menos 3 caracteres")
        return valor


class Fonte(BaseModel):
    rotulo: str
    fonte: str
    texto: str


class Ferramenta(BaseModel):
    nome: str
    argumentos: dict
    erro: str | None = None


class Resposta(BaseModel):
    id: int | None
    resposta: str
    cobertura: str
    fontes: list[Fonte]
    ferramentas: list[Ferramenta]
    latencia_ms: int


def ip_do_cliente(request: Request, confiar_proxy: bool) -> str:
    if confiar_proxy:
        # O proxy da nuvem acrescenta o IP que ele viu no fim da lista; o começo pode vir do próprio cliente.
        encaminhado = request.headers.get("x-forwarded-for", "")
        if encaminhado.strip():
            return encaminhado.split(",")[-1].strip()
    return request.client.host if request.client else "desconhecido"


def criar_app(montar_servicos) -> FastAPI:
    """montar_servicos: função sem argumentos que devolve Servicos (chamada ao subir a API)."""

    @asynccontextmanager
    async def ciclo(app: FastAPI):
        app.state.servicos = montar_servicos()
        yield
        if app.state.servicos.fechar:
            app.state.servicos.fechar()

    app = FastAPI(title="Assistente do regulamento da UFG", version="0.6.0", lifespan=ciclo,
                  description="Perguntas sobre o RGCG e o Calendário Acadêmico 2026 da UFG, com as fontes citadas. "
                              "Projeto de estudo: confira sempre nos documentos oficiais. As perguntas ficam "
                              "gravadas no log; não escreva dados pessoais.")

    @app.get("/", include_in_schema=False)
    def pagina():
        return FileResponse(PAGINA, media_type="text/html; charset=utf-8")

    @app.get("/health")
    def health(request: Request):
        servicos: Servicos = request.app.state.servicos
        if servicos.registro.banco_ok():
            return {"status": "ok", "banco": "ok"}
        return JSONResponse({"status": "erro", "banco": "fora do ar"}, status_code=503)

    @app.post("/perguntar", response_model=Resposta,
              responses={429: {"description": "Limite de perguntas"}, 503: {"description": "Groq ou banco indisponível"}})
    def perguntar(corpo: Pergunta, request: Request):
        servicos: Servicos = request.app.state.servicos
        inicio = time.perf_counter()
        linha = {"cliente": hash_cliente(ip_do_cliente(request, servicos.confiar_proxy), servicos.sal),
                 "pergunta": corpo.pergunta}

        def fechar(status: int, conteudo: dict, cabecalhos: dict | None = None) -> JSONResponse:
            linha["status"] = status
            linha["ms_total"] = 1000 * (time.perf_counter() - inicio)
            try:
                conteudo["id"] = servicos.registro.gravar(linha)
            except Exception:  # sem log não é motivo para negar a resposta ao usuário
                log.exception("falha ao gravar a consulta")
                conteudo["id"] = None
            if "latencia_ms" in conteudo:
                conteudo["latencia_ms"] = round(linha["ms_total"])
            return JSONResponse(conteudo, status_code=status, headers=cabecalhos)

        try:
            contagem = servicos.registro.contar(linha["cliente"])
        except Exception:
            log.exception("banco fora do ar ao contar requisições")
            return JSONResponse({"detail": "Banco de dados indisponível. Tente mais tarde."}, status_code=503)
        bloqueio = contagem.bloqueio(servicos.limites)
        if bloqueio:
            motivo, segundos = bloqueio
            return fechar(429, {"detail": f"Você atingiu o {motivo}. Tente de novo mais tarde."},
                          {"Retry-After": str(segundos)})

        try:
            r = servicos.agente.perguntar(corpo.pergunta)
        except ErroOcupado as erro:
            linha["erro"] = str(erro)
            return fechar(503, {"detail": "O assistente está no limite de uso do plano gratuito do modelo. "
                                          f"Tente de novo em {erro.segundos:.0f} s."},
                          {"Retry-After": str(max(1, round(erro.segundos)))})
        except ErroLLM as erro:
            linha["erro"] = str(erro)[:500]
            return fechar(503, {"detail": "O modelo de linguagem não respondeu. Tente de novo em instantes."})
        except Exception as erro:
            log.exception("erro inesperado no agente")
            linha["erro"] = f"{type(erro).__name__}: {str(erro)[:300]}"
            return fechar(500, {"detail": "Erro interno."})

        linha |= {"cobertura": r.cobertura, "ferramentas": [p.ferramenta for p in r.passos],
                  "chamadas_llm": r.chamadas_llm, "erros_ferramenta": r.erros_ferramenta,
                  "forcou_resposta": r.forcou_resposta, "citacoes": len(r.citados),
                  "tokens_entrada": r.tokens_entrada, "tokens_saida": r.tokens_saida,
                  "ms_llm": r.ms_llm, "ms_ferramentas": r.ms_ferramentas}
        resposta = Resposta(
            id=None, resposta=r.resposta, cobertura=r.cobertura,
            fontes=[Fonte(rotulo=rot, fonte=fonte, texto=texto) for rot, fonte, texto in r.citados],
            ferramentas=[Ferramenta(nome=p.ferramenta, argumentos=p.argumentos, erro=p.erro)
                         for p in r.passos if p.ferramenta != "responder"],
            latencia_ms=0)
        return fechar(200, resposta.model_dump())

    return app


def _app_do_ambiente() -> FastAPI:
    from dotenv import load_dotenv

    from api.servicos import servicos_do_ambiente

    load_dotenv()
    return criar_app(servicos_do_ambiente)


app = _app_do_ambiente()
