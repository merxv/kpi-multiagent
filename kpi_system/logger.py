"""Журнал всех вызовов агентов и инструментов (JSONL) + подсчёт распределения нагрузки."""
import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Optional

from .config import LOGS_DIR

CALL_KINDS = ("llm_call", "tool_call")


def short(value: Any, limit: int = 300) -> Any:
    """Обрезает длинные значения, чтобы лог оставался читаемым."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


class RunLogger:
    def __init__(self, run_id: str, on_event: Optional[Callable[[dict], None]] = None):
        self.run_id = run_id
        self.path = LOGS_DIR / f"{run_id}.jsonl"
        self.events: list[dict] = []
        self.on_event = on_event

    def log(self, kind: str, agent: str, **data: Any) -> dict:
        event = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "kind": kind,
            "agent": agent,
            **data,
        }
        self.events.append(event)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass  # сбой интерфейса не должен ронять систему
        return event

    def load_distribution(self) -> list[dict]:
        """Доля вызовов LLM + инструментов на каждого агента (требование ≤ 40%)."""
        counts: dict[str, dict[str, int]] = defaultdict(lambda: {"llm": 0, "tool": 0})
        for e in self.events:
            if e["kind"] == "llm_call":
                counts[e["agent"]]["llm"] += 1
            elif e["kind"] == "tool_call":
                counts[e["agent"]]["tool"] += 1
        total = sum(c["llm"] + c["tool"] for c in counts.values()) or 1
        rows = []
        for agent, c in counts.items():
            n = c["llm"] + c["tool"]
            rows.append({"agent": agent, "llm_calls": c["llm"], "tool_calls": c["tool"],
                         "total": n, "share": round(n / total, 3)})
        return sorted(rows, key=lambda r: -r["total"])
