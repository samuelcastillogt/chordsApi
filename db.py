import os
from pathlib import Path
from typing import Optional

import psycopg
from psycopg.rows import dict_row


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env.development.local"


def load_local_env(env_path: Path = ENV_FILE) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_database_url() -> Optional[str]:
    load_local_env()
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("DATABASE_URL_UNPOOLED")
        or os.getenv("POSTGRES_URL_NON_POOLING")
    )


def get_connection():
    db_url = get_database_url()
    if not db_url:
        raise RuntimeError(
            "No se encontro DATABASE_URL en el entorno ni en .env.development.local"
        )
    return psycopg.connect(db_url, autocommit=True)


def canciones_table_exists() -> bool:
    query = """
    SELECT EXISTS (
      SELECT 1
      FROM information_schema.tables
      WHERE table_schema = 'public' AND table_name = 'canciones'
    );
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query)
        exists = cur.fetchone()
        return bool(exists and exists[0])


def ensure_canciones_table() -> None:
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS canciones (
      id BIGSERIAL PRIMARY KEY,
      slug TEXT,
      nombre TEXT NOT NULL,
      artista TEXT NOT NULL,
      cancion TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    alter_sql = """
    ALTER TABLE canciones
    ADD COLUMN IF NOT EXISTS slug TEXT;
    """
    index_sql = """
    CREATE UNIQUE INDEX IF NOT EXISTS canciones_slug_unique_idx
    ON canciones (slug);
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(create_table_sql)
        cur.execute(alter_sql)
        cur.execute(index_sql)


def insert_cancion(slug: str, nombre: str, artista: str, cancion: str) -> dict:
    query = """
    INSERT INTO canciones (slug, nombre, artista, cancion)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (slug)
    DO UPDATE SET
      nombre = EXCLUDED.nombre,
      artista = EXCLUDED.artista,
      cancion = EXCLUDED.cancion
    RETURNING id, slug, nombre, artista, cancion, created_at;
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (slug, nombre, artista, cancion))
        row = cur.fetchone()
        if not row:
            raise RuntimeError("No se pudo guardar la cancion")
        return dict(row)


def get_cancion_by_slug(slug: str) -> Optional[dict]:
    query = """
    SELECT id, slug, nombre, artista, cancion, created_at
    FROM canciones
    WHERE slug = %s
    LIMIT 1;
    """
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (slug,))
        row = cur.fetchone()
        return dict(row) if row else None
