"""Тесты процедурного генератора: детерминизм и соблюдение параметров."""
from __future__ import annotations

import random
import unittest

from boolgen.ast import depth, node_count, ops_in, to_text, vars_in
from boolgen.generator import (
    GenerationError,
    check_candidate,
    generate_expression,
    has_absorption,
    is_structurally_trivial,
    random_expression,
)
from boolgen.params import Params
from boolgen.parser import parse
from boolgen.semantics import depends_on, is_contradiction, is_tautology


def make_params(**overrides) -> Params:
    base = dict(
        task_type="truth_table",
        operations=("NOT", "AND", "OR", "IMPL", "XOR", "EQV"),
        variables=3,
        depth=3,
        nodes_max=17,
        difficulty="medium",
    )
    base.update(overrides)
    return Params(**base).validate()


class TestDeterminism(unittest.TestCase):
    def test_same_seed_gives_same_expression(self):
        params = make_params()
        first = generate_expression(params, random.Random(123))
        second = generate_expression(params, random.Random(123))
        self.assertEqual(first, second)

    def test_different_seeds_give_different_expressions(self):
        params = make_params()
        expressions = {
            to_text(generate_expression(params, random.Random(seed)))
            for seed in range(12)
        }
        self.assertGreater(len(expressions), 1)


class TestParamsConformance(unittest.TestCase):
    def test_generated_expressions_respect_params(self):
        rng = random.Random(99)
        for variables in (2, 3, 4):
            # Без NOT при двух переменных почти любое выражение с повторением
            # переменной вырождается (поглощение), поэтому наборы операций
            # подобраны так, чтобы параметры были совместны.
            for ops in (
                ("NOT", "AND", "OR"),
                ("NOT", "IMPL"),
                ("NOT", "AND", "OR", "XOR"),
            ):
                params = make_params(variables=variables, operations=ops, difficulty="any")
                for _ in range(5):
                    node = generate_expression(params, rng)
                    with self.subTest(vars=variables, ops=ops, expr=to_text(node)):
                        self.assertLessEqual(node_count(node), params.nodes_max)
                        self.assertEqual(depth(node), params.depth)
                        self.assertLessEqual(ops_in(node), set(ops))
                        self.assertEqual(set(vars_in(node)), set(params.names()))
                        self.assertIsNone(check_candidate(node, params, params.names()))

    def test_forbidden_operations_are_not_used(self):
        # Контракт Params: запрет не пересекается с разрешёнными операциями.
        params = make_params(
            operations=("NOT", "AND", "OR", "XOR"),
            forbidden_operations=("IMPL", "EQV"),
        )
        rng = random.Random(5)
        for _ in range(10):
            node = generate_expression(params, rng)
            self.assertFalse(ops_in(node) & {"IMPL", "EQV"})

    def test_forbidden_overlaps_allowed_is_rejected(self):
        from boolgen.params import ParamsError

        with self.assertRaises(ParamsError):
            make_params(forbidden_operations=("IMPL",))

    def test_no_trivial_or_absorbing_expressions(self):
        params = make_params()
        rng = random.Random(31)
        for _ in range(20):
            node = generate_expression(params, rng)
            with self.subTest(expr=to_text(node)):
                self.assertFalse(is_structurally_trivial(node))
                self.assertFalse(has_absorption(node))
                self.assertFalse(is_tautology(node, params.names()))
                self.assertFalse(is_contradiction(node, params.names()))
                self.assertTrue(all(depends_on(node, params.names()).values()))


class TestDifficulties(unittest.TestCase):
    def test_all_levels_reachable_at_depth_four(self):
        rng = random.Random(77)
        for difficulty in ("easy", "medium", "hard"):
            params = make_params(difficulty=difficulty, depth=4, nodes_max=19)
            with self.subTest(difficulty=difficulty):
                node = generate_expression(params, rng)
                self.assertIsNone(check_candidate(node, params, params.names()))

    def test_impossible_params_raise_clear_error(self):
        params = make_params(difficulty="hard", depth=2, nodes_max=8)
        with self.assertRaises(GenerationError) as ctx:
            generate_expression(params, random.Random(1))
        self.assertIn("не удалось построить", str(ctx.exception))


class TestTrivialityDetectors(unittest.TestCase):
    def test_structural_triviality(self):
        for text in ("¬¬A", "A ∧ A", "A → A", "A ⊕ A", "B ∧ C ∧ C", "A ∨ ¬A"):
            with self.subTest(text=text):
                self.assertTrue(is_structurally_trivial(parse(text)))

    def test_absorption(self):
        for text in ("A ∨ A ∧ B", "A ∧ (A ∨ B)", "(A ∨ B ∧ A) ∧ C", "X ∨ Y ∧ X"):
            with self.subTest(text=text):
                self.assertTrue(has_absorption(parse(text)))

    def test_non_trivial_expressions_pass(self):
        for text in ("¬A ∧ (B ∨ C)", "A → (B ≡ C)", "(A ∨ B) ∧ ¬C"):
            with self.subTest(text=text):
                node = parse(text)
                self.assertFalse(is_structurally_trivial(node))
                self.assertFalse(has_absorption(node))

    def test_random_expression_has_no_params(self):
        rng = random.Random(3)
        node = random_expression(rng, ["A", "B"], depth=2)
        self.assertLessEqual(depth(node), 2)


if __name__ == "__main__":
    unittest.main()
