"""Postgres local, opcional. Sem DATABASE_URL o processo segue só em memória.

Somente usuários são gravados quando a variável existe. Contas e saldos ficam em memória.
O acompanhamento de transferência e a deduplicação continuam em memória.
"""
import os
import threading

import psycopg

_lock = threading.Lock()
_conn: psycopg.Connection | None = None


def ativo() -> bool:
    return _conn is not None


def iniciar() -> None:
    global _conn
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return
    conn = psycopg.connect(url, autocommit=True, connect_timeout=10)
    conn.execute("SELECT pg_advisory_lock(%s)", (824611,))
    try:
        _criar_tabelas(conn)
        with _lock:
            _conn = conn
        _semear_usuarios()
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (824611,))


def _criar_tabelas(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            usuario text PRIMARY KEY,
            salt bytea NOT NULL,
            hash bytea NOT NULL
        )
        """
    )


def fechar() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def buscar_usuario(usuario: str) -> dict | None:
    with _lock:
        if _conn is None:
            return None
        row = _conn.execute(
            "SELECT salt, hash FROM usuarios WHERE usuario = %s",
            (usuario,),
        ).fetchone()
    if row is None:
        return None
    return {"salt": bytes(row[0]), "hash": bytes(row[1])}


def inserir_usuario(usuario: str, senha: str) -> bool:
    from .seguranca import _novo_usuario

    reg = _novo_usuario(senha)
    with _lock:
        if _conn is None:
            return False
        cur = _conn.execute(
            """
            INSERT INTO usuarios (usuario, salt, hash)
            VALUES (%s, %s, %s)
            ON CONFLICT (usuario) DO NOTHING
            """,
            (usuario, reg["salt"], reg["hash"]),
        )
        return cur.rowcount == 1


def _semear_usuarios() -> None:
    from .seguranca import _novo_usuario

    sementes = {
        "lara": _novo_usuario(os.environ.get("SENHA_LARA", "iceibank")),
        "allan": _novo_usuario(os.environ.get("SENHA_ALLAN", "iceibank")),
    }
    for usuario, reg in sementes.items():
        with _lock:
            if _conn is None:
                return
            _conn.execute(
                """
                INSERT INTO usuarios (usuario, salt, hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (usuario) DO NOTHING
                """,
                (usuario, reg["salt"], reg["hash"]),
            )
