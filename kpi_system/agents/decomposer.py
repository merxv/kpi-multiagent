"""Декомпозитор: разбивает стратегическую цель на измеримые задачи."""
from ..schemas import Goal, Task, TasksOut, normalize_direction
from .base import BaseAgent

SYSTEM = """Ты — специалист по стратегическому планированию в университете.
Разбей стратегическую цель на {n} конкретные задачи. Каждая задача должна быть
измерима одним количественным показателем и не повторять другие задачи.
Ответ строго JSON:
{{"tasks": [{{"title": "формулировка задачи", "direction": "направление"}}]}}"""


class Decomposer(BaseAgent):
    name = "decomposer"
    role = "Декомпозирует цели на измеримые задачи"

    def on_decompose(self, goal: dict, n_tasks: int) -> dict:
        g = Goal(**goal)
        user = f"Цель: {g.title}\nНаправление: {g.direction}\nОписание: {g.description}"
        out = self.ask_llm(SYSTEM.format(n=n_tasks), user, TasksOut)
        tasks = [
            Task(id=f"{g.id}.T{i}", goal_id=g.id, title=t.title.strip(),
                 direction=normalize_direction(t.direction) if t.direction else g.direction)
            for i, t in enumerate(out.tasks[:n_tasks], 1)
        ]
        return {"tasks": [t.model_dump() for t in tasks]}
