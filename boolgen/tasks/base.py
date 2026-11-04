"""Базовый интерфейс типа задания и реестр плагинов.

Тип задания — это плагин с четырьмя обязанностями:

* ``build``            — построить «тело» задания: данные для отображения и эталон;
* ``check_reference``  — пересчитать всё с нуля и сверить с тем, что заявлено;
* ``check_uniqueness`` — проверить, что у задания ровно один правильный ответ;
* ``check_answer``     — проверить ответ ученика (используется при выдаче).

Благодаря этому верификатор не знает ничего специфического про типы заданий,
а новый тип добавляется одним файлом.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Sequence, Type

from ..ast import Node
from ..params import Params


class TaskPlugin:
    """Интерфейс плагина типа задания."""

    name: str = ""
    answer_kind: str = ""

    # -- построение --------------------------------------------------------- #
    def build(self, node: Node, params: Params, rng: random.Random) -> Dict[str, Any]:
        """Вернуть ``{"display": {...}, "reference": {...}}``."""
        raise NotImplementedError

    # -- проверка ----------------------------------------------------------- #
    def check_reference(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        """Сверить заявленный эталон с пересчитанным. Возвращает список ошибок."""
        raise NotImplementedError

    def check_uniqueness(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        """Проверить неоднозначность задания. По умолчанию ответ считается однозначным."""
        return []

    def check_quality(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any]
    ) -> List[str]:
        """Дополнительные педагогические проверки, специфичные для типа задания."""
        return []

    def check_answer(
        self, node: Node, var_order: Sequence[str], task: Dict[str, Any], answer: Any
    ) -> bool:
        """Проверить ответ ученика против эталона."""
        raise NotImplementedError

    # -- служебное ---------------------------------------------------------- #
    def template_key(self) -> str:
        """Ключ шаблона формулировки (может отличаться от ``name``)."""
        return self.name


REGISTRY: Dict[str, TaskPlugin] = {}


def register(cls: Type[TaskPlugin]) -> Type[TaskPlugin]:
    """Зарегистрировать плагин по ``cls.name``."""
    instance = cls()
    if not instance.name:
        raise ValueError(f"у плагина {cls.__name__} не задано имя")
    REGISTRY[instance.name] = instance
    return cls


def get(name: str) -> TaskPlugin:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(f"неизвестный тип задания {name!r}; есть: {sorted(REGISTRY)}") from None


def available() -> List[str]:
    return sorted(REGISTRY)


def normalize_bits(values: Sequence[Any]) -> List[int]:
    """Привести строки вида ``"0"/"1"``, ``True/False``, ``И/Л`` к 0/1."""
    mapping = {
        "0": 0, "1": 1, "false": 0, "true": 1, "л": 0, "и": 1,
        "нет": 0, "да": 1, "ложь": 0, "истина": 1,
    }
    out: List[int] = []
    for value in values:
        if isinstance(value, bool):
            out.append(int(value))
            continue
        if isinstance(value, int) and value in (0, 1):
            out.append(value)
            continue
        key = str(value).strip().lower()
        if key not in mapping:
            raise ValueError(f"не удалось разобрать значение {value!r} как 0/1")
        out.append(mapping[key])
    return out
