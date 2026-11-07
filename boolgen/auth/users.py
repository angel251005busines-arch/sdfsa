"""Реестр пользователей: регистрация, вход, проверка пароля.

Хранилище: ``data/users/users.db`` (SQLite). Пароли не хранятся открыто —
только хеш PBKDF2-HMAC-SHA256 с солью. Все примитивы из стандартной
библиотеки, сторонних зависимостей нет.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from typing import Optional

USERS_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "users", "users.db")


def _connect(db_path: str = USERS_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username   TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt       TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()


def _make_salt() -> str:
    return os.urandom(16).hex()


def register(username: str, password: str) -> tuple[bool, str]:
    """Зарегистрировать пользователя.

    Возвращает ``(ok, message)``.
    """
    username = username.strip()
    if not username or len(username) < 3:
        return False, "логин должен содержать не менее 3 символов"
    if not password or len(password) < 4:
        return False, "пароль должен содержать не менее 4 символов"

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username=?", (username,)
        ).fetchone()
        if row is not None:
            return False, "пользователь с таким логином уже существует"

        salt = _make_salt()
        pw_hash = _hash_password(password, salt)
        import time

        conn.execute(
            "INSERT INTO users (username, password_hash, salt, created_at) "
            "VALUES (?,?,?,?)",
            (username, pw_hash, salt, time.time()),
        )
        conn.commit()
        return True, "пользователь зарегистрирован"
    finally:
        conn.close()


def verify_password(username: str, password: str) -> bool:
    """Проверить логин и пароль."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE username=?", (username,)
        ).fetchone()
        if row is None:
            return False
        pw_hash, salt = row
        return _hash_password(password, salt) == pw_hash
    finally:
        conn.close()


def user_exists(username: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        return row is not None
    finally:
        conn.close()


def list_users() -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT username FROM users ORDER BY username").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()
