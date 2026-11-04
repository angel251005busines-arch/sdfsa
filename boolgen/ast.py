"""AST логических выражений — единственное представление, с которым работает ядро.

Все проверки (семантика, соответствие параметрам, сложность) выполняются над AST,
а НЕ над текстом. Текст LLM/пользователя сначала парсится в AST, и только потом
считается доверенным результатом верификатора.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterator, Tuple

#: Бинарные операции. Порядок важен для стабильных сообщений об ошибках.
BINARY_OPS: Tuple[str, ...] = ("AND", "OR", "XOR", "IMPL", "EQV")
#: Унарные операции.
UNARY_OPS: Tuple[str, ...] = ("NOT",)
ALL_OPS: Tuple[str, ...] = UNARY_OPS + BINARY_OPS

#: Символы для вывода (школьная нотация).
SYMBOL = {
    "NOT": "¬",
    "AND": "∧",
    "OR": "∨",
    "XOR": "⊕",
    "IMPL": "→",
    "EQV": "≡",
}

#: Приоритеты операций (как в школьном курсе информатики):
#: ¬ > ∧ > ⊕ > ∨ > → > ≡
PRECEDENCE = {"NOT": 6, "AND": 5, "XOR": 4, "OR": 3, "IMPL": 2, "EQV": 1}

#: Правоассоциативные операции: A→B→C читается как A→(B→C).
RIGHT_ASSOC = frozenset({"IMPL", "EQV"})


class Node:
    """Базовый класс узла AST."""

    __slots__ = ()

    def children(self) -> Tuple["Node", ...]:
        return ()

    def __repr__(self) -> str:  # отладочное представление = школьная запись
        return to_text(self)


@dataclass(frozen=True, repr=False)
class Var(Node):
    """Переменная, например ``A``."""

    name: str


@dataclass(frozen=True, repr=False)
class Not(Node):
    """Отрицание ``¬arg``."""

    arg: Node

    def children(self) -> Tuple[Node, ...]:
        return (self.arg,)


@dataclass(frozen=True, repr=False)
class Bin(Node):
    """Бинарная операция ``left op right``."""

    op: str
    left: Node
    right: Node

    def __post_init__(self) -> None:
        if self.op not in BINARY_OPS:
            raise ValueError(f"неизвестная бинарная операция: {self.op!r}")

    def children(self) -> Tuple[Node, ...]:
        return (self.left, self.right)


NodeT = Node


# --------------------------------------------------------------------------- #
#  Обход дерева
# --------------------------------------------------------------------------- #
def walk(node: Node) -> Iterator[Node]:
    """Обход в глубину (pre-order)."""
    yield node
    for child in node.children():
        yield from walk(child)


def vars_in(node: Node) -> Tuple[str, ...]:
    """Отсортированный кортеж имён переменных, встречающихся в выражении."""
    return tuple(sorted({n.name for n in walk(node) if isinstance(n, Var)}))


def ops_in(node: Node) -> FrozenSet[str]:
    """Множество использованных операций."""
    out = set()
    for n in walk(node):
        if isinstance(n, Not):
            out.add("NOT")
        elif isinstance(n, Bin):
            out.add(n.op)
    return frozenset(out)


def node_count(node: Node) -> int:
    """Полное число узлов дерева (переменные, отрицания и операции считаются)."""
    return 1 + sum(node_count(c) for c in node.children())


def depth(node: Node) -> int:
    """Глубина дерева: переменная = 0, каждое отрицание/операция = +1."""
    if not node.children():
        return 0
    return 1 + max(depth(c) for c in node.children())


# --------------------------------------------------------------------------- #
#  Печать в школьной нотации
# --------------------------------------------------------------------------- #
def to_text(node: Node) -> str:
    """Записать выражение в школьной нотации с минимальным числом скобок.

    Гарантируется обратный разбор: ``parse(to_text(n)) == n``.

    Приоритет ``⊕`` в школе не определён, поэтому XOR-подвыражение при
    смешении с другими операциями всегда печатается в скобках
    (``A ∨ (B ⊕ C)``, а не ``A ∨ B ⊕ C``).
    """
    return _fmt(node, 1, None)


def _fmt(node: Node, min_prec: int, parent_op: "str | None") -> str:
    if isinstance(node, Var):
        return node.name

    if isinstance(node, Not):
        inner = _fmt(node.arg, PRECEDENCE["NOT"], "NOT")
        text = SYMBOL["NOT"] + inner
        own = PRECEDENCE["NOT"]
    else:  # Bin
        p = PRECEDENCE[node.op]
        # левый ребёнок неассоциативной справа операции требует скобок при равном приоритете
        left_prec = p + 1 if node.op in RIGHT_ASSOC else p
        right_prec = p if node.op in RIGHT_ASSOC else p + 1
        text = (
            f"{_fmt(node.left, left_prec, node.op)} {SYMBOL[node.op]} "
            f"{_fmt(node.right, right_prec, node.op)}"
        )
        own = p

    needs_parens = own < min_prec
    if (
        not needs_parens
        and isinstance(node, Bin)
        and parent_op is not None
        and parent_op != node.op
        and "XOR" in (node.op, parent_op)
    ):
        needs_parens = True
    return f"({text})" if needs_parens else text


def is_dnf(node: Node) -> bool:
    """Является ли выражение ДНФ (дизъюнкция конъюнкций литералов).

    Литерал — переменная или её отрицание. Одиночный литерал/конъюнкция тоже ДНФ.
    """
    if isinstance(node, Bin) and node.op == "OR":
        return _is_dnf_sum(node)
    return _is_dnf_term(node)


def _is_literal(node: Node) -> bool:
    if isinstance(node, Var):
        return True
    return isinstance(node, Not) and isinstance(node.arg, Var)


def _is_dnf_term(node: Node) -> bool:
    """Конъюнкция литералов (или один литерал)."""
    if _is_literal(node):
        return True
    if isinstance(node, Bin) and node.op == "AND":
        return _is_dnf_term(node.left) and _is_dnf_term(node.right)
    return False


def _is_dnf_sum(node: Node) -> bool:
    """OR-дерево, листья которого — конъюнкции литералов."""
    if isinstance(node, Bin) and node.op == "OR":
        return _is_dnf_sum(node.left) and _is_dnf_sum(node.right)
    return _is_dnf_term(node)
