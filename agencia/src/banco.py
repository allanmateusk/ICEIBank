"""Postgres local: usuários e estado bancário por agência.

Sem DATABASE_URL, usuários e estado bancário são voláteis.
"""
import os
import threading

import psycopg
from psycopg.types.json import Jsonb

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
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (824611,))


def _criar_tabelas(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS estado_bancario (
        agencia integer PRIMARY KEY, dados jsonb NOT NULL
    )""")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            usuario text PRIMARY KEY,
            salt bytea NOT NULL,
            hash bytea NOT NULL
        )
        """
    )


def carregar_estado(agencia: int) -> dict | None:
    with _lock:
        if _conn is None:
            return None
        row = _conn.execute("SELECT dados FROM estado_bancario WHERE agencia = %s", (agencia,)).fetchone()
        return row[0] if row else None


def salvar_estado(agencia: int, dados: dict) -> None:
    with _lock:
        if _conn is None:
            return
        _conn.execute("""INSERT INTO estado_bancario (agencia, dados) VALUES (%s, %s)
            ON CONFLICT (agencia) DO UPDATE SET dados = EXCLUDED.dados""", (agencia, Jsonb(dados)))


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
