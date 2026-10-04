"""Клиент локальной модели Ollama. Ответ всегда запрашивается в формате JSON."""
import json
import time

import requests

from .config import Settings


class LLMError(Exception):
    """Модель недоступна или стабильно возвращает некорректный ответ."""


class OllamaClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.url = settings.ollama_url.rstrip("/")

    def ping(self) -> tuple[bool, str]:
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=5)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            if self.s.model not in names:
                return False, f"Ollama доступна, но модели {self.s.model} нет. Есть: {', '.join(names) or '—'}"
            return True, f"Ollama доступна, модель {self.s.model} найдена"
        except requests.RequestException as e:
            return False, f"Ollama недоступна по адресу {self.url}: {e}"

    def chat_json(self, system: str, user: str) -> dict:
        payload = {
            "model": self.s.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": "json",
            "stream": False,
            "options": {"temperature": self.s.temperature, "num_ctx": 8192},
        }
        last_error = ""
        for attempt in range(1, self.s.llm_retries + 2):
            try:
                r = requests.post(f"{self.url}/api/chat", json=payload, timeout=self.s.llm_timeout)
                r.raise_for_status()
                content = r.json()["message"]["content"]
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("ответ модели не является JSON-объектом")
                return data
            except requests.ConnectionError:
                raise LLMError(f"Нет связи с Ollama ({self.url}). Запустите Ollama и повторите.")
            except (requests.RequestException, KeyError, ValueError) as e:
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * attempt)
        raise LLMError(f"Модель не дала корректный ответ после {self.s.llm_retries + 1} попыток ({last_error})")
