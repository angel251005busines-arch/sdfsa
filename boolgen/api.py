"""HTTP API и демо-страница. Только стандартная библиотека.

В продакшене этот слой меняется на FastAPI, но контракт остаётся тем же:

* ``POST /api/generate`` — параметры → пакет проверенных заданий;
* ``POST /api/check``    — ответ ученика → вердикт;
* ``GET  /api/pool/stats`` — статистика пула (доля брака = метрика качества);
* ``GET  /api/health``   — живость и версия ядра.
"""
from __future__ import annotations

import json
import sys
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Tuple

from . import CORE_VERSION
from .params import Params, ParamsError
from .service import TaskService

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")


def _read_static(name: str) -> str:
    """Прочитать файл из каталога ``web`` (демо-страница и её скрипты)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", name)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return "<h1>boolgen</h1><p>Демо-страница не найдена.</p>" if name.endswith(".html") else ""


def create_handler(service: TaskService):
    """Собрать обработчик запросов, привязанный к сервису."""

    class Handler(BaseHTTPRequestHandler):
        server_version = f"boolgen/{CORE_VERSION}"

        # -- служебное ------------------------------------------------------ #
        def _respond(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._respond(status, body, "application/json; charset=utf-8")

        def _html(self, status: int, html: str) -> None:
            self._respond(status, html.encode("utf-8"), "text/html; charset=utf-8")

        def log_message(self, fmt: str, *args: Any) -> None:  # тише в консоли
            return

        # -- GET ------------------------------------------------------------ #
        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._html(200, _read_static("index.html"))
            elif self.path == "/app.js":
                self._respond(200, _read_static("app.js").encode("utf-8"),
                              "application/javascript; charset=utf-8")
            elif self.path == "/api/health":
                self._json(200, {"status": "ok", "core_version": CORE_VERSION})
            elif self.path == "/api/pool/stats":
                self._json(200, service.pool.stats())
            else:
                self._json(404, {"error": "not found"})

        # -- POST ----------------------------------------------------------- #
        def _body(self) -> Tuple[Dict[str, Any], bool]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except ValueError:
                return {}, False
            return (payload if isinstance(payload, dict) else {}), True

        def do_POST(self) -> None:  # noqa: N802
            payload, parsed = self._body()
            if not parsed:
                self._json(400, {"error": "тело запроса не является JSON-объектом"})
                return

            if self.path == "/api/generate":
                raw_params = payload.get("params", payload)
                try:
                    params = Params.from_dict(raw_params)
                except ParamsError as exc:
                    self._json(400, {"error": str(exc), "kind": "params"})
                    return
                try:
                    tasks = service.get_tasks(params, count=params.count)
                except Exception as exc:  # генерация может не найти подходящих выражений
                    self._json(422, {"error": f"{type(exc).__name__}: {exc}"})
                    return
                self._json(
                    200,
                    {
                        "tasks": tasks,
                        "stats": service.pool.stats(),
                        "params": params.to_dict(),
                    },
                )
                return

            if self.path == "/api/check":
                task_id = str(payload.get("task_id") or "")
                try:
                    params = Params.from_dict(payload.get("params") or {})
                except ParamsError as exc:
                    self._json(400, {"error": str(exc), "kind": "params"})
                    return
                try:
                    correct = service.grade(task_id, params, payload.get("answer"))
                except KeyError as exc:
                    self._json(404, {"error": str(exc)})
                    return
                self._json(200, {"correct": bool(correct), "task_id": task_id})
                return

            self._json(404, {"error": "not found"})

    return Handler


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    pool_path: str = "boolgen_pool.sqlite",
    open_browser: bool = True,
) -> None:
    """Запустить HTTP-сервер (блокирующий вызов).

    ``open_browser`` открывает страницу в браузере, если он есть (на сервере
    без графики просто ничего не произойдёт).
    """
    service = TaskService(pool_path=pool_path)
    server = ThreadingHTTPServer((host, port), create_handler(service))
    url = f"http://{host}:{port}"
    print("=" * 52)
    print(f"  Генератор заданий запущен: {url}")
    print(f"  Пул заданий: {pool_path}")
    print("  Остановить: Ctrl+C")
    print("=" * 52)
    sys.stdout.flush()
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:  # на сервере без браузера это нормально
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлено пользователем")
    finally:
        server.server_close()
        service.pool.close()
