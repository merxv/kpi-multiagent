"""Агент целевых значений: базовое и целевое значение по данным + обоснование."""
from ..schemas import JustificationOut
from ..tools import compute_target
from .base import AgentError, BaseAgent

SYSTEM = """Ты — аналитик данных университета. Кратко (1–2 предложения) обоснуй целевое значение KPI.
Если данных нет — предложи, как получить базовое значение.
Ответ строго JSON: {"justification": "..."}"""


class TargetSetter(BaseAgent):
    name = "target_setter"
    role = "Рассчитывает базовое и целевое значения KPI по фактическим данным"

    def register_tools(self):
        return {"compute_target": compute_target}

    def on_set_target(self, kpi: dict, horizon_year: int) -> dict:
        calc = None
        if kpi.get("metric_code"):
            try:
                calc = self.use_tool("compute_target", metric_code=kpi["metric_code"],
                                     horizon_year=horizon_year, higher_is_better=kpi["higher_is_better"])
            except AgentError as e:
                self.ctx.state.errors.append(f"{kpi['id']}: {e}")

        if calc:
            kpi.update(baseline=calc["baseline"], baseline_year=calc["baseline_year"],
                       target=calc["target"], target_year=horizon_year)
            user = (f"KPI: {kpi['name']} ({calc['unit']})\nИстория: {calc['history']}\n"
                    f"Средний годовой прирост: {calc['avg_annual_trend']}\n"
                    f"Цель на {horizon_year} год: {calc['target']}")
        else:
            kpi.update(baseline=None, baseline_year=None, target=None, target_year=horizon_year)
            user = f"KPI: {kpi['name']} ({kpi['unit']})\nФормула: {kpi['formula']}\nИсторических данных нет."

        kpi["justification"] = self.ask_llm(SYSTEM, user, JustificationOut).justification
        return {"kpi": kpi}
