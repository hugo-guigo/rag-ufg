"""Log de consultas da API e limite de requisições, os dois na tabela consultas.

O cliente é identificado por um hash do IP com sal (HMAC-SHA256, 16 caracteres): dá para contar
requisições do mesmo IP sem guardar o IP. Sem o sal, que fica nos segredos, não dá para testar IPs
conhecidos contra o hash.

Contam para o limite só as perguntas que chegaram ao agente (status diferente de 429): quem insiste
depois de bloqueado não prolonga o próprio bloqueio.
"""
import hashlib
import hmac
from dataclasses import dataclass

CONTAGEM = """
    SELECT count(*) FILTER (WHERE cliente = %(c)s AND criado_em > now() - interval '1 minute'),
           count(*) FILTER (WHERE cliente = %(c)s),
           count(*)
    FROM consultas
    WHERE criado_em > now() - interval '1 day' AND status <> 429"""

CAMPOS = ("cliente", "status", "pergunta", "cobertura", "ferramentas", "chamadas_llm", "erros_ferramenta",
          "forcou_resposta", "citacoes", "tokens_entrada", "tokens_saida", "ms_total", "ms_llm",
          "ms_ferramentas", "erro")
INSERCAO = (f"INSERT INTO consultas ({', '.join(CAMPOS)}) VALUES ({', '.join('%(' + c + ')s' for c in CAMPOS)}) "
            "RETURNING id")


def hash_cliente(ip: str, sal: str) -> str:
    return hmac.new(sal.encode(), ip.encode(), hashlib.sha256).hexdigest()[:16]


@dataclass(frozen=True)
class Limites:
    por_minuto: int = 5
    por_dia: int = 30
    # O que limita a demo é o teto de 200 mil tokens por dia do gpt-oss-20b no plano grátis do Groq
    # (medido: 199.137 usados depois da avaliação da etapa 5). Com ~3 mil tokens por pergunta, cabem
    # ~65 por dia; 50 deixa folga. As 1.000 requisições por dia não chegam a pesar.
    total_por_dia: int = 50


@dataclass(frozen=True)
class Contagem:
    no_minuto: int
    no_dia: int
    total_no_dia: int

    def bloqueio(self, limites: Limites) -> tuple[str, int] | None:
        """(motivo, segundos para tentar de novo) se passou de algum limite."""
        if self.total_no_dia >= limites.total_por_dia:
            return "o assistente atingiu o limite diário de perguntas da demonstração", 3600
        if self.no_dia >= limites.por_dia:
            return f"limite de {limites.por_dia} perguntas por dia", 3600
        if self.no_minuto >= limites.por_minuto:
            return f"limite de {limites.por_minuto} perguntas por minuto", 60
        return None


class Registro:
    """Leitura e escrita na tabela consultas por um pool de conexões do psycopg."""

    def __init__(self, pool):
        self.pool = pool

    def contar(self, cliente: str) -> Contagem:
        with self.pool.connection() as conexao:
            return Contagem(*conexao.execute(CONTAGEM, {"c": cliente}).fetchone())

    def gravar(self, linha: dict) -> int:
        valores = {c: linha.get(c) for c in CAMPOS}
        valores["ferramentas"] = valores["ferramentas"] or []
        for campo in ("chamadas_llm", "erros_ferramenta", "citacoes", "tokens_entrada", "tokens_saida"):
            valores[campo] = int(valores[campo] or 0)
        for campo in ("ms_total", "ms_llm", "ms_ferramentas"):
            valores[campo] = round(valores[campo] or 0)
        valores["forcou_resposta"] = bool(valores["forcou_resposta"])
        with self.pool.connection() as conexao:
            return conexao.execute(INSERCAO, valores).fetchone()[0]

    def banco_ok(self) -> bool:
        try:
            with self.pool.connection(timeout=3) as conexao:
                conexao.execute("SELECT 1")
            return True
        except Exception:
            return False
