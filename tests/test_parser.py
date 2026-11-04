"""Тесты: разбор нотаций, приоритеты, обратимость, ошибки."""
from __future__ import annotations

import unittest

from boolgen.ast import Bin, Not, Var, depth, is_dnf, node_count, ops_in, to_text, vars_in
from boolgen.parser import ParseError, parse, try_parse


class TestNotations(unittest.TestCase):
    def test_equivalent_spellings(self):
        expected = parse("¬A ∧ (B ∨ C)")
        for text in (
            "¬A ∧ (B ∨ C)",
            "!A & (B | C)",
            "not A and (B or C)",
            "НЕ A И (B ИЛИ C)",
            "~A * (B + C)",
            "¬A∧(B∨C)",
        ):
            with self.subTest(text=text):
                self.assertEqual(parse(text), expected)

    def test_all_operators(self):
        cases = {
            "A → B": "IMPL",
            "A -> B": "IMPL",
            "A ⇒ B": "IMPL",
            "A ≡ B": "EQV",
            "A ↔ B": "EQV",
            "A == B": "EQV",
            "A ⊕ B": "XOR",
            "A xor B": "XOR",
            "A ^ B": "XOR",
            "A ∧ B": "AND",
            "A ∨ B": "OR",
        }
        for text, op in cases.items():
            with self.subTest(text=text):
                self.assertIn(op, ops_in(parse(text)))

    def test_comments_and_spaces(self):
        node = parse("A ∧ B  # комментарий\n ∨ C")
        self.assertEqual(vars_in(node), ("A", "B", "C"))


class TestPrecedence(unittest.TestCase):
    def test_not_binds_tighter_than_and(self):
        self.assertEqual(parse("¬A ∧ B"), Bin("AND", Not(Var("A")), Var("B")))

    def test_and_binds_tighter_than_or(self):
        self.assertEqual(parse("A ∨ B ∧ C"), Bin("OR", Var("A"), Bin("AND", Var("B"), Var("C"))))

    def test_xor_between_and_and_or(self):
        self.assertEqual(
            parse("A ∨ B ⊕ C ∧ D"),
            Bin("OR", Var("A"), Bin("XOR", Var("B"), Bin("AND", Var("C"), Var("D")))),
        )

    def test_implication_is_right_associative(self):
        self.assertEqual(
            parse("A → B → C"),
            Bin("IMPL", Var("A"), Bin("IMPL", Var("B"), Var("C"))),
        )

    def test_implication_binds_tighter_than_equivalence(self):
        self.assertEqual(
            parse("A → B ≡ C"),
            Bin("EQV", Bin("IMPL", Var("A"), Var("B")), Var("C")),
        )

    def test_not_is_right_associative(self):
        self.assertEqual(parse("¬¬A"), Not(Not(Var("A"))))


class TestRoundTrip(unittest.TestCase):
    def test_to_text_reparses_to_same_tree(self):
        samples = [
            "¬A ∧ (B ∨ C)",
            "(A → B) → C",
            "A → (B → C)",
            "A ∧ (B ∧ C)",
            "(A ∧ B) ∧ C",
            "A ⊕ B ⊕ C",
            "A ≡ B ≡ C",
            "(A ∨ ¬B) → (C ≡ ¬A)",
            "¬(A ∧ B) ∨ ¬(C → A)",
        ]
        for text in samples:
            with self.subTest(text=text):
                node = parse(text)
                self.assertEqual(parse(to_text(node)), node)

    def test_minimal_parentheses(self):
        self.assertEqual(to_text(parse("(A ∧ B) ∧ C")), "A ∧ B ∧ C")
        self.assertEqual(to_text(parse("A ∧ (B ∧ C)")), "A ∧ (B ∧ C)")
        self.assertEqual(to_text(parse("(A → B) → C")), "(A → B) → C")

    def test_xor_is_parenthesized_when_mixed(self):
        """В школе приоритет ⊕ не определён — печатаем со скобками."""
        self.assertEqual(to_text(parse("A ∨ B ⊕ C")), "A ∨ (B ⊕ C)")
        self.assertEqual(to_text(parse("A ⊕ B ∧ C")), "A ⊕ (B ∧ C)")
        self.assertEqual(to_text(parse("A ⊕ B ⊕ C")), "A ⊕ B ⊕ C")
        self.assertEqual(parse(to_text(parse("A ≡ B ⊕ C"))), parse("A ≡ B ⊕ C"))


class TestMetadata(unittest.TestCase):
    def test_structure_metrics(self):
        node = parse("¬A ∧ (B → C)")
        self.assertEqual(vars_in(node), ("A", "B", "C"))
        self.assertEqual(node_count(node), 6)
        self.assertEqual(depth(node), 2)
        self.assertEqual(ops_in(node), frozenset({"NOT", "AND", "IMPL"}))

    def test_is_dnf(self):
        for text in ("A ∧ ¬B ∨ C", "A", "A ∧ B ∧ C", "A ∨ B"):
            with self.subTest(text=text):
                self.assertTrue(is_dnf(parse(text)))
        for text in ("(A ∨ B) ∧ C", "A → B", "¬(A ∧ B)", "A ≡ B"):
            with self.subTest(text=text):
                self.assertFalse(is_dnf(parse(text)))


class TestErrors(unittest.TestCase):
    def test_parse_errors_are_reported_with_position(self):
        for bad in ("", "A ∧", "(A ∨ B", "A ) B", "A & & B", "A ⊕⊕ B"):
            with self.subTest(bad=bad):
                with self.assertRaises(ParseError):
                    parse(bad)

    def test_try_parse_returns_message(self):
        node, error = try_parse("A ∧")
        self.assertIsNone(node)
        self.assertIn("позиция", error)

    def test_no_code_execution(self):
        for attack in ('__import__("os").system("echo pwned")', "A.__class__", "eval('1+1')"):
            with self.subTest(attack=attack):
                node, error = try_parse(attack)
                self.assertIsNone(node)
                self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
