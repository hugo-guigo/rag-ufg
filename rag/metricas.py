"""Métricas da avaliação. Funções puras, testadas em tests/test_metricas.py."""
import math
from collections.abc import Callable, Sequence


def normalizar(texto: str) -> str:
    return " ".join(texto.split())


def contem_trecho(texto: str, trecho: str) -> bool:
    return normalizar(trecho) in normalizar(texto)


def trechos_de(pergunta: dict) -> list[str]:
    """O campo "trecho" aceita um texto ou uma lista de textos (qualquer um deles conta como acerto)."""
    trecho = pergunta.get("trecho", [])
    return [trecho] if isinstance(trecho, str) else trecho


def posicao_do_acerto(itens: Sequence, acertou: Callable[[object], bool]) -> int | None:
    """Posição (1 = primeiro) do primeiro item relevante, ou None se nenhum for."""
    return next((i for i, item in enumerate(itens, start=1) if acertou(item)), None)


def recall_em_k(posicoes: Sequence[int | None], k: int) -> float:
    """Fração de perguntas com pelo menos um trecho relevante entre os k primeiros."""
    return sum(1 for p in posicoes if p is not None and p <= k) / len(posicoes)


def mrr(posicoes: Sequence[int | None], k: int) -> float:
    """Média de 1/posição do primeiro acerto (0 se não achou até k). Premia achar cedo."""
    return sum(1 / p for p in posicoes if p is not None and p <= k) / len(posicoes)


def percentil(valores: Sequence[float], q: float) -> float | None:
    """Interpolação linear, igual ao percentile_cont do Postgres."""
    v = sorted(x for x in valores if x is not None)
    if not v:
        return None
    pos = (len(v) - 1) * q
    baixo, alto = math.floor(pos), math.ceil(pos)
    return v[baixo] + (v[alto] - v[baixo]) * (pos - baixo)


def melhor_limiar(com_resposta: Sequence[float], sem_resposta: Sequence[float]) -> tuple[float, float]:
    """Limiar de similaridade que melhor separa "tem resposta" (>= limiar) de "não sei" (< limiar).

    Devolve (limiar, acurácia). É otimista: o limiar é escolhido olhando as próprias perguntas.
    """
    candidatos = sorted(set(com_resposta) | set(sem_resposta))
    total = len(com_resposta) + len(sem_resposta)
    melhor = (candidatos[0], 0.0)
    for limiar in candidatos:
        certos = sum(s >= limiar for s in com_resposta) + sum(s < limiar for s in sem_resposta)
        if certos / total > melhor[1]:
            melhor = (limiar, certos / total)
    return melhor
