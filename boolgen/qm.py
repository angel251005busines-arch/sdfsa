"""Минимизация булевых функций: Quine–McCluskey (МДНФ).

Реализация нужна для:
* заданий «привести к минимальной ДНФ» (эталонный ответ);
* метрики сложности (число литералов в МДНФ);
* проверки ответа ученика: сравниваем не строки, а семантику + длину МДНФ.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Set, Tuple

from .ast import Bin, Node, Not, Var, vars_in
from .semantics import minterms

# Импликанта: (значение, маска значимых битов). Бит 1 в маске = переменная входит в терм.
Term = Tuple[int, int]


def _popcount(x: int) -> int:
    return bin(x).count("1")


def literal_count(terms: Iterable[Term]) -> int:
    """Суммарное число литералов в ДНФ."""
    return sum(_popcount(care) for _, care in terms)


def prime_implicants(ones: Set[int], n: int) -> List[Term]:
    """Все простые импликанты для множества наборов ``ones``."""
    full_mask = (1 << n) - 1
    current: Set[Term] = {(m, full_mask) for m in ones}
    primes: Set[Term] = set()

    while current:
        used: Set[Term] = set()
        next_level: Set[Term] = set()
        by_care: Dict[int, List[Term]] = {}
        for term in current:
            by_care.setdefault(term[1], []).append(term)

        for care, group in by_care.items():
            for i, (value_a, _) in enumerate(group):
                for value_b, _ in group[i + 1:]:
                    diff = value_a ^ value_b
                    if _popcount(diff) != 1:
                        continue
                    if not (care & diff):
                        continue
                    next_level.add((value_a & ~diff, care & ~diff))
                    used.add((value_a, care))
                    used.add((value_b, care))
        primes |= current - used
        current = next_level

    return sorted(primes)


def covers(term: Term, minterm: int) -> bool:
    value, care = term
    return (minterm & care) == value


def _cost(terms: Sequence[Term]) -> Tuple[int, int]:
    """Критерий качества: сначала число литералов, затем число термов."""
    return (literal_count(terms), len(terms))


def minimal_cover(ones: Set[int], primes: Sequence[Term]) -> List[Term]:
    """Точное покрытие наборов простыми импликантами минимальной стоимости."""
    if not ones:
        return []

    coverage: Dict[Term, Set[int]] = {t: {m for m in ones if covers(t, m)} for t in primes}
    coverage = {t: cov for t, cov in coverage.items() if cov}
    if not coverage:
        raise ValueError("не удалось покрыть наборы простыми импликантами")

    chosen: List[Term] = []
    uncovered: Set[int] = set(ones)

    # Шаг 1: существенные импликанты (набор покрыт единственным термом).
    while True:
        essential: Set[Term] = set()
        for m in uncovered:
            holders = [t for t, cov in coverage.items() if m in cov]
            if len(holders) == 1:
                essential.add(holders[0])
        if not essential:
            break
        for t in essential:
            chosen.append(t)
            uncovered -= coverage[t]

    if not uncovered:
        return chosen

    # Шаг 2: точный перебор с отсечением (n <= 5, простых импликант немного).
    best: List[Term] = []
    best_cost: Tuple[int, int] = (10 ** 6, 10 ** 6)
    branch_terms = [t for t, cov in coverage.items() if cov & uncovered]

    def search(need: Set[int], acc: List[Term]) -> None:
        nonlocal best, best_cost
        if not need:
            cost = _cost(chosen + acc)
            if cost < best_cost:
                best_cost, best = cost, chosen + acc
            return
        if _cost(chosen + acc) >= best_cost:
            return
        pivot = min(need, key=lambda m: sum(1 for t in branch_terms if m in coverage[t]))
        for t in branch_terms:
            if pivot in coverage[t]:
                search(need - coverage[t], acc + [t])

    search(set(uncovered), [])
    return best


def minimal_dnf_for_minterms(ones: Iterable[int], n: int) -> List[Term]:
    """МДНФ по номерам наборов. Пустой список = константа 0."""
    ones_set = set(ones)
    if not ones_set:
        return []
    if len(ones_set) == 1 << n:  # тавтология: единственный терм без литералов
        return [(0, 0)]
    return minimal_cover(ones_set, prime_implicants(ones_set, n))


def minimal_dnf(node: Node, var_order: Sequence[str]) -> List[Term]:
    """МДНФ для готового AST."""
    return minimal_dnf_for_minterms(minterms(node, var_order), len(var_order))


def term_to_text(term: Term, var_names: Sequence[str]) -> str:
    """Терм в виде конъюнкции литералов.

    Соглашение о битах: переменная ``var_names[i]`` занимает бит ``n-1-i``
    (первая переменная — старший бит), как в таблице истинности.
    """
    value, care = term
    if care == 0:
        return "1"
    n = len(var_names)
    parts: List[str] = []
    for i, name in enumerate(var_names):
        bit = 1 << (n - 1 - i)
        if care & bit:
            parts.append(name if value & bit else "¬" + name)
    return "∧".join(parts)


def dnf_to_text(terms: Sequence[Term], var_names: Sequence[str]) -> str:
    if not terms:
        return "0"
    return "∨".join(term_to_text(t, var_names) for t in terms)


def terms_to_ast(terms: Sequence[Term], var_names: Sequence[str]) -> Node:
    """Обратное преобразование МДНФ в AST (для проверок и тестов)."""

    n = len(var_names)

    def term_node(term: Term) -> Node:
        value, care = term
        literals: List[Node] = []
        for i, name in enumerate(var_names):
            bit = 1 << (n - 1 - i)
            if care & bit:
                literals.append(Var(name) if value & bit else Not(Var(name)))
        if not literals:
            raise ValueError("константный терм нельзя представить без констант")
        node = literals[0]
        for lit in literals[1:]:
            node = Bin("AND", node, lit)
        return node

    nodes = [term_node(t) for t in terms]
    if not nodes:
        raise ValueError("пустая ДНФ")
    result = nodes[0]
    for extra in nodes[1:]:
        result = Bin("OR", result, extra)
    return result


def dnf_literal_count_of(node: Node, var_order: Sequence[str]) -> int:
    """Число литералов в МДНФ функции, заданной произвольным выражением."""
    return literal_count(minimal_dnf(node, var_order))


def names_for(node: Node, var_order: Sequence[str] | None = None) -> List[str]:
    return list(var_order) if var_order is not None else list(vars_in(node))

