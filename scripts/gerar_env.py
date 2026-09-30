"""Cria o .env local com senhas aleatórias, ou completa um .env existente com o que faltar.

Nunca sobrescreve um valor que já está no .env e nunca imprime valores.
A chave do Groq não é gerada: cole a sua no .env (GROQ_API_KEY=...).
"""
import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENV = RAIZ / ".env"


def valores_novos() -> dict[str, str]:
    admin, app = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    return {
        "POSTGRES_ADMIN_PASSWORD": admin,
        "APP_DB_PASSWORD": app,
        "DATABASE_URL_ADMIN": f"postgresql://admin:{admin}@127.0.0.1:5433/rag",
        "DATABASE_URL": f"postgresql://app:{app}@127.0.0.1:5433/rag",
        "GROQ_API_KEY": "",
        "SAL_CLIENTE": secrets.token_urlsafe(32),  # etapa 6: sal do hash do IP no log da API
    }


def main() -> None:
    novos = valores_novos()
    if not ENV.exists():
        ENV.write_text("".join(f"{k}={v}\n" for k, v in novos.items()), encoding="utf-8")
        print(f".env criado em {ENV}")
        return
    texto = ENV.read_text(encoding="utf-8")
    existentes = {linha.split("=", 1)[0].strip() for linha in texto.splitlines() if "=" in linha}
    faltando = {k: v for k, v in novos.items() if k not in existentes}
    # só variáveis independentes das senhas já existentes podem ser acrescentadas
    faltando = {k: v for k, v in faltando.items() if k in ("SAL_CLIENTE", "GROQ_API_KEY")}
    if not faltando:
        print(".env já está completo; nada foi alterado.")
        return
    separador = "" if texto.endswith("\n") else "\n"
    with ENV.open("a", encoding="utf-8") as f:
        f.write(separador + "".join(f"{k}={v}\n" for k, v in faltando.items()))
    print(f"acrescentado ao .env: {', '.join(faltando)}")


if __name__ == "__main__":
    main()
