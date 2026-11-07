"""Персональный пул заданий и статистика пользователя.

Каждый пользователь получает свою отдельную базу:
``data/users/<username>/pool.sqlite``.

В ней таблицы:

* ``tasks`` — опубликованные задания (аналогично общему пулу, но личные);
* ``answers`` — ответы пользователя (задание, ответ, верно/неверно, время);
* ``stats`` — агрегированная статистика по типам и сложности.

Ядро ``boolgen`` не знает об этой базе; она управляется только из этого модуля
и из :mod:`boolgen.auth.service_wrapper`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id                 TEXT PRIMARY KEY,
    task_type          TEXT NOT NULL,
    expression         TEXT NOT NULL,
    difficulty_score   REAL NOT NULL,
    source             TEXT NOT NULL,
    core_version       TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'published',
    payload            TEXT NOT NULL,
    created_at         REAL NOT NULL,
    served_count       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS answers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id        TEXT NOT NULL,
    task_type      TEXT NOT NULL,
    answer         TEXT NOT NULL,
    correct        INTEGER NOT NULL,
    answered_at    REAL NOT NULL,
    username       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stats (
    username       TEXT NOT NULL,
    task_type      TEXT NOT NULL,
    difficulty     TEXT,
    total          INTEGER NOT NULL DEFAULT 0,
    correct        INTEGER NOT NULL DEFAULT 0,
    last_answered  REAL,
    PRIMARY KEY (username, task_type, difficulty)
);
"""


class UserPool:
    """Персональная база заданий и статистики одного пользователя."""

    def __init__(self, username: str) -> None:
        self.username = username
        base = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "users", username
        )
        os.makedirs(base, exist_ok=True)
        self.db_path = os.path.join(base, "pool.sqlite")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- задания ----------------------------------------------------------- #
    def add_task(self, task: dict[str, Any]) -> bool:
        payload = json.dumps(task, ensure_ascii=False, sort_keys=True)
        try:
            self.conn.execute(
                "INSERT INTO tasks (id, task_type, expression, difficulty_score,"
                " source, core_version, status, payload, created_at, served_count)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    str(task.get("id") or ""),
                    str(task.get("task_type")),
                    str(task.get("expression")),
                    float(task.get("difficulty_score") or 0.0),
                    str(task.get("source") or "procedural"),
                    str(task.get("core_version") or ""),
                    "published",
                    payload,
                    time.time(),
                    0,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def pick_tasks(self, task_type: str, count: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, payload FROM tasks WHERE task_type=? AND status='published'"
            " ORDER BY served_count ASC, created_at ASC LIMIT ?",
            (task_type, count),
        ).fetchall()
        tasks = [json.loads(row["payload"]) for row in rows]
        for row in rows:
            self.conn.execute(
                "UPDATE tasks SET served_count = served_count + 1 WHERE id=?",
                (row["id"],),
            )
        self.conn.commit()
        return tasks

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    # -- ответы и статистика ---------------------------------------------- #
    def record_answer(
        self,
        task_id: str,
        task_type: str,
        answer: Any,
        correct: bool,
    ) -> None:
        answered_at = time.time()
        answer_text = (
            answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        )
        self.conn.execute(
            "INSERT INTO answers (task_id, task_type, answer, correct, answered_at, username)"
            " VALUES (?,?,?,?,?,?)",
            (task_id, task_type, answer_text, int(correct), answered_at, self.username),
        )
        difficulty = self._task_difficulty(task_id)
        self.conn.execute(
            "INSERT INTO stats (username, task_type, difficulty, total, correct, last_answered)"
            " VALUES (?,?,?,1,?,?)"
            " ON CONFLICT(username, task_type, difficulty) DO UPDATE SET"
            " total = total + 1,"
            " correct = correct + ? ,"
            " last_answered = ?",
            (
                self.username,
                task_type,
                difficulty,
                int(correct),
                answered_at,
                int(correct),
                answered_at,
            ),
        )
        self.conn.commit()

    def _task_difficulty(self, task_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT payload FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        task = json.loads(row["payload"])
        score = float(task.get("difficulty_score") or 0.0)
        if score < 2.6:
            return "easy"
        if score < 4.2:
            return "medium"
        return "hard"

    def get_stats(self) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT task_type, difficulty, total, correct, last_answered FROM stats"
            " WHERE username=? ORDER BY task_type, difficulty",
            (self.username,),
        ).fetchall()
        by_type: dict[str, dict[str, Any]] = {}
        total_all = 0
        correct_all = 0
        for row in rows:
            tt = row["task_type"]
            diff = row["difficulty"] or "unknown"
            total = row["total"]
            correct = row["correct"]
            total_all += total
            correct_all += correct
            by_type.setdefault(tt, {})[diff] = {
                "total": total,
                "correct": correct,
                "last_answered": row["last_answered"],
            }
        return {
            "username": self.username,
            "total": total_all,
            "correct": correct_all,
            "by_type": by_type,
        }

    def close(self) -> None:
        self.conn.close()
