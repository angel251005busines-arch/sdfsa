"""Тесты качества и дедупликации в верификаторе."""
from __future__ import annotations

import copy
import random
import unittest

from boolgen.compose import build_task
from boolgen.params import Params
from boolgen.verify import verify_task


def make_params(**overrides) -> Params:
    base = dict(
        task_type="truth_table",
        operations=("NOT", "AND", "OR", "IMPL"),
        variables=3,
        depth=3,
        nodes_max=17,
        difficulty="any",
        seed=5,
    )
    base.update(overrides)
    return Params(**base).validate()


def valid_task(params: Params, seed: int = 5) -> dict:
    return build_task(params, random.Random(seed), seed=seed)


class TestQuality(unittest.TestCase):
    def test_trivial_expression_rejected(self):
        params = make_params(depth=3, operations=("NOT", "AND"))
        task = copy.deepcopy(valid_task(params))
        task["expression"] = "A ∧ A ∧ (B ∨ C)"
        verdict = verify_task(task, params)
        self.assertIn("trivial_structure", verdict.codes())

    def test_tautology_rejected(self):
        params = make_params(depth=3, operations=("NOT", "OR"))
        task = copy.deepcopy(valid_task(params))
        task["expression"] = "(A ∨ ¬A) ∧ (B ∨ ¬B ∨ C)"
        verdict = verify_task(task, params)
        self.assertIn("tautology", verdict.codes())

    def test_absorption_rejected(self):
        params = make_params(depth=3, operations=("NOT", "AND", "OR"))
        task = copy.deepcopy(valid_task(params))
        task["expression"] = "(A ∨ B ∧ A) ∧ C"
        verdict = verify_task(task, params)
        self.assertIn("absorption", verdict.codes())

    def test_ambiguous_columns_task_rejected(self):
        """Симметричная функция: фрагмент не различает A и B → задание неоднозначно."""
        params = make_params(task_type="columns", variables=2, depth=1, operations=("XOR",))
        task = {
            "task_type": "columns",
            "expression": "A ⊕ B",
            "variables": ["A", "B"],
            "var_order": ["A", "B"],
            "prompt": "Функция F = A ⊕ B: определите столбцы переменных A и B.",
            "display": {"header": ["x1", "x2", "F"], "rows": [[0, 1, 1]]},
            "reference": {"kind": "column_mapping", "columns": ["x1", "x2"],
                          "value": ["A", "B"]},
        }
        verdict = verify_task(task, params)
        self.assertIn("ambiguous", verdict.codes())

    def test_columns_task_with_broken_table_rejected(self):
        params = make_params(task_type="columns")
        task = copy.deepcopy(valid_task(params))
        task["display"]["rows"][0][-1] ^= 1  # испорченное значение F
        verdict = verify_task(task, params)
        self.assertTrue(
            {"ambiguous", "reference_mismatch"} & set(verdict.codes()), verdict.codes()
        )


class TestDedup(unittest.TestCase):
    def test_duplicate_signature_rejected(self):
        params = make_params()
        task = valid_task(params)
        first = verify_task(task, params)
        second = verify_task(task, params, seen={first.canonical})
        self.assertIn("duplicate", second.codes())

    def test_reordered_operands_are_duplicates(self):
        params = make_params(operations=("AND",), depth=1, variables=2)
        task = copy.deepcopy(valid_task(params))
        first = verify_task(task, params)
        task["expression"] = "B ∧ A"
        second = verify_task(task, params, seen={first.canonical})
        self.assertIn("duplicate", second.codes())


if __name__ == "__main__":
    unittest.main()
