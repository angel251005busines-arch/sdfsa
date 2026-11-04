"""Процедурный генератор логических выражений по параметрам.

Генератор детерминирован относительно ``rng``: один и тот же seed даёт одно и
то же выражение. Это нужно для воспроизводимости баг-репортов.

Строим случайное дерево точно заданной глубины, затем:
* «починяем» выражение, добавляя пропущенные переменные (замена листа),
* проверяем ограничения: операции, размер, тривиальность, зависимость от всех
  переменных, коридор сложности.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import List, Optional, Sequence, Tuple

from .ast import BINARY_OPS, Bin, Node, Not, Var, depth, node_count, ops_in, vars_in, walk
from .metrics import difficulty_score, in_corridor
from .params import Params
from .semantics import depends_on, is_contradiction, is_tautology

MAX_ATTEMPTS = 600


class GenerationError(RuntimeError):
    """Не удалось построить выражение, удовлетворяющее параметрам."""


# --------------------------------------------------------------------------- #
#  Вспомогательные операции над деревом
# --------------------------------------------------------------------------- #
def _leaf_paths(node: Node, path: Tuple[int, ...] = ()) -> List[Tuple[int, ...]]:
    if isinstance(node, Var):
        return [path]
    out: List[Tuple[int, ...]] = []
    for i, child in enumerate(node.children()):
        out.extend(_leaf_paths(child, path + (i,)))
    return out


def _replace_at(node: Node, path: Tuple[int, ...], new: Node) -> Node:
    if not path:
        return new
    head, rest = path[0], path[1:]
    if isinstance(node, Not):
        return Not(_replace_at(node.arg, rest, new))
    kids = [node.left, node.right]
    kids[head] = _replace_at(kids[head], rest, new)
    return Bin(node.op, kids[0], kids[1])


def _conjuncts(node: Node) -> List[Node]:
    if isinstance(node, Bin) and node.op == "AND":
        return _conjuncts(node.left) + _conjuncts(node.right)
    return [node]


def _disjuncts(node: Node) -> List[Node]:
    if isinstance(node, Bin) and node.op == "OR":
        return _disjuncts(node.left) + _disjuncts(node.right)
    return [node]


def _literal_set(parts: Sequence[Node]) -> set:
    return set(parts)


def has_absorption(node: Node) -> bool:
    """Есть ли в выражении закон поглощения: ``X ∨ X∧Y`` или ``X ∧ (X ∨ Y)``.

    Проверка на уровне множеств литералов, поэтому ловит и вложенные случаи
    (``C ∨ A ∨ A∧C``, ``(A∨B) ∧ (A∨B∨C)``). Такие места не делают задание
    неверным, но делают его «грязным»: часть выражения заведомо избыточна
    и подсказывает ответ.
    """

    def groups_or(or_node: Node):
        out = []
        for item in _disjuncts(or_node):
            if isinstance(item, Bin) and item.op == "AND":
                out.append(_literal_set(_conjuncts(item)))
            else:
                out.append({item})
        return out

    def groups_and(and_node: Node):
        out = []
        for item in _conjuncts(and_node):
            if isinstance(item, Bin) and item.op == "OR":
                out.append(_literal_set(_disjuncts(item)))
            else:
                out.append({item})
        return out

    for sub in walk(node):
        if isinstance(sub, Bin) and sub.op in ("OR", "AND"):
            groups = groups_or(sub) if sub.op == "OR" else groups_and(sub)
            for i, first in enumerate(groups):
                for j, second in enumerate(groups):
                    if i != j and first and first <= second:
                        return True
    return False


def is_structurally_trivial(node: Node) -> bool:
    """Проверка «синтаксической» тривиальности.

    Ловит: ``¬¬A``, ``A ∧ A``, ``A → A``, а также повторы переменных внутри
    одной цепочки ``∧``/``∨`` (``B ∧ C ∧ C``).
    """
    if isinstance(node, Not):
        if isinstance(node.arg, Not):
            return True
        return is_structurally_trivial(node.arg)
    if isinstance(node, Bin):
        if node.left == node.right:  # A ∨ A, A → A, A ⊕ A ...
            return True
        if node.op in ("AND", "OR") and _has_repeated_var_in_chain(node):
            return True
        return is_structurally_trivial(node.left) or is_structurally_trivial(node.right)
    return False


def _chain_vars(node: Node, op: str) -> List[str]:
    """Переменные, входящие в цепочку операций ``op`` (без учёта отрицаний)."""
    found: List[str] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, Var):
            found.append(current.name)
        elif isinstance(current, Not) and isinstance(current.arg, Var):
            found.append(current.arg.name)
        elif isinstance(current, Bin) and current.op == op:
            stack.extend([current.left, current.right])
    return found


def _has_repeated_var_in_chain(node: Node) -> bool:
    names = _chain_vars(node, node.op)  # type: ignore[union-attr]
    return len(names) != len(set(names))


# --------------------------------------------------------------------------- #
#  Построение дерева
# --------------------------------------------------------------------------- #
def _build(
    rng: random.Random,
    level: int,
    bin_ops: Sequence[str],
    use_not: bool,
    names: Sequence[str],
) -> Node:
    """Дерево, глубина которого ровно ``level``."""
    if level <= 0:
        return Var(rng.choice(names))

    kinds = []
    if use_not:
        kinds.append("unary")
    if bin_ops:
        kinds.append("binary")
    if not kinds:  # остались только переменные
        return Var(rng.choice(names))

    if rng.random() < 0.28 and "unary" in kinds:
        return Not(_build(rng, level - 1, bin_ops, use_not, names))

    if not bin_ops:
        return Not(_build(rng, level - 1, bin_ops, use_not, names))

    op = rng.choice(bin_ops)
    if level == 1:
        return Bin(op, Var(rng.choice(names)), Var(rng.choice(names)))

    # Один из потомков обязан иметь глубину level-1, чтобы выдержать точную глубину.
    if rng.random() < 0.5:
        left = _build(rng, level - 1, bin_ops, use_not, names)
        right = _build(rng, rng.randint(0, level - 1), bin_ops, use_not, names)
    else:
        left = _build(rng, rng.randint(0, level - 1), bin_ops, use_not, names)
        right = _build(rng, level - 1, bin_ops, use_not, names)
    return Bin(op, left, right)


def _repair_vars(node: Node, rng: random.Random, names: Sequence[str],
                 require_all: bool) -> Node:
    """Добавить отсутствующие переменные, заменяя случайные листья."""
    if not require_all:
        return node
    for name in names:
        if name in set(vars_in(node)):
            continue
        paths = _leaf_paths(node)
        if not paths:
            return node
        node = _replace_at(node, rng.choice(paths), Var(name))
    return node


# --------------------------------------------------------------------------- #
#  Приёмка
# --------------------------------------------------------------------------- #
def check_candidate(node: Node, params: Params, var_order: Sequence[str]) -> Optional[str]:
    """Проверка выражения против параметров.

    Возвращает ``None``, если выражение годится, иначе — причину отказа.
    Это ровно та логика, которую верификатор применяет и к выхлопу LLM.
    """
    allowed = set(params.ops())
    if not ops_in(node) <= allowed:
        extra = sorted(ops_in(node) - allowed)
        return f"использованы запрещённые операции: {extra}"
    if node_count(node) > params.nodes_max:
        return f"слишком много узлов: {node_count(node)} > {params.nodes_max}"
    if depth(node) != params.depth:
        return f"глубина {depth(node)} вместо требуемой {params.depth}"
    if params.avoid_trivial and is_structurally_trivial(node):
        return "структурно тривиальное выражение"
    if params.avoid_trivial and has_absorption(node):
        return "поглощение в выражении"
    if params.require_all_vars:
        flags = depends_on(node, var_order)
        unused = [name for name, used in flags.items() if not used]
        if unused:
            return f"функция не зависит от переменных {unused}"
    if is_tautology(node, var_order):
        return "тавтология"
    if is_contradiction(node, var_order):
        return "противоречие"
    score = difficulty_score(node, var_order)
    if not in_corridor(score, params.difficulty, len(var_order)):
        return f"сложность {score} вне коридора {params.difficulty}"
    return None


def random_expression(
    rng: random.Random,
    names: Sequence[str],
    depth: int = 3,
    ops: Sequence[str] = ("NOT", "AND", "OR", "IMPL", "XOR", "EQV"),
) -> Node:
    """Случайное выражение без привязки к параметрам задания.

    Используется в самопроверке ядра и в property-тестах.
    """
    bin_ops = tuple(op for op in ops if op in BINARY_OPS)
    use_not = "NOT" in ops
    return _build(rng, depth, bin_ops, use_not, names)


def generate_expression(params: Params, rng: random.Random) -> Node:
    """Сгенерировать выражение, удовлетворяющее всем параметрам."""
    names = params.names()
    bin_ops = params.ops_binary()
    use_not = "NOT" in params.ops_unary()
    reasons: Counter = Counter()

    for _ in range(MAX_ATTEMPTS):
        node = _build(rng, params.depth, bin_ops, use_not, names)
        node = _repair_vars(node, rng, names, params.require_all_vars)
        reason = check_candidate(node, params, names)
        if reason is None:
            return node
        reasons[reason.split(":")[0]] += 1

    detail = ", ".join(f"{k} — {v}" for k, v in reasons.most_common(4))
    raise GenerationError(
        f"не удалось построить выражение за {MAX_ATTEMPTS} попыток "
        f"({params.to_dict()}); частые причины: {detail}"
    )

