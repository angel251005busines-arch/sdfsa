"""Состязательные тесты верификатора: порча эталона, текста, параметров."""
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


class TestAcceptsValid(unittest.TestCase):
    def test_procedural_task_is_accepted(self):
        params = make_params()
        verdict = verify_task(valid_task(params), params)
        self.assertTrue(verdict.ok, verdict.report())
        self.assertIsNotNone(verdict.canonical)


class TestSchemaAndSyntax(unittest.TestCase):
    def test_missing_fields(self):
        params = make_params()
        task = copy.deepcopy(valid_task(params))
        del task["reference"]
        verdict = verify_task(task, params)
        self.assertFalse(verdict.ok)
        self.assertIn("missing_field", verdict.codes())

    def test_unparsable_expression(self):
        params = make_params()
        task = copy.deepcopy(valid_task(params))
        task["expression"] = "A ∧ ("
        verdict = verify_task(task, params)
        self.assertIn("parse_error", verdict.codes())

    def test_extra_variable(self):
        params = make_params()
        task = copy.deepcopy(valid_task(params))
        task["expression"] = "A ∧ B ∧ C ∧ D"
        verdict = verify_task(task, params)
        self.assertIn("variable_set", verdict.codes())


class TestParamsConformance(unittest.TestCase):
    def test_forbidden_operation(self):
        params = make_params(operations=("NOT", "AND", "OR"))
        task = copy.deepcopy(valid_task(params))
        task["expression"] = "A ∧ B → C"
        verdict = verify_task(task, params)
        self.assertIn("forbidden_operation", verdict.codes())

    def test_wrong_depth(self):
        params = make_params(depth=2)
        task = copy.deepcopy(valid_task(make_params()))
        verdict = verify_task(task, params)
        self.assertIn("depth_mismatch", verdict.codes())

    def test_difficulty_drift(self):
        params = make_params()
        task = copy.deepcopy(valid_task(params))
        task["difficulty_score"] = 99.0
        verdict = verify_task(task, params)
        self.assertIn("difficulty_drift", verdict.codes())


class TestReferenceCorruption(unittest.TestCase):
    def test_changed_truth_table_cell(self):
        params = make_params()
        task = copy.deepcopy(valid_task(params))
        task["reference"]["rows"][0][-1] ^= 1
        verdict = verify_task(task, params)
        self.assertIn("reference_mismatch", verdict.codes())

    def test_changed_value(self):
        params = make_params(task_type="evaluate")
        task = copy.deepcopy(valid_task(params))
        task["reference"]["value"] ^= 1
        verdict = verify_task(task, params)
        self.assertIn("reference_mismatch", verdict.codes())

    def test_changed_count(self):
        params = make_params(task_type="count_ones")
        task = copy.deepcopy(valid_task(params))
        task["reference"]["value"] += 1
        verdict = verify_task(task, params)
        self.assertIn("reference_mismatch", verdict.codes())

    def test_wrong_minimal_dnf_literals(self):
        params = make_params(task_type="simplify")
        task = copy.deepcopy(valid_task(params))
        task["reference"]["literals"] = 1
        verdict = verify_task(task, params)
        self.assertIn("reference_mismatch", verdict.codes())

    def test_minimal_dnf_not_equivalent(self):
        params = make_params(task_type="simplify")
        task = copy.deepcopy(valid_task(params))
        task["reference"]["text"] = "A ∨ B ∨ C"
        verdict = verify_task(task, params)
        self.assertIn("reference_mismatch", verdict.codes())


class TestPrompt(unittest.TestCase):
    def test_prompt_without_expression_is_rejected(self):
        params = make_params()
        task = copy.deepcopy(valid_task(params))
        task["prompt"] = "Постройте таблицу истинности для логической функции."
        verdict = verify_task(task, params)
        self.assertIn("expression_not_in_prompt", verdict.codes())

    def test_llm_rewording_keeping_formula_is_accepted(self):
        params = make_params()
        task = copy.deepcopy(valid_task(params))
        task["prompt"] = (
            "Задание. Для функции F = " + task["expression"] +
            " от переменных A, B и C заполните таблицу истинности."
        )
        verdict = verify_task(task, params)
        self.assertTrue(verdict.ok, verdict.report())


if __name__ == "__main__":
    unittest.main()
