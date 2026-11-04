"""Тесты типов заданий: сборка, проверка и оценка ответов ученика."""
from __future__ import annotations

import random
import unittest

from boolgen.compose import build_task
from boolgen.params import TASK_TYPES, Params
from boolgen.service import public_view
from boolgen.verify import grade, verify_task


def params_for(task_type: str, **overrides) -> Params:
    base = dict(
        task_type=task_type,
        operations=("NOT", "AND", "OR", "IMPL"),
        variables=3,
        depth=3,
        nodes_max=17,
        difficulty="medium",
        seed=4,
    )
    base.update(overrides)
    return Params(**base).validate()


class TestAllTypes(unittest.TestCase):
    def test_each_type_builds_and_verifies(self):
        for task_type in TASK_TYPES:
            params = params_for(task_type)
            task = build_task(params, random.Random(4), seed=4)
            with self.subTest(task_type=task_type):
                verdict = verify_task(task, params)
                self.assertTrue(verdict.ok, f"{task_type}: {verdict.report()}")
                self.assertIn(task["expression"], task["prompt"])

    def test_public_view_hides_reference(self):
        params = params_for("columns")
        task = build_task(params, random.Random(4), seed=4)
        public = public_view(task)
        self.assertNotIn("reference", public)
        self.assertNotIn("seed", public)
        self.assertIn("prompt", public)


class TestGrading(unittest.TestCase):
    def test_correct_answers_accepted(self):
        cases = {
            "truth_table": lambda task: task["reference"]["rows"],
            "evaluate": lambda task: task["reference"]["value"],
            "count_ones": lambda task: task["reference"]["value"],
            "columns": lambda task: "".join(task["reference"]["value"]),
            "simplify": lambda task: task["reference"]["text"],
        }
        for task_type, answer_of in cases.items():
            params = params_for(task_type)
            task = build_task(params, random.Random(4), seed=4)
            with self.subTest(task_type=task_type):
                self.assertTrue(grade(task, params, answer_of(task)))

    def test_wrong_answers_rejected(self):
        params = params_for("count_ones")
        task = build_task(params, random.Random(4), seed=4)
        wrong = task["reference"]["value"] + 1
        self.assertFalse(grade(task, params, wrong))
        self.assertFalse(grade(task, params, "не число"))

    def test_truth_table_answer_accepts_strings(self):
        params = params_for("truth_table")
        task = build_task(params, random.Random(4), seed=4)
        rows = task["reference"]["rows"]
        as_strings = [[str(cell) for cell in row] for row in rows]
        self.assertTrue(grade(task, params, as_strings))
        broken = [row[:] for row in as_strings]
        broken[0][-1] = "1" if broken[0][-1] == "0" else "0"
        self.assertFalse(grade(task, params, broken))

    def test_columns_answer_formatting(self):
        params = params_for("columns")
        task = build_task(params, random.Random(4), seed=4)
        answer = task["reference"]["value"]
        variants = [
            "".join(answer),
            " ".join(answer),
            "".join(answer).lower(),
            ",".join(answer),
            answer,
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertTrue(grade(task, params, variant))
        reversed_answer = "".join(reversed(answer))
        if reversed_answer != "".join(answer):
            self.assertFalse(grade(task, params, reversed_answer))


class TestSimplifyGrading(unittest.TestCase):
    def test_equivalent_minimal_form_is_accepted(self):
        params = params_for("simplify")
        for seed in range(1, 30):
            task = build_task(params, random.Random(seed), seed=seed)
            text = task["reference"]["text"]
            if "∨" in text:
                terms = text.split("∨")
                reordered = "∨".join(reversed(terms))
                with self.subTest(text=text):
                    self.assertTrue(grade(task, params, reordered))
                    self.assertFalse(grade(task, params, text + "∨" + terms[0]))
                return
        self.skipTest("не нашлось МДНФ из нескольких термов")


if __name__ == "__main__":
    unittest.main()
