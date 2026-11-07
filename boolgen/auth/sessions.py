"""Сессии: токен → пользователь.

Хранилище: ``data/users/sessions.db`` (SQLITE). Токен — случайный UUID.
Сессия истекает через ``SESSION_TTL_SECONDS`` (по умолчанию 7 дней).
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import time
from typing import Optional

SESSIONS_DB = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "users", "sessions.db"
)
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60


def _connect(db_path: str = SESSIONS_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token     TEXT PRIMARY KEY,
            username  TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def create_session(username: str, ttl: int = SESSION_TTL_SECONDS) -> str:
    """Создать сессию и вернуть токен."""
    now = time.time()
    token = secrets.token_urlsafe(32)
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO sessions (token, username, created_at, expires_at) "
            "VALUES (?,?,?,?)",
            (token, username, now, now + ttl),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def get_user(token: str | None) -> str | None:
    """Вернуть имя пользователя по токену сессии, или ``None`` если не валиден."""
    if not token:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT username, expires_at FROM sessions WHERE token=?", (token,)
        ).fetchone()
        if row is None:
            return None
        username, expires_at = row
        if time.time() > expires_at:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
            return None
        return username
    finally:
        conn.close()


def delete_session(token: str | None) -> None:
    """Завершить сессию (выход)."""
    if not token:
        return
    conn = _connect()
    try:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()


def cleanup_expired() -> int:
    """Удалить истёкшие сессии. Вернуть число удалённых."""
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?", (time.time(),)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
