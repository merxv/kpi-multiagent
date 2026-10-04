"""Аналитик стратегии: извлекает стратегические цели из документа."""
from difflib import SequenceMatcher

from ..schemas import DIRECTIONS, Goal, GoalsOut, normalize_direction
from ..tools import read_document, split_into_chunks
from .base import AgentError, BaseAgent

SYSTEM = f"""Ты — аналитик стратегии развития университета.
Из фрагмента стратегии выдели стратегические цели (не более 3).
Цель — желаемый результат развития вуза, а не отдельное мероприятие.
Если во фрагменте нет целей — верни пустой список.
direction — одно из: {", ".join(DIRECTIONS)}.
Ответ строго JSON:
{{"goals": [{{"title": "краткая формулировка цели", "direction": "...", "description": "одно предложение"}}]}}"""


class StrategyAnalyst(BaseAgent):
    name = "strategy_analyst"
    role = "Выделяет стратегические цели из документа стратегии"

    def register_tools(self):
        return {"read_document": read_document, "split_into_chunks": split_into_chunks}

    def on_extract_goals(self, document_path: str, max_goals: int, focus_directions: list[str]) -> dict:
        s = self.ctx.settings
        text = self.use_tool("read_document", path=document_path)
        chunks = self.use_tool("split_into_chunks", text=text, max_chars=s.chunk_chars, max_chunks=s.max_chunks)

        found: list[Goal] = []
        for i, chunk in enumerate(chunks, 1):
            try:
                out = self.ask_llm(SYSTEM, f"Фрагмент {i}/{len(chunks)}:\n{chunk}", GoalsOut)
            except AgentError as e:
                self.ctx.state.errors.append(f"Фрагмент {i} пропущен: {e}")
                continue
            for g in out.goals:
                if not g.title.strip() or self._is_duplicate(g.title, found):
                    continue
                found.append(Goal(id=f"G{len(found) + 1}", title=g.title.strip(),
                                  direction=normalize_direction(g.direction), description=g.description))

        focus = {normalize_direction(d) for d in focus_directions}
        if focus:
            focused = [g for g in found if g.direction in focus]
            found = focused or found  # если фильтр отсёк всё — оставляем все цели
        goals = found[:max_goals]
        for i, g in enumerate(goals, 1):
            g.id = f"G{i}"
        return {"goals": [g.model_dump() for g in goals]}

    @staticmethod
    def _is_duplicate(title: str, goals: list[Goal]) -> bool:
        return any(SequenceMatcher(None, title.lower(), g.title.lower()).ratio() > 0.75 for g in goals)
