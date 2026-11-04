"""Пул проверенных заданий на SQLite.

Модель работы: задания генерируются и проверяются ЗАРАНЕЕ (воркером), а выдача
пользователю идёт из пула — быстро и без риска «а модель сейчас не ответила».
В пуле хранятся только задания, прошедшие верификатор; брак уходит в карантин
вместе со списком нарушений (это метрика качества модели/промпта).

Дедупликация — по канонической подписи функции (не зависит от имён переменных
и порядка операндов), поэтому «A∧B» и «B∧A» не попадут в пул дважды.
"""
from __future__ import annotations

import functools
import json
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id                 TEXT PRIMARY KEY,
    task_type          TEXT NOT NULL,
    expression         TEXT NOT NULL,
    signature          TEXT NOT NULL,
    params_fingerprint TEXT NOT NULL,
    difficulty_score   REAL NOT NULL,
    seed               INTEGER,
    source             TEXT NOT NULL,
    core_version       TEXT NOT NULL,
    status             TEXT NOT NULL,
    payload            TEXT NOT NULL,
    violations         TEXT NOT NULL DEFAULT '[]',
    created_at         REAL NOT NULL,
    served_count       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_pick ON tasks(task_type, params_fingerprint, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_sig ON tasks(task_type, signature, params_fingerprint);
"""

PUBLISHED = "published"
QUARANTINED = "quarantined"

Signature = Tuple[int, int]


def signature_of(verdict: Any) -> str:
    canonical = getattr(verdict, "canonical", None)
    if canonical is None:
        return ""
    return f"{canonical[0]}:{canonical[1]}"


def parse_signature(text: str) -> Optional[Signature]:
    if not text or ":" not in text:
        return None
    left, right = text.split(":", 1)
    try:
        return int(left), int(right)
    except ValueError:
        return None


class TaskPool:
    """Хранилище заданий. ``path=':memory:'`` — для тестов."""

    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        # check_same_thread=False + блокировка: HTTP-сервер многопоточный.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.conn.executescript(SCHEMA)
        self.conn.commit()


    # -- запись ------------------------------------------------------------- #
    def add(self, task: Dict[str, Any], verdict: Any, status: Optional[str] = None) -> bool:
        """Добавить задание. Возвращает ``False``, если такое уже есть."""
        status = status or (PUBLISHED if getattr(verdict, "ok", False) else QUARANTINED)
        payload = json.dumps(task, ensure_ascii=False, sort_keys=True)
        violations = json.dumps(
            [
                {"layer": v.layer, "code": v.code, "message": v.message}
                for v in getattr(verdict, "violations", [])
            ],
            ensure_ascii=False,
        )
        try:
            self.conn.execute(
                "INSERT INTO tasks (id, task_type, expression, signature, params_fingerprint,"
                " difficulty_score, seed, source, core_version, status, payload, violations, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(task.get("id") or ""),
                    str(task.get("task_type")),
                    str(task.get("expression")),
                    signature_of(verdict),
                    str(task.get("params_fingerprint") or ""),
                    float(task.get("difficulty_score") or 0.0),
                    task.get("seed"),
                    str(task.get("source") or "procedural"),
                    str(task.get("core_version") or ""),
                    status,
                    payload,
                    violations,
                    time.time(),
                ),
            )
        except sqlite3.IntegrityError:
            return False
        self.conn.commit()
        return True

    # -- чтение ------------------------------------------------------------- #
    def seen_signatures(self, task_type: str, params_fingerprint: str) -> Set[Signature]:
        """Канонические подписи уже опубликованных заданий этих параметров."""
        rows = self.conn.execute(
            "SELECT signature FROM tasks WHERE task_type=? AND params_fingerprint=? AND status=?",
            (task_type, params_fingerprint, PUBLISHED),
        ).fetchall()
        found: Set[Signature] = set()
        for row in rows:
            signature = parse_signature(row["signature"])
            if signature is not None:
                found.add(signature)
        return found

    def pick(
        self,
        task_type: str,
        params_fingerprint: str,
        count: int = 1,
        least_served: bool = True,
        mark_served: bool = False,
    ) -> List[Dict[str, Any]]:
        """Взять задания из пула (по умолчанию — реже всего выдававшиеся)."""
        order = "served_count ASC, created_at ASC" if least_served else "RANDOM()"
        rows = self.conn.execute(
            f"SELECT id, payload FROM tasks"
            f" WHERE task_type=? AND params_fingerprint=? AND status=?"
            f" ORDER BY {order} LIMIT ?",
            (task_type, params_fingerprint, PUBLISHED, count),
        ).fetchall()
        tasks = [json.loads(row["payload"]) for row in rows]
        if mark_served:
            for row in rows:
                self.conn.execute(
                    "UPDATE tasks SET served_count = served_count + 1 WHERE id=?", (row["id"],)
                )
            self.conn.commit()
        return tasks

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Достать задание по идентификатору (None, если нет)."""
        row = self.conn.execute(
            "SELECT payload FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def quarantined(self, limit: int = 50) -> List[Tuple[str, str, List[Dict[str, str]]]]:
        rows = self.conn.execute(
            "SELECT id, expression, violations FROM tasks WHERE status=? LIMIT ?",
            (QUARANTINED, limit),
        ).fetchall()
        return [
            (row["id"], row["expression"], json.loads(row["violations"] or "[]"))
            for row in rows
        ]

    def stats(self) -> Dict[str, Any]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
        ).fetchall()
        by_status = {row["status"]: row["n"] for row in rows}
        total = sum(by_status.values())
        published = by_status.get(PUBLISHED, 0)
        return {
            "total": total,
            "published": published,
            "quarantined": by_status.get(QUARANTINED, 0),
            "reject_rate": round(1 - published / total, 3) if total else 0.0,
        }

    def close(self) -> None:
        self.conn.close()


def _synchronized(method: Callable[..., Any]) -> Callable[..., Any]:
    """Сериализовать доступ к соединению SQLite (сервер многопоточный)."""

    @functools.wraps(method)
    def wrapper(self: "TaskPool", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


# Публичные методы работают с одним соединением, поэтому синхронизируются.
for _name in ("add", "get", "seen_signatures", "pick", "quarantined", "stats", "close"):
    setattr(TaskPool, _name, _synchronized(getattr(TaskPool, _name)))

