"""Задание 2 ЕГЭ: восстановление соответствия столбцов таблицы истинности.

Ключевая особенность — проверка ОДНОЗНАЧНОСТИ: фрагмент таблицы может допускать
несколько перестановок переменных. Тогда задание невалидно, даже если эталонный
ответ «правильный». Это тот слой, который почти всегда забывают.
"""
from __future__ import annotations

import itertools
import random
from typing import Any, Dict, List, Optional, Sequence

from ..ast import Node
from ..generator import GenerationError
from ..params import Params
from ..semantics import evaluate, truth_rows
from .base import TaskPlugin, register


@register
class ColumnsTask(TaskPlugin):
    name = "columns"
    answer_kind = "column_mapping"
    FRAGMENT_ROWS = 3
    MAX_FRAGMENT = 6
    BUILD_ATTEMPTS = 60

    @staticmethod
    def column_names(n: int) -> List[str]:
        return [f"x{i + 1}" for i in range(n)]

    def consistent_permutations(
        self, node: Node, var_order: Sequence[str], table: Sequence[Sequence[int]]
    ) -> List[List[str]]:
        """Все перестановки переменных, согласованные с фрагментом таблицы."""
        n = len(var_order)
        result: List[List[str]] = []
        for perm in itertools.permutations(var_order):
            ok = True
            for row in table:
                cells = [int(v) for v in row[:n]]
                f_value = int(row[n])
                env = {perm[j]: bool(cells[j]) for j in range(n)}
                if int(evaluate(node, env)) != f_value:
                    ok = False
                    break
            if ok:
                result.append(list(perm))
        return result

    def _fragment_variants(self, rng: random.Random, rows):
        """Варианты фрагмента в порядке приоритета.

        Основной формат (как в ЕГЭ): все наборы, при которых F = 1 (или F = 0).
        Дополнительно пробуем частичные фрагменты из 3–4 строк.
        """
        ones = [i for i, (_, value) in enumerate(rows) if value]
        zeros = [i for i, (_, value) in enumerate(rows) if not value]
        if 0 < len(ones) <= self.MAX_FRAGMENT:
            yield "all_ones", ones
        if 0 < len(zeros) <= self.MAX_FRAGMENT:
            yield "all_zeros", zeros
        for _ in range(self.BUILD_ATTEMPTS):
            size = min(rng.choice((self.FRAGMENT_ROWS, 4)), len(rows))
            yield "partial", sorted(rng.sample(range(len(rows)), size))

    def build(self, node: Node, params: Params, rng: random.Random) -> Dict[str, Any]:
        var_order = params.names()
        n = len(var_order)
        rows = truth_rows(node, var_order)

        for fragment_kind, index in self._fragment_variants(rng, rows):
            perm = list(var_order)
            rng.shuffle(perm)
            table: List[List[int]] = []
            for i in index:
                bits, f_value = rows[i]
                cells = [bits[var_order.index(perm[j])] for j in range(n)]
                table.append(cells + [f_value])
            consistent = self.consistent_permutations(node, var_order, table)
            if len(consistent) == 1:
                return {
                    "display": {
                        "header": self.column_names(n) + ["F"],
                        "rows": table,
                        "fragment_kind": fragment_kind,
                    },
                    "reference": {
                        "kind": "column_mapping",
                        "columns": self.column_names(n),
                        "value": consistent[0],
                    },
                }
        raise GenerationError(
            "не удалось построить однозначный фрагмент таблицы "
            "(функция, вероятно, симметрична по переменным)"
        )

    # -- проверки ----------------------------------------------------------- #
    def _table(self, task: Dict[str, Any]) -> Optional[List[List[int]]]:
        display = task.get("display") or {}
        rows = display.get("rows")
        if not isinstance(rows, list) or not rows:
            return None
        try:
            return [[int(v) for v in row] for row in rows]
        except (TypeError, ValueError):
            return None

    def check_reference(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        n = len(var_order)
        errors: List[str] = []
        header = list((task.get("display") or {}).get("header") or [])
        expected_header = self.column_names(n) + ["F"]
        if header != expected_header:
            errors.append(f"шапка таблицы {header!r} вместо {expected_header!r}")

        table = self._table(task)
        if table is None:
            return errors + ["фрагмент таблицы отсутствует или содержит нечисловые значения"]
        if any(len(row) != n + 1 for row in table):
            return errors + [f"ширина строк должна быть {n + 1}"]

        consistent = self.consistent_permutations(node, var_order, table)
        if not consistent:
            return errors + ["фрагмент таблицы противоречит выражению"]
        if len(consistent) > 1:
            errors.append(f"задание неоднозначно: подходит {len(consistent)} перестановок")

        claimed = (task.get("reference") or {}).get("value")
        if list(claimed or []) != consistent[0]:
            errors.append(f"в эталоне {claimed}, пересчёт даёт {consistent[0]}")
        return errors

    def check_uniqueness(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        table = self._table(task)
        if table is None:
            return ["фрагмент таблицы не разбирается"]
        consistent = self.consistent_permutations(node, var_order, table)
        if not consistent:
            return ["фрагмент таблицы противоречит выражению"]
        if len(consistent) > 1:
            return [
                f"задание неоднозначно: {len(consistent)} подходящих перестановок, "
                f"например {consistent[0]} и {consistent[1]}"
            ]
        return []

    def check_quality(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        table = self._table(task)
        if table is None:
            return []
        unique_rows = {tuple(row[:-1]) for row in table}
        if len(unique_rows) != len(table):
            return ["во фрагменте таблицы повторяются строки"]
        return []

    # -- проверка ответа ---------------------------------------------------- #
    def parse_answer(self, var_order: Sequence[str], answer: Any) -> Optional[List[str]]:
        if isinstance(answer, (list, tuple)):
            tokens = [str(tok).strip() for tok in answer]
        else:
            text = str(answer)
            cleaned = "".join(ch for ch in text if not ch.isspace() and ch not in ",;|")
            tokens = list(cleaned)
        lookup = {name.upper(): name for name in var_order}
        parsed: List[str] = []
        for token in tokens:
            name = lookup.get(token.upper())
            if name is None:
                return None
            parsed.append(name)
        return parsed

    def check_answer(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any], answer: Any
    ) -> bool:
        parsed = self.parse_answer(var_order, answer)
        if parsed is None:
            return False
        table = self._table(task)
        if table is not None:
            consistent = self.consistent_permutations(node, var_order, table)
            if len(consistent) == 1:
                return parsed == consistent[0]
            return False
        expected = (task.get("reference") or {}).get("value")
        return parsed == list(expected or [])
