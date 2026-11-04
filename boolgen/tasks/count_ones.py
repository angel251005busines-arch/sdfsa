"""Задание: сколько наборов переменных дают F = 1 (типичный вопрос ЕГЭ)."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence

from ..ast import Node
from ..params import Params
from ..semantics import count_ones
from .base import TaskPlugin, register


@register
class CountOnesTask(TaskPlugin):
    name = "count_ones"
    answer_kind = "int"

    def build(self, node: Node, params: Params, rng: random.Random) -> Dict[str, Any]:
        var_order = params.names()
        return {
            "display": {"rows": 1 << len(var_order)},
            "reference": {"kind": "int", "value": count_ones(node, var_order)},
        }

    def check_reference(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        expected = count_ones(node, var_order)
        claimed = (task.get("reference") or {}).get("value")
        try:
            given = int(claimed)
        except (TypeError, ValueError):
            return [f"эталонное значение {claimed!r} не является числом"]
        if given != expected:
            return [f"в эталоне {given} наборов, пересчёт даёт {expected}"]
        return []

    def check_answer(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any], answer: Any
    ) -> bool:
        try:
            return int(str(answer).strip()) == count_ones(node, var_order)
        except (TypeError, ValueError):
            return False
