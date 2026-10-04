"""Явное состояние задачи: хранится в памяти и сохраняется в runs/<run_id>.json."""
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from .config import RUNS_DIR
from .schemas import KPI, AgentMessage, Goal, Task


class LimitExceeded(Exception):
    """Превышен лимит шагов или времени — защита от зацикливания."""


class TaskState(BaseModel):
    run_id: str
    request: str
    document_path: str
    status: str = "created"
    plan: dict[str, Any] = {}
    goals: list[Goal] = []
    tasks: list[Task] = []
    kpis: list[KPI] = []
    messages: list[AgentMessage] = []
    errors: list[str] = []
    steps: int = 0
    max_steps: int
    max_runtime_sec: int
    started_at: float = Field(default_factory=time.time)
    finished_at: Optional[float] = None

    def tick(self) -> None:
        """Вызывается перед каждым обращением к LLM или инструменту."""
        self.steps += 1
        if self.steps > self.max_steps:
            raise LimitExceeded(f"Превышен лимит шагов ({self.max_steps})")
        elapsed = time.time() - self.started_at
        if elapsed > self.max_runtime_sec:
            raise LimitExceeded(f"Превышен лимит времени ({self.max_runtime_sec} с)")

    @property
    def elapsed(self) -> float:
        return round((self.finished_at or time.time()) - self.started_at, 1)

    def save(self) -> None:
        (RUNS_DIR / f"{self.run_id}.json").write_text(self.model_dump_json(indent=2), encoding="utf-8")
