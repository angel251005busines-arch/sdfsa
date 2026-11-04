"""Семантика: вычисление истинности, таблицы истинности, канонические подписи.

Здесь живут ДВА НЕЗАВИСИМЫХ вычислителя:

1. :func:`truth_rows` — рекурсивный интерпретатор по AST (наш код).
2. :func:`truth_rows_via_python` — трансляция AST в исходный код Python и его
   выполнение в песочнице. Код генерируется ТОЛЬКО из нашего AST (текст LLM в
   ``eval`` никогда не попадает), поэтому это безопасно и служит перекрёстной
   проверкой интерпретатора.

Расхождение этих двух движков — это баг ЯДРА, а не баг задания.
"""
from __future__ import annotations

import itertools
from typing import Dict, Iterator, List, Mapping, Sequence, Tuple

from .ast import Bin, Node, Not, Var, vars_in

Row = Tuple[Tuple[int, ...], int]  # (значения переменных в порядке var_order, значение F)


def check_vars(var_order: Sequence[str]) -> None:
    if len(set(var_order)) != len(var_order):
        raise ValueError(f"повторяющиеся переменные: {var_order!r}")
    for name in var_order:
        if not name.isidentifier():
            raise ValueError(f"недопустимое имя переменной: {name!r}")


def assignments(var_order: Sequence[str]) -> Iterator[Dict[str, bool]]:
    """Все наборы значений; первый элемент var_order — старший бит."""
    for bits in itertools.product((0, 1), repeat=len(var_order)):
        yield {name: bool(bit) for name, bit in zip(var_order, bits)}


# --------------------------------------------------------------------------- #
#  Движок 1: интерпретатор по AST
# --------------------------------------------------------------------------- #
def evaluate(node: Node, env: Mapping[str, bool]) -> bool:
    """Значение выражения на одном наборе значений."""
    if isinstance(node, Var):
        try:
            return bool(env[node.name])
        except KeyError:
            raise KeyError(f"переменная {node.name!r} отсутствует в наборе") from None
    if isinstance(node, Not):
        return not evaluate(node.arg, env)

    op = node.op
    if op == "AND":
        return evaluate(node.left, env) and evaluate(node.right, env)
    if op == "OR":
        return evaluate(node.left, env) or evaluate(node.right, env)
    if op == "XOR":
        return evaluate(node.left, env) != evaluate(node.right, env)
    if op == "IMPL":
        return (not evaluate(node.left, env)) or evaluate(node.right, env)
    if op == "EQV":
        return evaluate(node.left, env) == evaluate(node.right, env)
    raise ValueError(f"неизвестная операция: {op!r}")


def truth_rows(node: Node, var_order: Sequence[str]) -> List[Row]:
    """Полная таблица истинности в стандартном порядке наборов."""
    check_vars(var_order)
    rows: List[Row] = []
    for bits in itertools.product((0, 1), repeat=len(var_order)):
        env = {name: bool(bit) for name, bit in zip(var_order, bits)}
        rows.append((bits, int(evaluate(node, env))))
    return rows


# --------------------------------------------------------------------------- #
#  Движок 2: трансляция в Python-код (независимая реализация)
# --------------------------------------------------------------------------- #
_TO_PY: Dict[str, str] = {
    "AND": " and ",
    "OR": " or ",
    "XOR": " != ",
    "EQV": " == ",
}


def to_python_source(node: Node) -> str:
    """Перевести AST в выражение Python (только из нашего AST!)."""
    if isinstance(node, Var):
        return node.name
    if isinstance(node, Not):
        return f"(not {to_python_source(node.arg)})"
    if node.op == "IMPL":
        return f"((not {to_python_source(node.left)}) or {to_python_source(node.right)})"
    return f"({to_python_source(node.left)}{_TO_PY[node.op]}{to_python_source(node.right)})"


def truth_rows_via_python(node: Node, var_order: Sequence[str]) -> List[Row]:
    """Второй, независимый движок: генерирует Python-код и исполняет его в песочнице."""
    check_vars(var_order)
    code = compile(to_python_source(node), "<boolgen-expr>", "eval")
    sandbox = {"__builtins__": {}}  # никаких встроенных функций
    rows: List[Row] = []
    for bits in itertools.product((0, 1), repeat=len(var_order)):
        env = {name: bool(bit) for name, bit in zip(var_order, bits)}
        value = eval(code, sandbox, env)  # noqa: S307 - код построен из нашего AST
        rows.append((bits, int(bool(value))))
    return rows


# --------------------------------------------------------------------------- #
#  Производные характеристики
# --------------------------------------------------------------------------- #
def _rows_mask(rows: Sequence[Row]) -> int:
    result = 0
    for index, (_, value) in enumerate(rows):
        if value:
            result |= 1 << index
    return result


def mask(node: Node, var_order: Sequence[str]) -> int:
    """Битовая маска значений функции: бит i = значение на наборе с номером i."""
    return _rows_mask(truth_rows(node, var_order))


def minterms(node: Node, var_order: Sequence[str]) -> Tuple[int, ...]:
    """Номера наборов, на которых функция истинна."""
    return tuple(i for i, (_, value) in enumerate(truth_rows(node, var_order)) if value)


def count_ones(node: Node, var_order: Sequence[str]) -> int:
    return sum(value for _, value in truth_rows(node, var_order))


def is_tautology(node: Node, var_order: Sequence[str]) -> bool:
    return mask(node, var_order) == (1 << (1 << len(var_order))) - 1


def is_contradiction(node: Node, var_order: Sequence[str]) -> bool:
    return mask(node, var_order) == 0


def canonical_key(node: Node) -> Tuple[int, int]:
    """Каноническая подпись функции, не зависящая от имён и порядка переменных.

    Формулы, отличающиеся только именами переменных или перестановкой операндов,
    получают одинаковую подпись — это основа дедупликации пула заданий.
    """
    names = vars_in(node)
    return (len(names), mask(node, names))


def equivalent(a: Node, b: Node, var_order: Sequence[str]) -> bool:
    """Семантическая эквивалентность на общем наборе переменных."""
    return mask(a, var_order) == mask(b, var_order)


def depends_on(node: Node, var_order: Sequence[str]) -> Dict[str, bool]:
    """Для каждой переменной: влияет ли её изменение на результат хотя бы раз."""
    result = {name: False for name in var_order}
    for bits, _value in truth_rows(node, var_order):
        env = {name: bool(bit) for name, bit in zip(var_order, bits)}
        base = evaluate(node, env)
        for name in var_order:
            if result[name]:
                continue
            flipped = dict(env)
            flipped[name] = not env[name]
            if evaluate(node, flipped) != base:
                result[name] = True
        if all(result.values()):
            break
    return result


def redundant_vars(node: Node, var_order: Sequence[str]) -> List[str]:
    """Переменные, от которых функция фактически не зависит."""
    flags = depends_on(node, var_order)
    return [name for name in var_order if not flags[name]]


def column_values(node: Node, var_order: Sequence[str], name: str) -> Tuple[int, ...]:
    """Столбец значений переменной ``name`` в стандартном порядке наборов."""
    i = list(var_order).index(name)
    return tuple(bits[i] for bits, _ in truth_rows(node, var_order))

