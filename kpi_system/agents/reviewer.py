"""Проверяющий: контроль качества KPI (SMART, связь с целью, дубли)."""
from ..schemas import SMART_KEYS, ReviewOut
from ..tools import check_kpi_formal, find_duplicates
from .base import AgentError, BaseAgent

SYSTEM = """Ты — строгий проверяющий (контроль качества KPI университета).
Оцени KPI по критериям SMART целыми числами от 1 до 5:
- specific: конкретна ли формулировка показателя (1 — расплывчато, 5 — однозначно);
- measurable: можно ли однозначно посчитать значение по формуле;
- achievable: реалистично ли целевое значение относительно базового;
- relevant: насколько KPI измеряет выполнение именно этой задачи и цели;
- time_bound: задан ли срок и периодичность.
Не завышай оценки: 5 ставь только безупречному показателю.
comment — кратко, что исправить (пустая строка, если все оценки не ниже 3).
Ответ строго JSON:
{"specific": 4, "measurable": 4, "achievable": 4, "relevant": 4, "time_bound": 4, "comment": ""}"""

MIN_SCORE = 2.0   # оценка ≤ 2 по ключевому критерию — на доработку
MIN_MEAN = 3.0    # средняя оценка ниже 3 — на доработку


class Reviewer(BaseAgent):
    name = "reviewer"
    role = "Проверяет KPI и возвращает на доработку"

    def register_tools(self):
        return {"check_kpi_formal": check_kpi_formal, "find_duplicates": find_duplicates}

    def on_review(self, kpis: list[dict], goals: dict, tasks: dict, all_kpis: list[dict]) -> dict:
        reviewed = []
        for kpi in kpis:
            task_title = tasks[kpi["task_id"]]
            formal = self.use_tool("check_kpi_formal", kpi=kpi, task_title=task_title)
            notes = list(formal["errors"])
            try:
                values = (f"база {kpi['baseline']} ({kpi['baseline_year']}) → цель {kpi['target']} ({kpi['target_year']})"
                          if kpi.get("target") is not None else f"цель на {kpi['target_year']} год, данных нет")
                user = (f"Цель: {goals[kpi['goal_id']]}\nЗадача: {task_title}\n"
                        f"KPI: {kpi['name']}\nФормула: {kpi['formula']}\nЕдиница: {kpi['unit']}\n"
                        f"Периодичность: {kpi['periodicity']}\nЗначения: {values}")
                verdict = self.ask_llm(SYSTEM, user, ReviewOut)
                kpi["smart"] = verdict.scores()
                if min(verdict.relevant, verdict.measurable) <= MIN_SCORE or verdict.mean() < MIN_MEAN:
                    weak = ", ".join(k for k in SMART_KEYS if getattr(verdict, k) <= MIN_SCORE) or "средняя оценка"
                    notes.append(f"SMART: слабые критерии — {weak}. {verdict.comment}".strip())
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
