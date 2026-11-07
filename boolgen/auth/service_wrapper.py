"""Обёртка над TaskService с персональным пулом и статистикой пользователя.

Ядро ``boolgen`` (``service.TaskService``) не меняется. Этот модуль:

* принимает токен сессии и имя пользователя;
* при выдаче заданий использует пользовательскую БД ``data/users/<user>/pool.sqlite``;
* при проверке ответа записывает результат в личную статистику.

Все основные модули ``boolgen`` остаются нетронутыми.
"""
from __future__ import annotations

import json
from typing import Any

from . import sessions, user_pool
from .users import verify_password, user_exists
from ..service import TaskService


class UserTaskService:
    """Сервис заданий с аутентификацией и персональной статистикой."""

    def __init__(self) -> None:
        self._base = TaskService()
        self._pools: dict[str, user_pool.UserPool] = {}

    # -- аутентификация --------------------------------------------------- #
    def register(self, username: str, password: str) -> tuple[bool, str]:
        from .users import register as reg

        return reg(username, password)

    def login(self, username: str, password: str) -> tuple[bool, str | None]:
        """Вернуть ``(ok, token)``."""
        if not verify_password(username, password):
            return False, None
        token = sessions.create_session(username)
        return True, token

    def logout(self, token: str | None) -> None:
        sessions.delete_session(token)

    def current_user(self, token: str | None) -> str | None:
        return sessions.get_user(token)

    def require_user(self, token: str | None) -> str:
        username = sessions.get_user(token)
        if username is None:
            raise PermissionError("требуется вход: /login")
        return username

    def _pool_for(self, username: str) -> user_pool.UserPool:
        pool = self._pools.get(username)
        if pool is None:
            pool = user_pool.UserPool(username)
            self._pools[username] = pool
        return pool

    # -- генерация / выдача ----------------------------------------------- #
    def produce(self, username: str, params) -> dict[str, Any]:
        """Сгенерировать задания в персональный пул пользователя."""
        report = self._base.produce(params, params.count)
        pool = self._pool_for(username)
        for task in report["accepted"]:
            pool.add_task(task)
        return report

    def get_tasks(
        self,
        username: str,
        params,
        count: int | None = None,
    ) -> list[dict[str, Any]]:
        """Выдать задания из персонального пула пользователя (без эталона)."""
        wanted = count if count is not None else params.count
        # гарантируем наличие в персональном пуле
        self.produce(username, params)
        pool = self._pool_for(username)
        tasks = pool.pick_tasks(params.task_type, wanted)
        if len(tasks) < wanted:
            self.produce(username, params)
            tasks = pool.pick_tasks(params.task_type, wanted)
        # вырезаем эталон перед отдачей пользователю
        hidden = {"reference", "seed", "params_fingerprint", "core_version"}
        return [
            {k: v for k, v in t.items() if k not in hidden} for t in tasks
        ]

    # -- проверка ответа --------------------------------------------------- #
    def grade(
        self,
        token: str | None,
        task_id: str,
        params,
        answer: Any,
    ) -> dict[str, Any]:
        """Проверить ответ ученика и записать в личную статистику.

        Возвращает ``{"correct": bool, "task_id": str, "username": str}``.
        """
        username = self.require_user(token)
        pool = self._pool_for(username)
        task = pool.get_task(task_id)
        if task is None:
            raise KeyError(f"задание {task_id!r} не найдено в персональном пуле")

        from ..verify import grade as grade_answer

        correct = grade_answer(task, params, answer)
        pool.record_answer(task_id, params.task_type, answer, bool(correct))
        return {
            "correct": bool(correct),
            "task_id": task_id,
            "username": username,
        }

    # -- статистика -------------------------------------------------------- #
    def stats(self, username: str) -> dict[str, Any]:
        pool = self._pool_for(username)
        return pool.get_stats()

    def close(self) -> None:
        for pool in self._pools.values():
            pool.close()
