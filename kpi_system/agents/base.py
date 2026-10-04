"""Базовый агент: вызовы LLM и инструментов с логированием, лимитами и повторными попытками."""
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..llm import LLMError, OllamaClient
from ..logger import RunLogger, short
from ..schemas import AgentMessage
from ..state import TaskState

T = TypeVar("T", bound=BaseModel)
MAX_TOOLS = 5


class AgentError(Exception):
    """Агент не смог выполнить задачу (после повторных попыток)."""


@dataclass
class RunContext:
    settings: Settings
    llm: OllamaClient
    logger: RunLogger
    state: TaskState


class BaseAgent:
    name = "base"
    role = ""

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.tools: dict[str, Callable[..., Any]] = self.register_tools()
        if len(self.tools) > MAX_TOOLS:
            raise ValueError(f"У агента {self.name} больше {MAX_TOOLS} инструментов")

    def register_tools(self) -> dict[str, Callable[..., Any]]:
        return {}

    # ---------- приём сообщения ----------
    def receive(self, msg: AgentMessage) -> AgentMessage:
        """Единая точка входа: агент получает типизированное сообщение и отвечает сообщением."""
        handler = getattr(self, f"on_{msg.type}", None)
        if handler is None:
            raise AgentError(f"{self.name} не умеет обрабатывать сообщения типа {msg.type}")
        self.ctx.logger.log("agent_start", self.name, msg_type=msg.type)
        result = handler(**msg.payload)
        return AgentMessage(sender=self.name, receiver=msg.sender, type=f"{msg.type}_result", payload=result)

    # ---------- инструменты ----------
    def use_tool(self, tool: str, **kwargs: Any) -> Any:
        if tool not in self.tools:
            raise AgentError(f"У агента {self.name} нет инструмента {tool}")
        self.ctx.state.tick()
        t0 = time.perf_counter()
        try:
            result = self.tools[tool](**kwargs)
        except Exception as e:
            self._log_call("tool_call", t0, tool=tool, args=short(kwargs), status="error", error=str(e))
            raise AgentError(f"Инструмент {tool}: {e}") from e
        self._log_call("tool_call", t0, tool=tool, args=short(kwargs), status="ok", result=short(result))
        return result

    # ---------- LLM ----------
    def ask_llm(self, system: str, user: str, schema: type[T]) -> T:
        """Запрос к модели с проверкой JSON по pydantic-схеме; при неверной структуре — повтор с подсказкой."""
        self.ctx.state.tick()
        t0 = time.perf_counter()
        prompt, last_error = user, ""
        attempts = self.ctx.settings.llm_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                raw = self.ctx.llm.chat_json(system, prompt)
                parsed = schema.model_validate(raw)
                self._log_call("llm_call", t0, schema=schema.__name__, attempts=attempt,
                               status="ok", prompt=short(user, 200), response=short(raw))
                return parsed
            except ValidationError as e:
                err = e.errors()[0]
                last_error = f"поле {'.'.join(map(str, err['loc']))}: {err['msg']}"
                prompt = f"{user}\n\nПредыдущий ответ не прошёл проверку ({last_error}). Верни строго JSON по схеме."
            except LLMError as e:
                last_error = str(e)
                break  # клиент уже делал повторы, сеть/модель недоступна
        self._log_call("llm_call", t0, schema=schema.__name__, attempts=attempt,
                       status="error", prompt=short(user, 200), error=last_error)
        raise AgentError(f"{self.name}: {last_error}")

    def _log_call(self, kind: str, t0: float, **data: Any) -> None:
        self.ctx.logger.log(kind, self.name, duration_ms=int((time.perf_counter() - t0) * 1000), **data)
