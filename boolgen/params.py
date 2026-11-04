"""Параметры генерации — публичный контракт системы.

Один и тот же объект ``Params`` используется как:
* входные данные от пользователя (веб-форма / API),
* спецификация для генератора,
* и эталон для проверки соответствия в верификаторе.
Именно поэтому он строго валидируется один раз, а дальше не меняется.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional, Tuple

from .ast import ALL_OPS, BINARY_OPS, UNARY_OPS

TASK_TYPES: Tuple[str, ...] = (
    "truth_table",   # построить таблицу истинности
    "evaluate",      # вычислить значение на наборе
    "count_ones",    # сколько наборов дают F = 1
    "columns",       # восстановить соответствие столбцов (задание 2 ЕГЭ)
    "simplify",      # привести к МДНФ
)
DIFFICULTIES: Tuple[str, ...] = ("easy", "medium", "hard", "any")
STYLES: Tuple[str, ...] = ("ege", "neutral")
DEFAULT_VAR_NAMES = ("A", "B", "C", "D", "E")


class ParamsError(ValueError):
    """Некорректные параметры генерации."""


@dataclass(frozen=True)
class Params:
    """Параметры генерации одного пакета заданий."""

    task_type: str = "truth_table"
    operations: Tuple[str, ...] = ("NOT", "AND", "OR")
    variables: int = 3
    depth: int = 3
    nodes_max: int = 12
    count: int = 5
    difficulty: str = "medium"
    forbidden_operations: Tuple[str, ...] = ()
    avoid_trivial: bool = True
    require_all_vars: bool = True
    var_names: Tuple[str, ...] = ()
    style: str = "ege"
    seed: Optional[int] = None
    source: str = "procedural"  # procedural | llm
    extra: Dict[str, Any] = field(default_factory=dict)

    # -- производные значения ---------------------------------------------- #
    def names(self) -> Tuple[str, ...]:
        """Имена переменных: явные или A, B, C… по числу переменных."""
        if self.var_names:
            return tuple(self.var_names)
        return DEFAULT_VAR_NAMES[: self.variables]

    def ops(self) -> Tuple[str, ...]:
        """Разрешённые операции без запрещённых."""
        return tuple(op for op in self.operations if op not in self.forbidden_operations)

    def ops_binary(self) -> Tuple[str, ...]:
        return tuple(op for op in self.ops() if op in BINARY_OPS)

    def ops_unary(self) -> Tuple[str, ...]:
        return tuple(op for op in self.ops() if op in UNARY_OPS)


    # -- валидация ---------------------------------------------------------- #
    def validate(self) -> "Params":
        errors = []

        if self.task_type not in TASK_TYPES:
            errors.append(f"task_type={self.task_type!r} не из {list(TASK_TYPES)}")
        if not self.operations:
            errors.append("нужно разрешить хотя бы одну операцию")
        for op in self.operations:
            if op not in ALL_OPS:
                errors.append(f"неизвестная операция {op!r}")
        for op in self.forbidden_operations:
            if op not in ALL_OPS:
                errors.append(f"неизвестная запрещённая операция {op!r}")
        if set(self.operations) & set(self.forbidden_operations):
            errors.append("операция не может быть одновременно разрешённой и запрещённой")
        if not (2 <= self.variables <= 5):
            errors.append("variables должно быть от 2 до 5")
        if not (1 <= self.depth <= 5):
            errors.append("depth должно быть от 1 до 5")
        if not (3 <= self.nodes_max <= 40):
            errors.append("nodes_max должно быть от 3 до 40")
        if not (1 <= self.count <= 100):
            errors.append("count должно быть от 1 до 100")
        if self.difficulty not in DIFFICULTIES:
            errors.append(f"difficulty={self.difficulty!r} не из {list(DIFFICULTIES)}")
        if self.style not in STYLES:
            errors.append(f"style={self.style!r} не из {list(STYLES)}")
        if self.var_names:
            if len(self.var_names) != self.variables:
                errors.append("длина var_names должна равняться variables")
            if len(set(self.var_names)) != len(self.var_names):
                errors.append("var_names содержит повторы")
            for name in self.var_names:
                if not name.isidentifier():
                    errors.append(f"недопустимое имя переменной {name!r}")
        if self.operations and not self.ops():
            errors.append("после применения запретов не осталось ни одной операции")
        if self.nodes_max < self.depth + 1:
            errors.append("nodes_max слишком мал для заданной глубины")
        if self.operations and not self.ops_binary() and self.depth > 2:
            errors.append("только NOT: глубину больше 2 задать нельзя")

        if errors:
            raise ParamsError("; ".join(errors))
        return self

    # -- сериализация ------------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "operations": list(self.operations),
            "variables": self.variables,
            "depth": self.depth,
            "nodes_max": self.nodes_max,
            "count": self.count,
            "difficulty": self.difficulty,
            "forbidden_operations": list(self.forbidden_operations),
            "avoid_trivial": self.avoid_trivial,
            "require_all_vars": self.require_all_vars,
            "var_names": list(self.var_names),
            "style": self.style,
            "seed": self.seed,
            "source": self.source,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Params":
        allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = set(data) - allowed
        if unknown:
            raise ParamsError(f"неизвестные параметры: {sorted(unknown)}")
        payload = dict(data)
        for key in ("operations", "forbidden_operations", "var_names"):
            if key in payload and payload[key] is not None:
                payload[key] = tuple(payload[key])
        return cls(**payload).validate()

    def replace(self, **changes: Any) -> "Params":
        return replace(self, **changes)

    def fingerprint(self) -> str:
        """Устойчивый хеш параметров (без seed/count) — ключ для пула заданий."""
        payload = self.to_dict()
        for key in ("seed", "count"):
            payload.pop(key, None)
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

