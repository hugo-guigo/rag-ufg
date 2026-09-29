"""Baixa os PDFs públicos listados em fontes.json e confere o SHA-256.

O checksum garante que a avaliação roda sobre o mesmo documento que foi anotado. Se a UFG trocar
o PDF no mesmo endereço, o download falha em vez de misturar versões sem avisar.
"""
import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PDFS = RAIZ / "dados" / "pdfs"


@dataclass(frozen=True)
class Fonte:
    id: str
    titulo: str
    url: str
    sha256: str

    @property
    def caminho(self) -> Path:
        return PASTA_PDFS / f"{self.id}.pdf"


def carregar_fontes(arquivo: Path = RAIZ / "fontes.json") -> list[Fonte]:
    return [Fonte(**f) for f in json.loads(arquivo.read_text(encoding="utf-8"))]


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def baixar(fonte: Fonte) -> Path:
    """Baixa só se o arquivo não existe ou não bate com o checksum."""
    if fonte.caminho.exists() and sha256(fonte.caminho) == fonte.sha256:
        return fonte.caminho
    fonte.caminho.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(fonte.url, timeout=60) as resposta:
        conteudo = resposta.read()
    obtido = hashlib.sha256(conteudo).hexdigest()
    if obtido != fonte.sha256:
        raise ValueError(f"{fonte.id}: SHA-256 {obtido} difere do esperado {fonte.sha256}. "
                         "O PDF mudou na origem; confira antes de atualizar fontes.json.")
    fonte.caminho.write_bytes(conteudo)
    return fonte.caminho


if __name__ == "__main__":
    for f in carregar_fontes():
        print(f"{f.id}: {baixar(f)}")
