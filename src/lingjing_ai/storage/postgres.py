from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


Row = Mapping[str, Any]


def connect(dsn: str, schema: str, *, ensure_schema: bool = False) -> psycopg.Connection:
    """Open a PostgreSQL connection with search_path set to the given schema."""
    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        if ensure_schema:
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    except Exception:
        conn.close()
        raise
    return conn


def drop_schema(dsn: str, schema: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))


@contextmanager
def schema_connection(dsn: str, schema: str, *, ensure_schema: bool = False) -> Iterator[psycopg.Connection]:
    conn = connect(dsn, schema, ensure_schema=ensure_schema)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetchone(dsn: str, schema: str, query: str, params: Sequence[Any] = ()) -> Row | None:
    with schema_connection(dsn, schema) as conn:
        return conn.execute(query, params).fetchone()


def fetchall(dsn: str, schema: str, query: str, params: Sequence[Any] = ()) -> list[Row]:
    with schema_connection(dsn, schema) as conn:
        return list(conn.execute(query, params).fetchall())


def execute_statements(dsn: str, schema: str, statements: Sequence[str]) -> None:
    with schema_connection(dsn, schema, ensure_schema=True) as conn:
        for statement in statements:
            text = statement.strip()
            if text:
                conn.execute(text)
