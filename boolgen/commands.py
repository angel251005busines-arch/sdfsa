"""Реализация команд CLI. Точка входа — :mod:`boolgen.cli`."""
from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

from . import qm
from .ast import to_text, vars_in
from .generator import random_expression
from .params import Params
from .parser import parse
from .phrasing import render_table
from .semantics import mask, minterms, truth_rows, truth_rows_via_python
from .service import TaskService
from .verify import verify_task


def params_from_args(args: argparse.Namespace) -> Params:
    operations = tuple(op.strip().upper() for op in args.ops.split(",") if op.strip())
    forbidden = tuple(op.strip().upper() for op in args.forbid.split(",") if op.strip())
    return Params(
        task_type=args.type,
        operations=operations,
        variables=args.vars,
        depth=args.depth,
        nodes_max=args.nodes_max,
        count=args.count,
        difficulty=args.difficulty,
        forbidden_operations=forbidden,
        seed=args.seed,
    ).validate()


def cmd_demo(args: argparse.Namespace) -> int:
    """Сгенерировать и проверить задания каждого типа."""
    from .params import TASK_TYPES

    for task_type in TASK_TYPES:
        params = params_from_args(args).replace(task_type=task_type)
        report = TaskService().produce(params, count=args.count)
        print(
            f"=== {task_type}: принято {len(report['accepted'])}, "
            f"отклонено {len(report['rejected'])}, попыток {report['attempts']}"
        )
        for task in report["accepted"]:
            print(f"  выражение : {task['expression']}")
            print(f"  сложность : {task['difficulty_score']}")
            print(f"  задание   : {task['prompt']}")
            if task["display"].get("rows"):
                for line in render_table(task["display"]).splitlines():
                    print(f"    {line}")
            print(f"  эталон    : {json.dumps(task['reference'], ensure_ascii=False)}")
            print()
        for rejected in report["rejected"][:3]:
            print(f"  отклонено: {json.dumps(rejected, ensure_ascii=False)[:200]}")
    return 0


def cmd_gen(args: argparse.Namespace) -> int:
    params = params_from_args(args)
    report = TaskService(pool_path=args.pool).produce(params, count=args.count)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"принято {len(report['accepted'])} из {report['attempts']} попыток")
    for index, task in enumerate(report["accepted"], 1):
        print(f"\n[{index}] {task['prompt']}")
        if task["display"].get("rows"):
            for line in render_table(task["display"]).splitlines():
                print("    " + line)
        print(f"    эталон: {json.dumps(task['reference'], ensure_ascii=False)}")
    return 0


def _extract_tasks(payload: Any) -> List[Dict[str, Any]]:
    """Достать список заданий из JSON: список, отчёт ``gen`` или одиночное задание."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("tasks", "accepted", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload]
    raise ValueError("ожидался JSON-объект или список заданий")


def cmd_verify(args: argparse.Namespace) -> int:
    """Проверить внешние задания (например, JSON от LLM-генератора)."""
    params = params_from_args(args)
    with open(args.file, encoding="utf-8") as handle:
        payload = json.load(handle)
    tasks = _extract_tasks(payload)
    if not tasks:
        print("в файле нет заданий")
        return 1
    seen: set = set()
    failed = 0
    for index, task in enumerate(tasks, 1):
        verdict = verify_task(task, params, seen=seen)
        print(f"[{index}] {'OK' if verdict.ok else 'ОТКЛОНЕНО'} {task.get('expression', '')}")
        if verdict.ok and verdict.canonical is not None:
            seen.add(verdict.canonical)
        else:
            failed += 1
            for violation in verdict.violations:
                print(f"    {violation}")
    print(f"\nитого: принято {len(tasks) - failed}, отклонено {failed}")
    return 0 if failed == 0 else 1


def cmd_selftest(args: argparse.Namespace) -> int:
    """Самопроверка ядра: два движка, round-trip парсера, покрытие МДНФ."""
    import random

    rng = random.Random(args.seed)
    names = ["A", "B", "C"]
    failures = 0
    stats: Dict[str, int] = {"движки": 0, "round_trip": 0, "мднф": 0}

    for _ in range(args.rounds):
        node = random_expression(rng, names, depth=3)
        order = vars_in(node)

        if truth_rows(node, order) != truth_rows_via_python(node, order):
            stats["движки"] += 1
            print(f"РАСХОЖДЕНИЕ ДВИЖКОВ: {to_text(node)}")

        if parse(to_text(node)) != node:
            stats["round_trip"] += 1
            print(f"ROUND-TRIP: {to_text(node)}")

        ones = minterms(node, order)
        if ones:
            terms = qm.minimal_dnf(node, order)
            covered = 0
            for m in range(1 << len(order)):
                if any(qm.covers(term, m) for term in terms):
                    covered |= 1 << m
            if covered != mask(node, order):
                stats["мднф"] += 1
                print(f"МДНФ НЕ ПОКРЫВАЕТ ФУНКЦИЮ: {to_text(node)}")

    failures = sum(stats.values())
    detail = ", ".join(f"{key}: {value}" for key, value in stats.items())
    print(f"проверено {args.rounds} формул — сбои: {failures} ({detail})")
    return 0 if failures == 0 else 1


def cmd_pool(args: argparse.Namespace) -> int:
    """Показать состояние пула: сколько проверенных, сколько в карантине."""
    from .pool import TaskPool

    pool = TaskPool(args.pool)
    stats = pool.stats()
    print(f"пул: {args.pool}")
    print(f"  всего заданий : {stats['total']}")
    print(f"  опубликовано  : {stats['published']}")
    print(f"  в карантине   : {stats['quarantined']}")
    print(f"  доля брака    : {stats['reject_rate']:.1%}")
    if args.quarantine:
        items = pool.quarantined(limit=args.quarantine)
        if not items:
            print("\n  карантин пуст")
        for task_id, expression, violations in items:
            print(f"\n  [{task_id}] {expression}")
            for violation in violations:
                print(f"      {violation['layer']}/{violation['code']}: "
                      f"{violation['message'][:120]}")
    pool.close()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .api import serve

    serve(
        host=args.host,
        port=args.port,
        pool_path=args.pool,
        open_browser=not args.no_open,
    )
    return 0
