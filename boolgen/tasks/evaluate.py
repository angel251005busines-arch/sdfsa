"""Задание: вычислить значение выражения на заданном наборе переменных."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence

from ..ast import Node
from ..params import Params
from ..semantics import evaluate
from .base import TaskPlugin, normalize_bits, register


@register
class EvaluateTask(TaskPlugin):
    name = "evaluate"
    answer_kind = "value"

    def build(self, node: Node, params: Params, rng: random.Random) -> Dict[str, Any]:
        var_order = params.names()
        assignment = {name: rng.choice([0, 1]) for name in var_order}
        value = int(evaluate(node, {k: bool(v) for k, v in assignment.items()}))
        return {
            "display": {"assignment": assignment},
            "reference": {"kind": "value", "value": value},
        }

    def _assignment(self, var_order: Sequence[str], task: Dict[str, Any]):
        display = task.get("display") or {}
        assignment = display.get("assignment") or {}
        if set(assignment) != set(var_order):
            raise ValueError(
                f"набор задан для {sorted(assignment)}, ожидались {sorted(var_order)}"
            )
        return {name: bool(normalize_bits([assignment[name]])[0]) for name in var_order}

    def check_reference(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        try:
            env = self._assignment(var_order, task)
        except ValueError as exc:
            return [str(exc)]
        expected = int(evaluate(node, env))
        claimed = (task.get("reference") or {}).get("value")
        try:
            claimed_norm = normalize_bits([claimed])[0]
        except ValueError:
            return [f"эталонное значение {claimed!r} не является 0/1"]
        if claimed_norm != expected:
            return [f"эталонное значение {claimed_norm}, пересчёт даёт {expected}"]
        return []

    def check_answer(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any], answer: Any
    ) -> bool:
        try:
            env = self._assignment(var_order, task)
            given = normalize_bits([answer])[0]
        except (ValueError, TypeError):
            return False
        return given == int(evaluate(node, env))
