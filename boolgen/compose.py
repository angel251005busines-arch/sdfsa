"""Сборка задания: параметры → выражение → тело задания → формулировка.

Здесь намеренно НЕТ проверок: собранное задание обязательно прогоняется через
:mod:`boolgen.verify`. Единственная защита на этом шаге — повторить попытку,
если плагин не смог построить задание (например, для `columns` попался
симметричный фрагмент таблицы).
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List, Optional

from . import CORE_VERSION
from .ast import to_text
from .generator import GenerationError, generate_expression
from .metrics import difficulty_score
from .params import Params
from .phrasing import build_prompt
from .tasks import get as get_plugin

MAX_BUILD_ATTEMPTS = 10


class BuildError(RuntimeError):
    """Не удалось собрать задание по заданным параметрам."""


def make_rng(seed: Optional[int]) -> random.Random:
    return random.Random(seed)


def task_id(task: Dict[str, Any]) -> str:
    raw = "|".join(
        [
            str(task.get("task_type")),
            str(task.get("expression")),
            str(task.get("seed")),
            json.dumps(task.get("display"), sort_keys=True, ensure_ascii=False),
            json.dumps(task.get("reference"), sort_keys=True, ensure_ascii=False),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def build_task(params: Params, rng: random.Random, seed: Optional[int] = None) -> Dict[str, Any]:
    """Собрать одно задание (без проверки — её выполняет верификатор)."""
    plugin = get_plugin(params.task_type)
    var_order = list(params.names())
    last_error: Optional[Exception] = None

    for _ in range(MAX_BUILD_ATTEMPTS):
        node = generate_expression(params, rng)
        try:
            body = plugin.build(node, params, rng)
        except GenerationError as exc:  # например, фрагмент таблицы оказался неоднозначным
            last_error = exc
            continue

        task: Dict[str, Any] = {
            "task_type": params.task_type,
            "expression": to_text(node),
            "variables": var_order,
            "var_order": var_order,
            "display": body["display"],
            "reference": body["reference"],
            "answer_kind": plugin.answer_kind,
            "difficulty_score": difficulty_score(node, var_order),
            "source": params.source,
            "core_version": CORE_VERSION,
            "seed": seed,
            "params_fingerprint": params.fingerprint(),
        }
        task["prompt"] = build_prompt(task, params.style)
        task["id"] = task_id(task)
        return task

    raise BuildError(
        f"не удалось собрать задание типа {params.task_type} за {MAX_BUILD_ATTEMPTS} попыток: "
        f"{last_error}"
    )


def build_batch(params: Params) -> List[Dict[str, Any]]:
    """Собрать пакет заданий по параметрам (seed управляет всей пачкой)."""
    seed = params.seed if params.seed is not None else random.randrange(1, 2 ** 31)
    rng = make_rng(seed)
    tasks: List[Dict[str, Any]] = []
    for _ in range(params.count):
        tasks.append(build_task(params, rng, seed=seed))
    return tasks
