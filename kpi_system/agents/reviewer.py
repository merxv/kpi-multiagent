"""Проверяющий: контроль качества KPI (SMART, связь с целью, дубли)."""
from ..schemas import ReviewOut
from ..tools import check_kpi_formal, find_duplicates
from .base import AgentError, BaseAgent

SYSTEM = """Ты — проверяющий (контроль качества KPI университета).
Оцени KPI:
- relevant: действительно ли показатель измеряет выполнение задачи и цели;
- measurable: можно ли его однозначно посчитать по формуле.
comment — кратко, что исправить (пустая строка, если всё хорошо).
Ответ строго JSON: {"relevant": true, "measurable": true, "comment": ""}"""


class Reviewer(BaseAgent):
    name = "reviewer"
    role = "Проверяет KPI и возвращает на доработку"

    def register_tools(self):
        return {"check_kpi_formal": check_kpi_formal, "find_duplicates": find_duplicates}

    def on_review(self, kpis: list[dict], goals: dict, tasks: dict, all_kpis: list[dict]) -> dict:
        reviewed = []
        for kpi in kpis:
            formal = self.use_tool("check_kpi_formal", kpi=kpi)
            notes = list(formal["errors"])
            try:
                user = (f"Цель: {goals[kpi['goal_id']]}\nЗадача: {tasks[kpi['task_id']]}\n"
                        f"KPI: {kpi['name']}\nФормула: {kpi['formula']}\nЕдиница: {kpi['unit']}")
                verdict = self.ask_llm(SYSTEM, user, ReviewOut)
                if not (verdict.relevant and verdict.measurable):
                    notes.append(verdict.comment or "KPI слабо связан с задачей или неизмерим")
            except AgentError as e:
                formal["warnings"].append(f"Смысловая проверка не выполнена: {e}")

            kpi["review_notes"] = notes + formal["warnings"]
            kpi["status"] = "needs_revision" if notes else "approved"
            reviewed.append(kpi)

        # дубли ищем среди всех KPI: новый дубль отправляется на доработку
        ids = {k["id"] for k in reviewed}
        for d in self.use_tool("find_duplicates", kpis=all_kpis):
            target = next((k for k in reviewed if k["id"] == d["second"]), None) \
                or next((k for k in reviewed if k["id"] == d["first"]), None)
            if target and target["id"] in ids:
                other = d["first"] if target["id"] == d["second"] else d["second"]
                target["review_notes"].append(f"Дублирует {other} (сходство {d['similarity']}), нужен другой показатель")
                target["status"] = "needs_revision"
        return {"kpis": reviewed}
