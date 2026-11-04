"""Типы заданий: реестр и повторный экспорт."""
from __future__ import annotations

from . import count_ones, evaluate, simplify, truth_table, columns  # noqa: F401  (регистрация)
from .base import REGISTRY, TaskPlugin, available, get, register

__all__ = ["REGISTRY", "TaskPlugin", "available", "get", "register"]
