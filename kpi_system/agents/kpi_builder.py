"""Конструктор KPI: формулирует показатель для задачи с опорой на справочник."""
import json

from ..schemas import KPI, KPIOut, PERIODICITY
from ..tools import list_metrics, search_kpi_library
from .base import BaseAgent

SYSTEM = f"""Ты — конструктор KPI для университета.
Сформулируй ОДИН измеримый ключевой показатель (KPI) для задачи.
Можешь взять подходящий показатель из справочника или сформулировать свой.
metric_code — код из списка «Доступные данные», только если показатель совпадает по смыслу, иначе null.
higher_is_better — true, если рост значения — это хорошо.
periodicity — одно из: {", ".join(PERIODICITY)}.
Ответ строго JSON:
{{"name": "...", "formula": "как считать", "unit": "%, шт, млн руб, балл ...",
"periodicity": "год", "data_source": "откуда брать данные", "metric_code": null, "higher_is_better": true}}"""


class KPIBuilder(BaseAgent):
    name = "kpi_builder"
    role = "Формулирует KPI: название, формула, единица, периодичность, источник"

    def register_tools(self):
        return {"search_kpi_library": search_kpi_library, "list_metrics": list_metrics}

    def __init__(self, ctx):
        super().__init__(ctx)
        self._metrics: list[dict] | None = None

    def _available_metrics(self) -> list[dict]:
        if self._metrics is None:  # справочник данных запрашиваем один раз за прогон
            self._metrics = self.use_tool("list_metrics")
        return self._metrics

    def on_build_kpi(self, task: dict, goal: dict, kpi_id: str, notes: list[str] | None = None,
                     previous: dict | None = None) -> dict:
        metrics = self._available_metrics()
        library = self.use_tool("search_kpi_library", query=task["title"], direction=task["direction"])

        lib_text = "\n".join(f"- {k['name']} ({k['unit']}); формула: {k['formula']}; metric_code: {k['metric_code'] or 'null'}"
                             for k in library) or "- нет подходящих"
        data_text = "\n".join(f"- {m['metric_code']}: {m['metric_name']} ({m['unit']})" for m in metrics)
        user = (f"Цель: {goal['title']}\nЗадача: {task['title']}\n\n"
                f"Справочник типовых KPI:\n{lib_text}\n\nДоступные данные:\n{data_text}")
        if notes:
            user += (f"\n\nПредыдущий вариант KPI: {json.dumps(previous, ensure_ascii=False)}\n"
                     f"Замечания проверяющего: {'; '.join(notes)}\nИсправь KPI с учётом замечаний.")

        out = self.ask_llm(SYSTEM, user, KPIOut)
        known = {m["metric_code"] for m in metrics}
        kpi = KPI(id=kpi_id, task_id=task["id"], goal_id=goal["id"], **out.model_dump())
        if kpi.metric_code not in known:
            kpi.metric_code = None
        return {"kpi": kpi.model_dump()}
