"""Веб-маршруты аутентификации для HTTP-сервера boolgen.

Добавляются поверх существующего сервера :mod:`boolgen.api` без изменения
его исходного кода. Маршруты:

* ``GET  /login``      — страница входа (HTML)
* ``POST /login``      — JSON вход, устанавливает cookie session_token
* ``POST /logout``     — выход, удаляет cookie
* ``GET  /me``         — информация о текущем пользователе (JSON)
* ``GET  /me/stats``   — персональная статистика (JSON)

Использование: создать ``AuthHandler`` вместо обычного Handler из api.py,
передав ему ``UserTaskService``.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

from .service_wrapper import UserTaskService


class AuthHandler(BaseHTTPRequestHandler):
    """Обработчик с маршрутами auth. Остальные пути deleгируются в
    переданный ``fallback`` обработчик (обычный Handler из api.py)."""

    server_version = "boolgen-auth/0.1.0"

    def __init__(self, *args: Any, service: UserTaskService, fallback: Any, **kwargs: Any) -> None:
        self._service = service
        self._fallback = fallback
        super().__init__(*args, **kwargs)

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._respond(status, body, "application/json; charset=utf-8")

    def _html(self, status: int, html: str) -> None:
        self._respond(status, html.encode("utf-8"), "text/html; charset=utf-8")

    def _token(self) -> str | None:
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("session_token="):
                return part.split("=", 1)[1]
        return None

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        payload = self._body()

        if path == "/login":
            username = str(payload.get("username", ""))
            password = str(payload.get("password", ""))
            ok, token = self._service.login(username, password)
            if ok:
                self._json(200, {"ok": True, "username": username})
                self.send_header("Set-Cookie", f"session_token={token}; Path=/; HttpOnly; SameSite=Lax")
            else:
                self._json(401, {"ok": False, "error": "неверный логин или пароль"})
            self.end_headers()
            return
        if path == "/logout":
            self._service.logout(self._token())
            self._json(200, {"ok": True})
            self.send_header("Set-Cookie", "session_token=; Path=/; Max-Age=0")
            self.end_headers()
            return
        if path == "/register":
            username = str(payload.get("username", ""))
            password = str(payload.get("password", ""))
            ok, msg = self._service.register(username, password)
            self._json(200 if ok else 400, {"ok": ok, "message": msg})
            return
        self._delegate()

    def _delegate(self) -> None:
        handler = self._fallback(
            self.rfile, self.wfile, self.server,  # type: ignore[arg-type]
        )
        method = "do_" + self.command
        if hasattr(handler, method):
            getattr(handler, method)()


LOGIN_PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Вход — boolgen</title>
<style>body{font-family:system-ui,sans-serif;max-width:400px;margin:60px auto;padding:16px;}
input{width:100%;padding:8px;margin:6px 0;border:1px solid #888;border-radius:8px;}
button{width:100%;padding:8px;background:#4c7dff;color:#fff;border:none;border-radius:8px;cursor:pointer;}
a{color:#4c7dff;text-decoration:none;} .err{color:#d93b3b;font-size:.9rem;}</style></head>
<body>
<h2>Вход в генератор заданий</h2>
<form id="f"><div class="err" id="err"></div>
<input name="username" placeholder="Логин (мин. 3 символа)" required>
<input type="password" name="password" placeholder="Пароль (мин. 4 символа)" required>
<button type="submit">Войти</button></form>
<p>Нет аккаунта? нажмите "Зарегистрироваться" в меню</p>
<script>
document.getElementById('f').onsubmit=async(e)=>{
 e.preventDefault();const fd=new FormData(e.target);
 const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({username:fd.get('username'),password:fd.get('password')})});
 const d=await r.json();document.getElementById('err').textContent=d.error||'';
 if(d.ok)location.href='/';
};
</script></body></html>"""
