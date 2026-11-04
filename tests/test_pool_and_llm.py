"""Тесты пула заданий и LLM-драйвера формулировок."""
from __future__ import annotations

import random
import unittest

from boolgen.compose import build_task
from boolgen.llm import OpenAICompatDriver, TemplateDriver, make_driver
from boolgen.params import Params
from boolgen.pool import QUARANTINED, TaskPool
from boolgen.verify import verify_task


def params_for(**overrides) -> Params:
    base = dict(
        task_type="truth_table",
        operations=("NOT", "AND", "OR", "IMPL"),
        variables=3,
        depth=3,
        nodes_max=17,
        difficulty="medium",
        seed=8,
    )
    base.update(overrides)
    return Params(**base).validate()


class TestPool(unittest.TestCase):
    def setUp(self):
        self.pool = TaskPool(":memory:")
        self.params = params_for()
        self.task = build_task(self.params, random.Random(8), seed=8)
        self.verdict = verify_task(self.task, self.params)

    def tearDown(self):
        self.pool.close()

    def test_add_and_dedup(self):
        self.assertTrue(self.pool.add(self.task, self.verdict))
        self.assertFalse(self.pool.add(self.task, self.verdict))  # уникальный индекс
        self.assertEqual(self.pool.stats()["published"], 1)

    def test_quarantine_counted_in_stats(self):
        broken = dict(self.task)
        broken["reference"] = {"kind": "value", "value": 999}
        bad_verdict = verify_task(broken, self.params)
        self.assertFalse(bad_verdict.ok)
        self.assertTrue(self.pool.add(broken, bad_verdict))
        stats = self.pool.stats()
        self.assertEqual(stats["quarantined"], 1)
        self.assertEqual(stats["reject_rate"], 1.0)

    def test_pick_and_get(self):
        self.pool.add(self.task, self.verdict)
        picked = self.pool.pick("truth_table", self.params.fingerprint(), count=5,
                                mark_served=True)
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0]["id"], self.task["id"])
        stored = self.pool.get(self.task["id"])
        self.assertEqual(stored["expression"], self.task["expression"])
        self.assertIsNone(self.pool.get("нет-такого-id"))

    def test_seen_signatures(self):
        self.pool.add(self.task, self.verdict)
        seen = self.pool.seen_signatures("truth_table", self.params.fingerprint())
        self.assertIn(self.verdict.canonical, seen)


class TestDrivers(unittest.TestCase):
    def setUp(self):
        self.params = params_for()
        self.task = build_task(self.params, random.Random(8), seed=8)

    def test_template_driver_contains_formula_and_variables(self):
        text = TemplateDriver().phrase(self.task)
        self.assertIn(self.task["expression"], text)
        for name in self.task["var_order"]:
            self.assertIn(name, text)

    def test_factory_returns_template_by_default(self):
        self.assertIsInstance(make_driver("procedural"), TemplateDriver)

    def test_validate_rejects_distortions(self):
        driver = OpenAICompatDriver(base_url="http://127.0.0.1:1/v1", timeout=0.2)
        good = "Постройте таблицу истинности для F = " + self.task["expression"]
        self.assertTrue(driver.validate(self.task, good))
        self.assertFalse(driver.validate(self.task, "Постройте таблицу истинности."))
        self.assertFalse(driver.validate(self.task, good + " Ответ: 1"))
        self.assertFalse(driver.validate(self.task, "F = A ∧ B (переменные A, B, C)"))

    def test_phrase_falls_back_to_template_on_network_error(self):
        driver = OpenAICompatDriver(base_url="http://127.0.0.1:1/v1", timeout=0.2)
        text = driver.phrase(self.task)
        self.assertIn(self.task["expression"], text)


if __name__ == "__main__":
    unittest.main()
