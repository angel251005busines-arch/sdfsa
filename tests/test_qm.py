"""Тесты минимизации ДНФ (Quine–McCluskey)."""
from __future__ import annotations

import unittest

from boolgen import qm
from boolgen.parser import parse
from boolgen.semantics import mask


def cover_mask(terms, n):
    result = 0
    for m in range(1 << n):
        if any(qm.covers(term, m) for term in terms):
            result |= 1 << m
    return result


class TestQuineMcCluskey(unittest.TestCase):
    def test_exhaustive_coverage_3_variables(self):
        """Все 256 функций от 3 переменных покрываются ровно своими наборами."""
        for function_mask in range(1 << (1 << 3)):
            ones = {i for i in range(8) if function_mask >> i & 1}
            terms = qm.minimal_dnf_for_minterms(ones, 3)
            with self.subTest(function_mask=function_mask):
                self.assertEqual(cover_mask(terms, 3), function_mask)

    def test_random_coverage_4_variables(self):
        import random

        rng = random.Random(7)
        for _ in range(120):
            function_mask = rng.randrange(1 << 16)
            ones = {i for i in range(16) if function_mask >> i & 1}
            terms = qm.minimal_dnf_for_minterms(ones, 4)
            self.assertEqual(cover_mask(terms, 4), function_mask)

    def test_minimality_examples(self):
        cases = {
            "A ∧ B ∨ A ∧ ¬B": ("A", 1),
            "¬A ∧ ¬B ∨ ¬A ∧ B ∨ A ∧ B": ("¬A∨B", 2),
            "A → B": ("¬A∨B", 2),
            "A ⊕ B": ("¬B∧A∨¬A∧B", 4),
            "A ∧ B ∧ C ∨ A ∧ B ∧ ¬C": ("A∧B", 2),
        }
        for text, (expected_text, expected_literals) in cases.items():
            node = parse(text)
            names = ["A", "B", "C"]
            terms = qm.minimal_dnf(node, names)
            with self.subTest(text=text):
                self.assertEqual(qm.literal_count(terms), expected_literals)
                # порядок термов и литералов не важен — сравниваем как множества
                self.assertEqual(
                    sorted("".join(sorted(t.split("∧"))) for t in
                           qm.dnf_to_text(terms, names).split("∨")),
                    sorted("".join(sorted(t.split("∧"))) for t in expected_text.split("∨")),
                )
                self.assertEqual(cover_mask(terms, 3), mask(node, names))

    def test_minimal_dnf_is_equivalent(self):
        for text in ("(A ∨ B) ∧ ¬C", "A → (B ≡ C)", "¬(A ∧ B) ∨ C ∧ ¬A"):
            node = parse(text)
            names = ["A", "B", "C"]
            terms = qm.minimal_dnf(node, names)
            with self.subTest(text=text):
                self.assertEqual(cover_mask(terms, 3), mask(node, names))

    def test_terms_to_ast_roundtrip(self):
        names = ["A", "B", "C"]
        for function_mask in range(0, 256, 11):
            ones = {i for i in range(8) if function_mask >> i & 1}
            if not ones or len(ones) == 8:
                continue
            terms = qm.minimal_dnf_for_minterms(ones, 3)
            node = qm.terms_to_ast(terms, names)
            with self.subTest(function_mask=function_mask):
                self.assertEqual(mask(node, names), function_mask)

    def test_tautology_and_contradiction(self):
        self.assertEqual(qm.minimal_dnf_for_minterms(set(), 3), [])
        self.assertEqual(qm.minimal_dnf_for_minterms(set(range(8)), 3), [(0, 0)])
        self.assertEqual(qm.dnf_to_text([(0, 0)], ["A", "B", "C"]), "1")


if __name__ == "__main__":
    unittest.main()
