"""Настройки системы. Значения берутся из .env (см. .env.example), ключи в коде не хранятся."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
RUNS_DIR = ROOT / "runs"

load_dotenv(ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:7b"))
    temperature: float = field(default_factory=lambda: float(_env("LLM_TEMPERATURE", "0.2")))
    llm_timeout: int = field(default_factory=lambda: int(_env("LLM_TIMEOUT", "180")))
    llm_retries: int = field(default_factory=lambda: int(_env("LLM_RETRIES", "2")))

    # Защита от зацикливания и бесконечной работы
    max_steps: int = field(default_factory=lambda: int(_env("MAX_STEPS", "150")))
    max_runtime_sec: int = field(default_factory=lambda: int(_env("MAX_RUNTIME_SEC", "1200")))
    max_revisions: int = field(default_factory=lambda: int(_env("MAX_REVISIONS", "1")))

    # Размер задачи
    max_goals: int = field(default_factory=lambda: int(_env("MAX_GOALS", "4")))
    tasks_per_goal: int = field(default_factory=lambda: int(_env("TASKS_PER_GOAL", "2")))
    chunk_chars: int = field(default_factory=lambda: int(_env("CHUNK_CHARS", "2500")))
    max_chunks: int = field(default_factory=lambda: int(_env("MAX_CHUNKS", "6")))


for _d in (LOGS_DIR, RUNS_DIR):
    _d.mkdir(exist_ok=True)
