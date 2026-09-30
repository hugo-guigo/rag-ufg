"""Primeiro deploy no Azure (ou reaplicar a infraestrutura). Os deploys seguintes são do GitHub Actions.

Uso:
  python scripts/deploy_azure.py orcamento            # alerta de orçamento da assinatura (antes de tudo)
  python scripts/deploy_azure.py infra [--imagem ghcr.io/hugo-guigo/rag-ufg:latest]

"infra" cria o grupo rg-rag-ufg e aplica infra/main.bicep com os segredos lidos do .env
(DATABASE_URL_NEON, GROQ_API_KEY, SAL_CLIENTE). Os segredos vão para o Azure por um arquivo de
parâmetros temporário, apagado em seguida; nada é impresso. No fim grava no GitHub as variáveis
(não secretas) que o workflow usa: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID e API_URL.
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
GRUPO, REGIAO = "rg-rag-ufg", "northcentralus"
EMAIL = "hugo.guilherme.paula@gmail.com"
AZ = shutil.which("az") or r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"


def az(*args: str) -> str:
    r = subprocess.run([AZ, *args, "--output", "json"], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"az {' '.join(args[:2])} falhou:\n{r.stderr[-1500:]}")
    return r.stdout


def orcamento() -> None:
    az("deployment", "sub", "create", "--location", REGIAO, "--name", "orcamento",
       "--template-file", str(RAIZ / "infra" / "orcamento.bicep"), "--parameters", f"email={EMAIL}")
    print("orçamento de US$ 1/mês criado, com alertas em 50% e 100% (real) e 100% (previsto)")


def infra(imagem: str) -> None:
    env = dotenv_values(RAIZ / ".env")
    faltando = [k for k in ("DATABASE_URL_NEON", "GROQ_API_KEY", "SAL_CLIENTE") if not env.get(k)]
    if faltando:
        raise SystemExit(f"faltam no .env: {', '.join(faltando)}")
    az("group", "create", "--name", GRUPO, "--location", REGIAO)
    parametros = {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
                  "contentVersion": "1.0.0.0",
                  "parameters": {"imagem": {"value": imagem},
                                 "databaseUrl": {"value": env["DATABASE_URL_NEON"]},
                                 "groqApiKey": {"value": env["GROQ_API_KEY"]},
                                 "salCliente": {"value": env["SAL_CLIENTE"]}}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(parametros, f)
    try:
        saida = json.loads(az("deployment", "group", "create", "--resource-group", GRUPO, "--name", "api",
                              "--template-file", str(RAIZ / "infra" / "main.bicep"), "--parameters", f"@{f.name}"))
    finally:
        os.remove(f.name)
    resultado = saida["properties"]["outputs"]
    conta = json.loads(az("account", "show"))
    variaveis = {"AZURE_CLIENT_ID": resultado["clientIdDeploy"]["value"], "AZURE_TENANT_ID": conta["tenantId"],
                 "AZURE_SUBSCRIPTION_ID": conta["id"], "API_URL": resultado["url"]["value"]}
    for nome, valor in variaveis.items():
        subprocess.run(["gh", "variable", "set", nome, "--body", valor, "--repo", "hugo-guigo/rag-ufg"],
                       check=True, capture_output=True)
    print(f"infraestrutura aplicada; URL: {resultado['url']['value']}")
    print("variáveis do GitHub gravadas: " + ", ".join(variaveis))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("acao", choices=["orcamento", "infra"])
    parser.add_argument("--imagem", default="ghcr.io/hugo-guigo/rag-ufg:latest")
    args = parser.parse_args()
    if args.acao == "orcamento":
        orcamento()
    else:
        infra(args.imagem)


if __name__ == "__main__":
    main()
