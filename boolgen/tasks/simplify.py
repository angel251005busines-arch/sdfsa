"""Задание: привести выражение к минимальной ДНФ (МДНФ).

Тонкость: у МДНФ может быть несколько равноправных записей. Поэтому ответ
проверяется не по строке, а по двум свойствам одновременно:
семантическая эквивалентность + минимальное число литералов.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence

from .. import qm
from ..ast import Bin, Node, Not, Var, is_dnf
from ..params import Params
from ..parser import try_parse
from ..semantics import equivalent, minterms
from .base import TaskPlugin, register


def count_dnf_literals(node: Node) -> int:
    """Число литералов в записанной ДНФ."""
    if isinstance(node, Var):
        return 1
    if isinstance(node, Not):
        return 1
    if isinstance(node, Bin) and node.op in ("AND", "OR"):
        return count_dnf_literals(node.left) + count_dnf_literals(node.right)
    raise ValueError("выражение не является ДНФ")


@register
class SimplifyTask(TaskPlugin):
    name = "simplify"
    answer_kind = "dnf"
    MIN_LITERALS = 2  # МДНФ из одного литерала — не задача

    def build(self, node: Node, params: Params, rng: random.Random) -> Dict[str, Any]:
        var_order = params.names()
        terms = qm.minimal_dnf(node, var_order)
        return {
            "display": {},
            "reference": {
                "kind": "dnf",
                "literals": qm.literal_count(terms),
                "text": qm.dnf_to_text(terms, list(var_order)),
                "minterms": list(minterms(node, var_order)),
            },
        }

    def check_reference(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        reference = task.get("reference") or {}
        terms = qm.minimal_dnf(node, var_order)
        expected_literals = qm.literal_count(terms)
        errors: List[str] = []

        claimed = reference.get("literals")
        if claimed != expected_literals:
            errors.append(
                f"в эталоне {claimed} литералов, пересчёт даёт {expected_literals} "
                f"({qm.dnf_to_text(terms, list(var_order))})"
            )

        text = reference.get("text")
        if text is not None:
            candidate, parse_error = try_parse(str(text))
            if candidate is None:
                errors.append(f"эталонная МДНФ не разбирается: {parse_error}")
            elif not equivalent(candidate, node, var_order):
                errors.append(f"эталонная МДНФ {text!r} не эквивалентна выражению")
            elif not is_dnf(candidate):
                errors.append(f"эталон {text!r} не является ДНФ")
            elif count_dnf_literals(candidate) != expected_literals:
                errors.append(
                    f"эталон {text!r} содержит {count_dnf_literals(candidate)} литералов, "
                    f"а минимум — {expected_literals}"
                )
        return errors

    def check_quality(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        literals = qm.literal_count(qm.minimal_dnf(node, var_order))
        if literals < self.MIN_LITERALS:
            return [f"МДНФ содержит {literals} литерал(ов) — задание слишком простое"]
        return []

    def check_answer(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any], answer: Any
    ) -> bool:
        candidate, _error = try_parse(str(answer))
        if candidate is None or not is_dnf(candidate):
            return False
        if not equivalent(candidate, node, var_order):
            return False
        expected = (task.get("reference") or {}).get("literals")
        if expected is None:
            expected = qm.literal_count(qm.minimal_dnf(node, var_order))
        return count_dnf_literals(candidate) == expected
