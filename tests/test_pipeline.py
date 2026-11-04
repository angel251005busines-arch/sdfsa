"""Property-тесты сквозного конвейера: ни ложных пропусков, ни ложных отказов."""
from __future__ import annotations

import unittest

from boolgen.params import TASK_TYPES, Params
from boolgen.service import TaskService
from boolgen.verify import grade, verify_task

MIXED = ("NOT", "AND", "OR", "IMPL", "XOR", "EQV")


class TestPipeline(unittest.TestCase):
    def test_accepted_tasks_always_verify(self):
        """Всё, что сервис отдал как принятое, обязано проходить верификатор."""
        combos = [
            (task_type, difficulty, depth)
            for task_type in TASK_TYPES
            for difficulty, depth in (("easy", 2), ("medium", 3), ("hard", 4))
        ]
        for task_type, difficulty, depth in combos:
            params = Params(
                task_type=task_type,
                operations=MIXED,
                variables=3,
                depth=depth,
                nodes_max=19,
                difficulty=difficulty,
                count=2,
                seed=17,
            ).validate()
            report = TaskService().produce(params, 2)
            with self.subTest(task_type=task_type, difficulty=difficulty):
                self.assertEqual(len(report["accepted"]), 2, report["rejected"][:1])
                for task in report["accepted"]:
                    verdict = verify_task(task, params)
                    self.assertTrue(verdict.ok, f"{task['expression']}: {verdict.report()}")

    def test_reference_answers_grade_true(self):
        from boolgen.compose import build_task
        from boolgen.params import Params
        import random

        answer_of = {
            "truth_table": lambda t: t["reference"]["rows"],
            "evaluate": lambda t: t["reference"]["value"],
            "count_ones": lambda t: t["reference"]["value"],
            "columns": lambda t: "".join(t["reference"]["value"]),
            "simplify": lambda t: t["reference"]["text"],
        }
        for task_type in TASK_TYPES:
            params = Params(
                task_type=task_type,
                operations=MIXED,
                variables=3,
                depth=3,
                nodes_max=17,
                difficulty="medium",
                seed=21,
            ).validate()
            for seed in (21, 22, 23):
                task = build_task(params, random.Random(seed), seed=seed)
                with self.subTest(task_type=task_type, seed=seed):
                    self.assertTrue(grade(task, params, answer_of[task_type](task)))

    def test_batch_has_no_duplicate_signatures(self):
        from boolgen.params import Params

        params = Params(
            task_type="truth_table",
            operations=MIXED,
            variables=3,
            depth=3,
            nodes_max=17,
            difficulty="medium",
            count=6,
            seed=29,
        ).validate()
        report = TaskService().produce(params, 6)
        signatures = [
            verify_task(task, params).canonical for task in report["accepted"]
        ]
        self.assertEqual(len(signatures), len(set(signatures)))


if __name__ == "__main__":
    unittest.main()
