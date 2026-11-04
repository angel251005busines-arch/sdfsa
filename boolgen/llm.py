"""LLM-драйвер: модель отвечает ТОЛЬКО за формулировку, и то под проверкой.

Почему так:
* для школы/ЕГЭ нужны стандартные формулировки — свободный текст скорее вредит;
* любая ошибка модели в тексте (потерянное «не», изменённая формула, другие
  числа) обнаруживается дешёвой проверкой и откатывается к шаблону.

Драйвер совместим с любым OpenAI-подобным API: Ollama (``/v1``), llama.cpp
server, vLLM. Никаких сторонних библиотек не требуется — только ``urllib``.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Protocol

from .phrasing import build_prompt

SYSTEM_PROMPT = (
    "Ты — методист по информатике. Переформулируй текст задания, СОХРАНИВ БЕЗ ИЗМЕНЕНИЙ:\n"
    "1) логическое выражение (символ в символ),\n"
    "2) имена всех переменных,\n"
    "3) все числа,\n"
    "4) требуемую форму ответа.\n"
    "Не добавляй подсказок, пояснений и ответов. Верни JSON: {{\"prompt\": \"...\"}}.\n"
    "Исходный текст: {prompt}\n"
    "Выражение (не менять): {expression}"
)


class PhraseDriver(Protocol):
    """Интерфейс драйвера формулировок."""

    def phrase(self, task: Dict[str, Any]) -> str:
        ...


class TemplateDriver:
    """Детерминированные шаблоны — безопасный режим по умолчанию."""

    def __init__(self, style: str = "ege") -> None:
        self.style = style

    def phrase(self, task: Dict[str, Any]) -> str:
        return build_prompt(task, self.style)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


class OpenAICompatDriver:
    """Формулировки через OpenAI-совместимый HTTP API с откатом на шаблон."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "qwen2.5:7b-instruct",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        temperature: float = 0.4,
        style: str = "ege",
        fallback: Optional[PhraseDriver] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.fallback = fallback or TemplateDriver(style)

    # -- HTTP --------------------------------------------------------------- #
    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=data, headers=headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # -- проверка текста модели --------------------------------------------- #
    def validate(self, task: Dict[str, Any], text: str) -> bool:
        """Текст модели годен, только если не искажает смысл задания."""
        if not isinstance(text, str) or len(text.strip()) < 10 or len(text) > 1200:
            return False
        expression = str(task.get("expression", ""))
        if _normalize(expression) not in _normalize(text):
            return False
        for name in task.get("var_order") or task.get("variables") or []:
            if not re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", text):
                return False
        # Модель не должна «дописать» ответ: запрещаем явные формулировки ответа.
        banned = ("ответ:", "ответ —", "ответ -", "получаем", "следовательно", "значит,")
        lowered = text.lower()
        return not any(word in lowered for word in banned)

    def phrase(self, task: Dict[str, Any]) -> str:
        base = self.fallback.phrase(task)
        request_text = SYSTEM_PROMPT.format(
            prompt=base, expression=task.get("expression", "")
        )
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": "Ты аккуратный методист. Отвечай только JSON."},
                {"role": "user", "content": request_text},
            ],
            "response_format": {"type": "json_object"},
        }
        try:
            data = self._post(payload)
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            text = parsed.get("prompt", "")
        except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
            return base
        return text if self.validate(task, text) else base


def make_driver(source: str = "procedural", **kwargs: Any) -> PhraseDriver:
    """Фабрика драйверов: ``procedural`` (шаблоны) или ``llm`` (модель)."""
    if source == "llm":
        fallback = TemplateDriver(kwargs.pop("style", "ege"))
        return OpenAICompatDriver(fallback=fallback, **kwargs)
    return TemplateDriver(kwargs.get("style", "ege"))
