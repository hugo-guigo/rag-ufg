-- Idempotente: roda no Postgres local e no Neon pelo mesmo script (scripts/preparar_banco.py).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS documentos (
    id      text PRIMARY KEY,
    titulo  text NOT NULL,
    url     text NOT NULL,
    sha256  char(64) NOT NULL
);

-- Um trecho por (estratégia de chunking, modelo de embedding): as variantes convivem para a avaliação.
CREATE TABLE IF NOT EXISTS trechos (
    id             text NOT NULL,
    estrategia     text NOT NULL,
    modelo         text NOT NULL,
    documento      text NOT NULL REFERENCES documentos (id),
    texto          text NOT NULL,
    contexto       text NOT NULL DEFAULT '',
    artigos        int[] NOT NULL,
    pagina_inicio  int NOT NULL,
    pagina_fim     int NOT NULL,
    embedding      vector(384) NOT NULL,
    PRIMARY KEY (estrategia, modelo, id)
);
-- Sem índice aproximado (HNSW/IVFFlat) de propósito: com algumas centenas de linhas a busca exata
-- lê tudo em menos de 1 ms e nunca erra. Ver a seção de decisões do README.

CREATE TABLE IF NOT EXISTS eventos_calendario (
    id           serial PRIMARY KEY,
    documento    text NOT NULL REFERENCES documentos (id),
    data_inicio  date NOT NULL,
    data_fim     date NOT NULL CHECK (data_fim >= data_inicio),
    descricao    text NOT NULL,
    categoria    text,
    pagina       int NOT NULL
);
CREATE INDEX IF NOT EXISTS eventos_calendario_datas ON eventos_calendario (data_inicio, data_fim);
