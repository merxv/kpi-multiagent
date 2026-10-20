"""Метрики качества результата одного прогона."""
from .logger import RunLogger
from .state import TaskState


def _share(part: int, whole: int) -> float:
    return round(part / whole, 3) if whole else 0.0


def quality_metrics(state: TaskState, logger: RunLogger) -> dict:
    kpis = state.kpis
    n = len(kpis)
    approved = [k for k in kpis if k.status == "approved"]
    covered_goals = {k.goal_id for k in approved}
    smart = [sum(k.smart.values()) / len(k.smart) for k in kpis if k.smart]
    load = logger.load_distribution()
    llm_calls = [e for e in logger.events if e["kind"] == "llm_call"]

    return {
        "goals": len(state.goals),
        "tasks": len(state.tasks),
        "kpis": n,
        # качество KPI
        "approved_share": _share(len(approved), n),
        "first_pass_share": _share(sum(k.revisions == 0 for k in approved), n),
        "data_linked_share": _share(sum(k.target is not None for k in kpis), n),
        "goal_coverage": _share(len(covered_goals), len(state.goals)),
        "avg_smart": round(sum(smart) / len(smart), 2) if smart else None,
        "revisions_total": sum(k.revisions for k in kpis),
        # работа системы
        "steps": state.steps,
        "elapsed_sec": state.elapsed,
        "llm_calls": len(llm_calls),
        "llm_retries": sum(e.get("attempts", 1) - 1 for e in llm_calls),
        "llm_errors": sum(e.get("status") == "error" for e in llm_calls),
        "max_agent_share": max((r["share"] for r in load), default=0.0),
        "max_agent": load[0]["agent"] if load else None,
        "errors": len(state.errors),
    }


METRIC_TITLES = {
    "approved_share": "Доля принятых KPI",
    "first_pass_share": "Принято с первого раза",
    "data_linked_share": "KPI с рассчитанной целью",
    "goal_coverage": "Покрытие целей",
    "avg_smart": "Средняя оценка SMART",
    "max_agent_share": "Макс. доля агента",
}
