"""Точка входа CLI: разбор аргументов и запуск команд.

Примеры::

    python -m boolgen.cli selftest
    python -m boolgen.cli demo --count 2
    python -m boolgen.cli gen --type columns --vars 3 --depth 3 --count 5 --json
    python -m boolgen.cli serve --port 8000
"""
from __future__ import annotations

import argparse
import sys

from . import CORE_VERSION, commands
from .generator import GenerationError
from .params import DIFFICULTIES, TASK_TYPES, ParamsError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="boolgen",
        description="Генератор заданий по алгебре логики с ядром-верификатором",
    )
    parser.add_argument("--version", action="version", version=f"boolgen {CORE_VERSION}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--type", default="truth_table", choices=list(TASK_TYPES))
    common.add_argument("--ops", default="NOT,AND,OR", help="разрешённые операции через запятую")
    common.add_argument("--forbid", default="", help="запрещённые операции через запятую")
    common.add_argument("--vars", type=int, default=3, help="число переменных (2..5)")
    common.add_argument("--depth", type=int, default=3, help="глубина выражения (1..5)")
    common.add_argument("--nodes-max", dest="nodes_max", type=int, default=17)
    common.add_argument("--difficulty", default="medium", choices=list(DIFFICULTIES))
    common.add_argument("--count", type=int, default=3)
    common.add_argument("--seed", type=int, default=None)

    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", parents=[common], help="демонстрация всех типов")
    demo.set_defaults(func=commands.cmd_demo)

    gen = subparsers.add_parser("gen", parents=[common], help="сгенерировать задания")
    gen.add_argument("--json", action="store_true", help="вывести JSON")
    gen.add_argument("--pool", default=":memory:", help="файл пула SQLite")
    gen.set_defaults(func=commands.cmd_gen)

    check = subparsers.add_parser("verify", parents=[common], help="проверить внешний JSON")
    check.add_argument("file", help="JSON-файл: одно задание или список")
    check.set_defaults(func=commands.cmd_verify)

    selftest = subparsers.add_parser("selftest", help="самопроверка ядра")
    selftest.add_argument("--rounds", type=int, default=200)
    selftest.add_argument("--seed", type=int, default=12345)
    selftest.set_defaults(func=commands.cmd_selftest)

    pool = subparsers.add_parser("pool", help="состояние пула заданий")
    pool.add_argument("--pool", default="boolgen_pool.sqlite", help="файл пула SQLite")
    pool.add_argument("--quarantine", type=int, default=0,
                      help="показать N заданий из карантина с причинами отказа")
    pool.set_defaults(func=commands.cmd_pool)

    serve = subparsers.add_parser("serve", help="HTTP API и демо-страница")
    serve.add_argument("--host", default="127.0.0.1", help="адрес (0.0.0.0 — для доступа с других машин)")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--pool", default="boolgen_pool.sqlite")
    serve.add_argument("--no-open", dest="no_open", action="store_true",
                       help="не открывать браузер автоматически")
    serve.set_defaults(func=commands.cmd_serve)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ParamsError as exc:
        print(f"ошибка параметров: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"файл не найден: {exc}", file=sys.stderr)
        return 2
    except GenerationError as exc:
        print(f"не удалось сгенерировать задание: {exc}", file=sys.stderr)
        print(
            "подсказка: попробуйте увеличить --nodes-max, разрешить больше операций "
            "(--ops NOT,AND,OR,IMPL) или изменить --depth/--difficulty",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
