"""Сервисный слой: генерация → проверка → пул → выдача.

Это то место, где склеиваются все части. Правила здесь простые:

* в выдачу пользователю попадают только задания со статусом ``published``;
* при выдаче из задания вырезается эталон (иначе ответ утечёт в браузер);
* брак не выбрасывается, а уходит в карантин с перечнем нарушений.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .compose import BuildError, build_task
from .llm import PhraseDriver, TemplateDriver
from .params import Params
from .pool import TaskPool

from .verify import Verdict, verify_task


def public_view(task: Dict[str, Any]) -> Dict[str, Any]:
    """Представление задания для ученика: без эталона и служебных полей."""
    hidden = {"reference", "seed", "params_fingerprint", "core_version"}
    return {key: value for key, value in task.items() if key not in hidden}


class TaskService:
    """Оркестратор: собрать, проверить, положить в пул, выдать."""

    def __init__(
        self,
        pool: Optional[TaskPool] = None,
        driver: Optional[PhraseDriver] = None,
        pool_path: str = ":memory:",
    ) -> None:
        self.pool = pool or TaskPool(pool_path)
        self.driver = driver or TemplateDriver()

    # -- производство ------------------------------------------------------- #
    def produce(self, params: Params, count: Optional[int] = None) -> Dict[str, Any]:
        """Сгенерировать и проверить задания, пополнив пул."""
        wanted = count if count is not None else params.count
        fingerprint = params.fingerprint()
        seen = self.pool.seen_signatures(params.task_type, fingerprint)
        seed = params.seed if params.seed is not None else random.randrange(1, 2 ** 31)
        rng = random.Random(seed)

        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        attempts = 0
        max_attempts = max(wanted * 5, 20)

        while len(accepted) < wanted and attempts < max_attempts:
            attempts += 1
            try:
                task = build_task(params, rng, seed=seed)
            except BuildError as exc:
                rejected.append({"stage": "build", "error": str(exc)})
                continue

            task = dict(task)
            task["prompt"] = self.driver.phrase(task)
            verdict = verify_task(task, params, seen=seen)
            self.pool.add(task, verdict)

            if verdict.ok and verdict.canonical is not None:
                seen.add(verdict.canonical)
                accepted.append(task)
            else:
                rejected.append(
                    {
                        "stage": "verify",
                        "expression": task.get("expression"),
                        "violations": [str(v) for v in verdict.violations],
                    }
                )

        return {
            "accepted": accepted,
            "rejected": rejected,
            "attempts": attempts,
            "stats": self.pool.stats(),
        }

    # -- выдача ------------------------------------------------------------- #
    def get_tasks(self, params: Params, count: Optional[int] = None) -> List[Dict[str, Any]]:
        """Выдать задания из пула; при нехватке — догенерировать."""
        wanted = count if count is not None else params.count
        self.produce(params, wanted)  # гарантирует наличие (дедуп не даст дублей)
        tasks = self.pool.pick(
            params.task_type, params.fingerprint(), count=wanted, mark_served=True
        )
        if len(tasks) < wanted:
            self.produce(params, wanted - len(tasks))
            tasks = self.pool.pick(
                params.task_type, params.fingerprint(), count=wanted, mark_served=True
            )
        return [public_view(task) for task in tasks]

    # -- проверка ответа ---------------------------------------------------- #
    def grade(self, task_id: str, params: Params, answer: Any) -> bool:
        from .verify import grade as grade_answer

        task = self.pool.get(task_id)
        if task is None:
            raise KeyError(f"задание {task_id!r} не найдено в пуле")
        return grade_answer(task, params, answer)


def check_batch(tasks: List[Dict[str, Any]], params: Params) -> List[Verdict]:
    """Проверить готовый пакет (например, ответ LLM-генератора) без записи в пул."""
    seen: set = set()
    verdicts: List[Verdict] = []
    for task in tasks:
        verdict = verify_task(task, params, seen=seen)
        if verdict.ok and verdict.canonical is not None:
            seen.add(verdict.canonical)
        verdicts.append(verdict)
    return verdicts
