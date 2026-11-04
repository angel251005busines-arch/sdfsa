"""Верификатор — доверенное ядро системы.

Ничто не попадает пользователю, пока не пройдёт все слои проверок:

1. ``schema``     — структура задания и обязательные поля;
2. ``syntax``     — выражение разбирается в AST нашим парсером (без eval текста);
3. ``params``     — соответствие заданным параметрам (операции, переменные,
                    глубина, размер, коридор сложности);
4. ``semantics``  — согласие ДВУХ независимых вычислителей истинности;
5. ``reference``  — пересчёт эталонного ответа и сверка с заявленным;
6. ``prompt``     — текст задания содержит именно то выражение, которое проверено;
7. ``quality``    — нетривиальность, отсутствие вырожденности, однозначность ответа;
8. ``dedup``      — задание не дублирует уже принятые (по канонической подписи).

Задача верификатора — быть параноидальным. Любая ошибка здесь дороже, чем
лишний отказ: в пул попадают только задания, прошедшие все слои.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import CORE_VERSION
from .ast import Node, depth, node_count, ops_in, to_text, vars_in
from .generator import has_absorption, is_structurally_trivial
from .metrics import difficulty_score, in_corridor, metrics as compute_metrics
from .params import Params
from .parser import try_parse
from .semantics import (
    canonical_key,
    depends_on,
    is_contradiction,
    is_tautology,
    truth_rows,
    truth_rows_via_python,
)
from .tasks.base import get as get_plugin

REQUIRED_FIELDS = ("task_type", "expression", "variables", "prompt", "reference")

CanonicalKey = Tuple[int, int]


@dataclass(frozen=True)
class Violation:
    """Одно нарушение: слой, машинный код и человекочитаемое сообщение."""

    layer: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.layer}/{self.code}] {self.message}"


@dataclass
class Verdict:
    """Результат проверки задания."""

    ok: bool
    violations: List[Violation] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    canonical: Optional[CanonicalKey] = None
    core_version: str = CORE_VERSION

    def codes(self) -> List[str]:
        return [v.code for v in self.violations]

    def report(self) -> str:
        if self.ok:
            score = self.metrics.get("difficulty_score")
            return f"OK  (сложность {score}, узлов {self.metrics.get('nodes')})"
        return "\n".join(str(v) for v in self.violations)


def _normalize(text: str) -> str:
    """Нормализация для сравнения формулировки с выражением."""
    text = text.replace("−", "-").replace("–", "-")
    text = re.sub(r"\s+", "", text)
    return text.lower()


def verify_task(
    task: Dict[str, Any],
    params: Params,
    seen: Optional[Set[CanonicalKey]] = None,
) -> Verdict:
    """Проверить одно задание по всем слоям. ``seen`` — подписи уже принятых заданий."""
    violations: List[Violation] = []

    def add(layer: str, code: str, message: str) -> None:
        violations.append(Violation(layer, code, message))

    # --- 1. схема ------------------------------------------------------- #
    for name in REQUIRED_FIELDS:
        if name not in task:
            add("schema", "missing_field", f"отсутствует поле {name!r}")
    if violations:
        return Verdict(False, violations)

    if task["task_type"] != params.task_type:
        add("schema", "task_type_mismatch",
            f"тип {task['task_type']!r} вместо ожидаемого {params.task_type!r}")

    expression = task.get("expression")
    if not isinstance(expression, str) or not expression.strip():
        add("syntax", "empty_expression", "выражение пустое или не является строкой")
        return Verdict(False, violations)

    prompt = task.get("prompt")
    if not isinstance(prompt, str) or len(prompt.strip()) < 10:
        add("schema", "bad_prompt", "текст задания отсутствует или слишком короткий")

    var_order = list(params.names())
    declared = task.get("variables")
    if not isinstance(declared, list) or list(declared) != var_order:
        add("schema", "variables_mismatch", f"variables={declared}, ожидалось {var_order}")

    # --- 2. синтаксис: свой парсер, никакого eval ------------------------ #
    node, parse_error = try_parse(expression)
    if node is None:
        add("syntax", "parse_error", f"выражение не разбирается: {parse_error}")
        return Verdict(False, violations)

    used = list(vars_in(node))
    extra = sorted(set(used) - set(var_order))
    missing = sorted(set(var_order) - set(used))
    if extra or missing:
        add("params", "variable_set",
            f"лишние переменные {extra}, отсутствуют {missing}")
        return Verdict(False, violations)

    # --- 3. соответствие параметрам ------------------------------------- #
    used_ops = ops_in(node)
    allowed = set(params.ops())
    if not used_ops <= allowed:
        add("params", "forbidden_operation",
            f"использованы неразрешённые операции {sorted(used_ops - allowed)}")
    forbidden_hit = sorted(used_ops & set(params.forbidden_operations))
    if forbidden_hit:
        add("params", "forbidden_operation",
            f"использованы запрещённые операции {forbidden_hit}")
    if node_count(node) > params.nodes_max:
        add("params", "too_many_nodes",
            f"узлов {node_count(node)} > {params.nodes_max}")
    if depth(node) != params.depth:
        add("params", "depth_mismatch", f"глубина {depth(node)} вместо {params.depth}")

    score = difficulty_score(node, var_order)
    if not in_corridor(score, params.difficulty, len(var_order)):
        add("params", "difficulty_out_of_corridor",
            f"сложность {score} вне коридора {params.difficulty}")
    claimed_score = task.get("difficulty_score")
    if isinstance(claimed_score, (int, float)) and abs(float(claimed_score) - score) > 0.02:
        add("params", "difficulty_drift",
            f"заявлена сложность {claimed_score}, пересчёт даёт {score}")

    # --- 4. семантика: сверка двух независимых движков ------------------ #
    if truth_rows(node, var_order) != truth_rows_via_python(node, var_order):
        add("semantics", "engine_mismatch",
            "движки вычисления истинности расходятся — дефект ядра, задание в карантин")

    # --- 5-7. проверки, специфичные для типа задания --------------------- #
    plugin = get_plugin(params.task_type)

    def run(check, layer: str, code: str) -> None:
        try:
            messages = check(node, var_order, task) or []
        except Exception as exc:  # проверка не должна ронять весь верификатор
            add(layer, "checker_crash", f"{type(exc).__name__}: {exc}")
            return
        for message in messages:
            add(layer, code, message)

    run(plugin.check_reference, "reference", "reference_mismatch")

    if isinstance(prompt, str) and prompt.strip():
        if _normalize(to_text(node)) not in _normalize(prompt):
            add("prompt", "expression_not_in_prompt",
                f"текст задания не содержит проверенного выражения {to_text(node)!r}")

    if params.avoid_trivial and is_structurally_trivial(node):
        add("quality", "trivial_structure", "выражение тривиально (¬¬A, A∧A, повтор литералов)")
    if params.avoid_trivial and has_absorption(node):
        add("quality", "absorption", "выражение содержит поглощение (X ∨ X∧Y ≡ X)")
    if is_tautology(node, var_order):
        add("quality", "tautology", "функция тождественно истинна")
    if is_contradiction(node, var_order):
        add("quality", "contradiction", "функция тождественно ложна")
    if params.require_all_vars:
        unused = [name for name, used_flag in depends_on(node, var_order).items() if not used_flag]
        if unused:
            add("quality", "redundant_variable",
                f"функция не зависит от переменных {unused}")

    run(plugin.check_uniqueness, "quality", "ambiguous")
    run(plugin.check_quality, "quality", "pedagogy")

    # --- 8. дедупликация -------------------------------------------------- #
    key = canonical_key(node)
    if seen is not None and key in seen:
        add("dedup", "duplicate",
            f"задание дублирует уже принятое (подпись {key[0]} переменных, маска {key[1]:#x})")

    return Verdict(
        ok=not violations,
        violations=violations,
        metrics=compute_metrics(node, var_order),
        canonical=key,
    )


def verify_batch(
    tasks: Sequence[Dict[str, Any]],
    params: Params,
    seen: Optional[Set[CanonicalKey]] = None,
) -> List[Tuple[Dict[str, Any], Verdict]]:
    """Проверить пакет заданий с дедупликацией внутри пакета."""
    seen_keys: Set[CanonicalKey] = set(seen or ())
    results: List[Tuple[Dict[str, Any], Verdict]] = []
    for task in tasks:
        verdict = verify_task(task, params, seen=seen_keys)
        if verdict.ok and verdict.canonical is not None:
            seen_keys.add(verdict.canonical)
        results.append((task, verdict))
    return results


def grade(task: Dict[str, Any], params: Params, answer: Any) -> bool:
    """Проверить ответ ученика. Выражение пересобирается из текста заново."""
    node, error = try_parse(str(task.get("expression", "")))
    if node is None:
        raise ValueError(f"выражение задания не разбирается: {error}")
    plugin = get_plugin(params.task_type)
    return plugin.check_answer(node, list(params.names()), task, answer)

