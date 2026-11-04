"""Тесты семантики: истинность, два движка, зависимости, канонизация."""
from __future__ import annotations

import random
import unittest

from boolgen.ast import to_text, vars_in
from boolgen.generator import random_expression
from boolgen.parser import parse
from boolgen.semantics import (
    canonical_key,
    count_ones,
    depends_on,
    equivalent,
    evaluate,
    is_contradiction,
    is_tautology,
    mask,
    minterms,
    redundant_vars,
    truth_rows,
    truth_rows_via_python,
)

ORDER = ["A", "B", "C"]


class TestTruthTables(unittest.TestCase):
    def test_known_table_for_implication(self):
        rows = truth_rows(parse("A → B"), ["A", "B"])
        self.assertEqual(rows, [((0, 0), 1), ((0, 1), 1), ((1, 0), 0), ((1, 1), 1)])

    def test_implication_false_only_for_true_to_false(self):
        self.assertEqual(minterms(parse("A → B"), ["A", "B"]), (0, 1, 3))

    def test_equivalence(self):
        self.assertEqual(minterms(parse("A ≡ B"), ["A", "B"]), (0, 3))

    def test_xor(self):
        self.assertEqual(minterms(parse("A ⊕ B"), ["A", "B"]), (1, 2))

    def test_de_morgan(self):
        self.assertTrue(equivalent(parse("¬(A ∧ B)"), parse("¬A ∨ ¬B"), ["A", "B"]))
        self.assertTrue(equivalent(parse("¬(A ∨ B)"), parse("¬A ∧ ¬B"), ["A", "B"]))

    def test_contraposition(self):
        self.assertTrue(equivalent(parse("A → B"), parse("¬B → ¬A"), ["A", "B"]))

    def test_converse_is_not_equivalent(self):
        self.assertFalse(equivalent(parse("A → B"), parse("B → A"), ["A", "B"]))

    def test_row_order_uses_first_variable_as_msb(self):
        rows = truth_rows(parse("A"), ["A", "B"])
        self.assertEqual([(bits, value) for bits, value in rows],
                         [((0, 0), 0), ((0, 1), 0), ((1, 0), 1), ((1, 1), 1)])

    def test_evaluate_requires_all_variables(self):
        with self.assertRaises(KeyError):
            evaluate(parse("A ∧ B"), {"A": True})


class TestTwoEngines(unittest.TestCase):
    def test_engines_agree_on_random_expressions(self):
        rng = random.Random(2024)
        for _ in range(120):
            node = random_expression(rng, ORDER, depth=3)
            order = vars_in(node)
            with self.subTest(expr=to_text(node)):
                self.assertEqual(
                    truth_rows(node, order), truth_rows_via_python(node, order)
                )

    def test_python_source_matches_semantics(self):
        from boolgen.semantics import to_python_source

        self.assertEqual(to_python_source(parse("A → B")), "((not A) or B)")
        self.assertEqual(to_python_source(parse("A ⊕ B")), "(A != B)")


class TestProperties(unittest.TestCase):
    def test_dependency_detection(self):
        flags = depends_on(parse("A ∧ B"), ["A", "B", "C"])
        self.assertEqual(flags, {"A": True, "B": True, "C": False})
        self.assertEqual(redundant_vars(parse("A ∨ ¬A"), ["A", "B"]), ["A", "B"])

    def test_tautology_and_contradiction(self):
        self.assertTrue(is_tautology(parse("A ∨ ¬A"), ["A"]))
        self.assertTrue(is_contradiction(parse("A ∧ ¬A"), ["A"]))

    def test_count_ones(self):
        self.assertEqual(count_ones(parse("A ⊕ B"), ["A", "B"]), 2)
        self.assertEqual(count_ones(parse("A ∨ ¬A"), ["A"]), 2)
        self.assertEqual(count_ones(parse("A ∧ ¬A"), ["A"]), 0)

    def test_canonical_key_ignores_names_and_order(self):
        self.assertEqual(canonical_key(parse("A ∧ B")), canonical_key(parse("B ∧ A")))
        self.assertEqual(canonical_key(parse("A ∧ B")), canonical_key(parse("X ∧ Y")))
        self.assertNotEqual(canonical_key(parse("A ∧ B")), canonical_key(parse("A ∨ B")))

    def test_mask_matches_minterms(self):
        node = parse("(A ∨ ¬B) ∧ C")
        expected = 0
        for index in minterms(node, ORDER):
            expected |= 1 << index
        self.assertEqual(mask(node, ORDER), expected)


if __name__ == "__main__":
    unittest.main()
