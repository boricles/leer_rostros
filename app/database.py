"""Conexión a Postgres + pgvector y esquema de la tabla de personas.

Una fila = una foto. Varias fotos de la misma persona comparten `person_id`.
`estado` distingue los dos flujos:
  - 'buscada'    -> la registró un FAMILIAR que busca a alguien.
  - 'encontrada' -> la registró un RESCATISTA que halló a alguien.
"""

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None

# Columnas extra del dominio (se agregan por ALTER para tablas ya existentes).
_EXTRA_COLS = [
    ("person_id", "UUID"),
    ("estado", "TEXT NOT NULL DEFAULT 'buscada'"),
    ("es_menor", "BOOLEAN NOT NULL DEFAULT false"),
    ("nombre", "TEXT"),
    ("apellido", "TEXT"),
    ("edad", "TEXT"),
    ("doc_tipo", "TEXT"),
    ("doc_numero", "TEXT"),
    ("telefono_contacto", "TEXT"),
    ("refugio", "TEXT"),
    ("telefono_responsable", "TEXT"),
    ("doc_responsable", "TEXT"),
    ("descripcion", "TEXT"),
    ("ubicacion", "TEXT"),
    ("codigo", "TEXT"),
]


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = ConnectionPool(s.database_url, configure=_configure, open=True)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def init_db() -> None:
    s = get_settings()
    with psycopg.connect(s.database_url) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()
        register_vector(conn)
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS personas (
                id          UUID PRIMARY KEY,
                image_url   TEXT NOT NULL,
                image_key   TEXT NOT NULL,
                embedding   vector({s.embedding_dim}) NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # Columnas del dominio (idempotente; actualiza tablas previas).
        for col, decl in _EXTRA_COLS:
            conn.execute(f"ALTER TABLE personas ADD COLUMN IF NOT EXISTS {col} {decl}")
        conn.execute("UPDATE personas SET person_id = id WHERE person_id IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS personas_person_id_idx ON personas (person_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS personas_estado_idx ON personas (estado)")
        # HNSW para búsqueda vectorial rápida a escala.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS personas_embedding_hnsw "
            "ON personas USING hnsw (embedding vector_cosine_ops)"
        )
        conn.commit()
