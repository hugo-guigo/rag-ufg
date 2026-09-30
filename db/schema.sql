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
-- Busca por palavra-chave (full-text do Postgres, com radicais do português) para a busca híbrida.
ALTER TABLE trechos ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('portuguese', texto)) STORED;
CREATE INDEX IF NOT EXISTS trechos_tsv ON trechos USING gin (tsv);
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
-- Etapa 5: embedding de cada evento (mesmo modelo dos trechos, int8) para a busca híbrida do agente.
-- Sem coluna tsv gerada: unaccent não é IMMUTABLE e não entra em coluna gerada. Com 179 eventos, o
-- to_tsvector na hora da consulta custa menos de 1 ms.
ALTER TABLE eventos_calendario ADD COLUMN IF NOT EXISTS embedding vector(384);

-- Etapa 6: uma linha por pergunta que chega à API. Serve à observabilidade (latência, tokens,
-- ferramentas, erros) e ao limite de requisições: contar no banco vale para todas as instâncias da
-- nuvem, enquanto um contador em memória só vê a própria instância.
CREATE TABLE IF NOT EXISTS consultas (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    criado_em         timestamptz NOT NULL DEFAULT now(),
    cliente           text NOT NULL,        -- hash do IP com sal: conta requisições sem guardar o IP
    status            smallint NOT NULL,    -- código HTTP devolvido
    pergunta          text NOT NULL,
    cobertura         text,
    ferramentas       text[] NOT NULL DEFAULT '{}',
    chamadas_llm      smallint NOT NULL DEFAULT 0,
    erros_ferramenta  smallint NOT NULL DEFAULT 0,
    forcou_resposta   boolean NOT NULL DEFAULT false,
    citacoes          smallint NOT NULL DEFAULT 0,
    tokens_entrada    int NOT NULL DEFAULT 0,
    tokens_saida      int NOT NULL DEFAULT 0,
    ms_total          int NOT NULL,
    ms_llm            int NOT NULL DEFAULT 0,
    ms_ferramentas    int NOT NULL DEFAULT 0,
    erro              text
);
CREATE INDEX IF NOT EXISTS consultas_cliente_tempo ON consultas (cliente, criado_em);
CREATE INDEX IF NOT EXISTS consultas_tempo ON consultas (criado_em);
