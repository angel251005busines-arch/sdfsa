"""Задание: построить таблицу истинности."""
from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence

from ..ast import Node
from ..params import Params
from ..semantics import truth_rows
from .base import TaskPlugin, normalize_bits, register


@register
class TruthTableTask(TaskPlugin):
    name = "truth_table"
    answer_kind = "truth_table"

    def _table(self, node: Node, var_order: Sequence[str]) -> List[List[int]]:
        return [[*bits, value] for bits, value in truth_rows(node, var_order)]

    def _header(self, var_order: Sequence[str]) -> List[str]:
        return list(var_order) + ["F"]

    def build(self, node: Node, params: Params, rng: random.Random) -> Dict[str, Any]:
        var_order = params.names()
        return {
            "display": {"header": self._header(var_order)},
            "reference": {
                "kind": "truth_table",
                "header": self._header(var_order),
                "rows": self._table(node, var_order),
            },
        }

    def check_reference(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        reference = task.get("reference") or {}
        header = self._header(var_order)
        errors: List[str] = []
        if list(reference.get("header") or []) != header:
            errors.append(f"шапка {reference.get('header')!r} вместо {header!r}")

        actual = self._table(node, var_order)
        claimed = reference.get("rows")
        if not isinstance(claimed, list) or len(claimed) != len(actual):
            got = len(claimed) if isinstance(claimed, list) else "?"
            errors.append(f"в эталоне {got} строк вместо {len(actual)}")
            return errors
        try:
            claimed_norm = [normalize_bits(row) for row in claimed]
        except ValueError as exc:
            errors.append(f"эталонная таблица не разбирается: {exc}")
            return errors
        for i, (expected, given) in enumerate(zip(actual, claimed_norm)):
            if expected != given:
                errors.append(f"строка {i}: в эталоне {given}, пересчёт даёт {expected}")
        return errors

    def check_answer(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any], answer: Any
    ) -> bool:
        try:
            rows = [normalize_bits(row) for row in answer]
        except (ValueError, TypeError):
            return False
        return rows == self._table(node, var_order)
