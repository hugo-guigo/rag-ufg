"""Embeddings com o multilingual-e5-small em ONNX, sem PyTorch.

O E5 foi treinado com prefixos: "query: " para a pergunta e "passage: " para o documento. Sem eles
a qualidade da busca cai, segundo o cartão do modelo. O vetor final é a média dos vetores dos tokens
(ignorando o padding), normalizada para norma 1. Com norma 1, similaridade de cosseno = produto escalar.
"""
import os
import time
from dataclasses import dataclass

import numpy as np

# No Windows sem modo desenvolvedor o cache do Hugging Face copia arquivos em vez de criar symlinks.
# Funciona igual; o aviso só polui a saída.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

REPOSITORIO = "Xenova/multilingual-e5-small"
REVISAO = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"  # fixa a versão: o mesmo arquivo em todo lugar
ARQUIVOS = {"int8": "onnx/model_quantized.onnx", "fp32": "onnx/model.onnx"}
DIMENSAO = 384
MAX_TOKENS = 512


def media_normalizada(estados: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    """(lote, tokens, dim) + (lote, tokens) -> (lote, dim) com norma 1."""
    m = mascara[..., None].astype(np.float32)
    media = (estados * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
    return media / np.linalg.norm(media, axis=1, keepdims=True)


@dataclass
class Estatisticas:
    textos: int = 0
    truncados: int = 0
    segundos: float = 0.0


class Embedder:
    def __init__(self, variante: str = "int8"):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.variante = variante
        self.nome = f"multilingual-e5-small-{variante}"
        modelo = hf_hub_download(REPOSITORIO, ARQUIVOS[variante], revision=REVISAO)
        tokenizador = hf_hub_download(REPOSITORIO, "tokenizer.json", revision=REVISAO)
        self.tokenizador = Tokenizer.from_file(tokenizador)
        self.tokenizador.enable_truncation(MAX_TOKENS)
        pad = self.tokenizador.token_to_id("<pad>")
        self.tokenizador.enable_padding(pad_id=pad, pad_token="<pad>")
        self.sessao = ort.InferenceSession(modelo, providers=["CPUExecutionProvider"])
        self.entradas = {e.name for e in self.sessao.get_inputs()}
        self.estatisticas = Estatisticas()

    def _codificar(self, textos: list[str]) -> np.ndarray:
        cod = self.tokenizador.encode_batch(textos)
        ids = np.array([c.ids for c in cod], dtype=np.int64)
        mascara = np.array([c.attention_mask for c in cod], dtype=np.int64)
        self.estatisticas.truncados += sum(1 for c in cod if c.overflowing)
        feed = {"input_ids": ids, "attention_mask": mascara}
        if "token_type_ids" in self.entradas:
            feed["token_type_ids"] = np.zeros_like(ids)
        estados = self.sessao.run(None, feed)[0]
        return media_normalizada(estados, mascara)

    def documentos(self, textos: list[str], lote: int = 16) -> np.ndarray:
        inicio = time.perf_counter()
        # ordenar por tamanho deixa cada lote com pouco padding
        ordem = sorted(range(len(textos)), key=lambda i: len(textos[i]))
        vetores = np.zeros((len(textos), DIMENSAO), dtype=np.float32)
        for k in range(0, len(ordem), lote):
            idx = ordem[k:k + lote]
            vetores[idx] = self._codificar(["passage: " + textos[i] for i in idx])
        self.estatisticas.textos += len(textos)
        self.estatisticas.segundos += time.perf_counter() - inicio
        return vetores

    def pergunta(self, texto: str) -> np.ndarray:
        return self._codificar(["query: " + texto])[0]
