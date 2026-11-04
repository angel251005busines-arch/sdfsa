"""Формулировки заданий — детерминированные шаблоны в стиле ФИПИ.

Почему шаблоны, а не свободный текст от LLM: формулировка задания влияет на
смысл ответа («упростите» ≠ «минимизируйте»). Шаблон гарантирует, что текст
всегда соответствует эталону, а LLM можно оставить только как
стилистический слой с обязательной проверкой (см. ``llm.py``).
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

TEMPLATES: Dict[str, Dict[str, str]] = {
    "ege": {
        "truth_table": (
            "Постройте таблицу истинности для логической функции F = {expr} "
            "от переменных {names}."
        ),
        "evaluate": (
            "Вычислите значение логического выражения F = {expr} при {assignment}."
        ),
        "count_ones": (
            "Сколько существует различных наборов значений логических переменных "
            "{names}, при которых логическое выражение F = {expr} истинно?"
        ),
        "columns": (
            "Логическая функция F задаётся выражением F = {expr}. "
            "В таблице истинности переменные {names} обозначены как {columns}, "
            "но соответствие столбцов переменным неизвестно. {fragment_note} "
            "Определите, какой столбец соответствует каждой переменной. "
            "В ответе запишите {n} буквы без пробелов: i-я буква — переменная "
            "в i-м столбце (считая слева)."
        ),
        "simplify": (
            "Приведите логическое выражение F = {expr} к минимальной дизъюнктивной "
            "нормальной форме (МДНФ) и запишите полученную функцию."
        ),
    },
    "neutral": {
        "truth_table": "Постройте таблицу истинности функции F = {expr} (переменные {names}).",
        "evaluate": "Найдите значение F = {expr} при {assignment}.",
        "count_ones": "Сколько наборов переменных {names} дают F = 1 для F = {expr}?",
        "columns": (
            "Функция F = {expr}. Дан фрагмент таблицы истинности, в которой {names} "
            "обозначены как {columns} в неизвестном порядке. Укажите, какой столбец "
            "какой переменной соответствует."
        ),
        "simplify": "Приведите F = {expr} к МДНФ.",
    },
}


def _names_text(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " и " + names[-1]


def _assignment_text(assignment: Dict[str, Any]) -> str:
    return ", ".join(f"{name} = {value}" for name, value in assignment.items())


def _columns_text(count: int) -> str:
    if count == 1:
        return "x1"
    return f"x1, …, x{count}"


#: Пояснение к фрагменту таблицы: от него зависит смысл задания.
FRAGMENT_NOTES = {
    "all_ones": "Ниже приведены все наборы, при которых F = 1.",
    "all_zeros": "Ниже приведены все наборы, при которых F = 0.",
    "partial": "Ниже приведён фрагмент таблицы истинности.",
}


def template_vars(task: Dict[str, Any]) -> Dict[str, Any]:
    names = list(task.get("var_order") or task.get("variables") or [])
    display = task.get("display") or {}
    return {
        "expr": task.get("expression", ""),
        "names": _names_text(names),
        "n": len(names),
        "columns": _columns_text(len(names)),
        "first_column": "x1",
        "assignment": _assignment_text(display.get("assignment") or {}),
        "fragment_note": FRAGMENT_NOTES.get(
            str(display.get("fragment_kind") or "partial"), FRAGMENT_NOTES["partial"]
        ),
    }


def build_prompt(task: Dict[str, Any], style: str = "ege") -> str:
    """Собрать текст задания по шаблону."""
    style_table = TEMPLATES.get(style) or TEMPLATES["ege"]
    template = style_table.get(task["task_type"])
    if template is None:
        raise KeyError(f"нет шаблона для типа задания {task['task_type']!r}")
    return template.format(**template_vars(task))


def render_table(display: Dict[str, Any]) -> str:
    """Текстовое представление фрагмента таблицы (для CLI/логов)."""
    header = display.get("header") or []
    rows: List[Sequence[Any]] = display.get("rows") or []
    if not header:
        return ""
    width = [max(len(str(header[i])), *(len(str(r[i])) for r in rows)) if rows else len(str(header[i]))
             for i in range(len(header))]
    def line(cells: Sequence[Any]) -> str:
        return " | ".join(str(c).ljust(width[i]) for i, c in enumerate(cells))
    out = [line(header), "-+-".join("-" * w for w in width)]
    out.extend(line(row) for row in rows)
    return "\n".join(out)
