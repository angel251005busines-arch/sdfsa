"""Объективная метрика сложности задания.

Ключевая мысль: «уровень сложности», который сообщила LLM, ничего не значит.
Сложность — это функция от структуры выражения, её можно пересчитать и проверить.
Поэтому в параметрах задаётся коридор, а верификатор проверяет попадание в него.
"""
from __future__ import annotations

from typing import Dict, Sequence

from .ast import Node, depth, node_count, ops_in
from .semantics import count_ones

# Веса подобраны так, чтобы коридоры были различимы на школьном материале
# (2–5 переменных, 5–15 узлов). Значения калиброваны на реальных примерах ЕГЭ.
W_VARIABLE = 0.75   # за каждую переменную сверх двух
W_NODE = 0.18       # за каждый узел AST
W_DEPTH = 0.22      # за уровень вложенности
W_IMPL_EQV = 0.45   # импликация/эквивалентность — традиционно «трудные» операции
W_XOR = 0.35        # XOR требует внимательности
W_BALANCE = 0.30    # «ровно половина единиц» легко угадать => добавляем вес

#: Базовые границы коридоров при n = 2 переменных. При большем числе
#: переменных границы сдвигаются на вклад переменных (см. :func:`corridor`),
#: иначе «easy» при n = 4 был бы недостижим в принципе.
BASE_EASY_MAX = 2.6
BASE_MEDIUM_MAX = 4.2
#: Сдвиг границ на каждую переменную сверх двух: чем больше переменных,
#: тем выше «минимально возможная» сложность задания.
SHIFT_PER_VARIABLE = 0.7


def corridor(difficulty: str, variables: int = 2):
    """Границы коридора ``(lo, hi)`` для заданного числа переменных."""
    shift = SHIFT_PER_VARIABLE * max(variables - 2, 0)
    easy_max = BASE_EASY_MAX + shift
    medium_max = BASE_MEDIUM_MAX + shift
    if difficulty == "easy":
        return (0.0, easy_max)
    if difficulty == "medium":
        return (easy_max, medium_max)
    if difficulty == "hard":
        return (medium_max, 1e9)
    if difficulty == "any":
        return (0.0, 1e9)
    raise ValueError(
        f"неизвестный уровень сложности {difficulty!r}; допустимо: easy/medium/hard/any"
    )


def in_corridor(score: float, difficulty: str, variables: int = 2) -> bool:
    lo, hi = corridor(difficulty, variables)
    return lo <= score < hi


def balance(node: Node, var_order: Sequence[str]) -> float:
    """0 — половина наборов истинна (легко угадать), 1 — крайние случаи."""
    total = 1 << len(var_order)
    share = count_ones(node, var_order) / total
    return round(abs(share - 0.5) * 2, 4)


def difficulty_score(node: Node, var_order: Sequence[str]) -> float:
    """Численная сложность выражения. Чем больше, тем труднее."""
    n = len(var_order)
    ops = ops_in(node)
    hard_ops = len(ops & {"IMPL", "EQV"})
    score = (
        W_VARIABLE * max(n - 2, 0)
        + W_NODE * node_count(node)
        + W_DEPTH * depth(node)
        + W_IMPL_EQV * hard_ops
        + (W_XOR if "XOR" in ops else 0.0)
        + W_BALANCE * balance(node, var_order)
    )
    return round(score, 2)


def metrics(node: Node, var_order: Sequence[str]) -> Dict[str, object]:
    """Полный набор метрик задания (сохраняется в пул и показывается в отчёте)."""
    ops = sorted(ops_in(node))
    return {
        "variables": list(var_order),
        "nodes": node_count(node),
        "depth": depth(node),
        "operations": ops,
        "ones": count_ones(node, var_order),
        "rows": 1 << len(var_order),
        "balance": balance(node, var_order),
        "difficulty_score": difficulty_score(node, var_order),
    }
