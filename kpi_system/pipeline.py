"""Сборка системы и запуск одного прогона."""
import time
import uuid
from datetime import datetime
from typing import Callable, Optional

import pandas as pd

from .agents import (AGENT_TITLES, AgentError, Decomposer, KPIBuilder, Orchestrator, PipelineError,
                     Reviewer, RunContext, StrategyAnalyst, TargetSetter)
from .config import Settings
from .llm import OllamaClient
from .logger import RunLogger
from .quality import quality_metrics
from .state import LimitExceeded, TaskState

STATUS_TITLES = {
    "approved": "✅ принят",
    "needs_attention": "⚠️ требует внимания",
    "needs_revision": "🔁 на доработке",
    "draft": "черновик",
}


def run_pipeline(document_path: str, request: str = "", settings: Optional[Settings] = None,
                 on_event: Optional[Callable[[dict], None]] = None) -> tuple[TaskState, RunLogger]:
    settings = settings or Settings()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]
    logger = RunLogger(run_id, on_event)
    state = TaskState(run_id=run_id, request=request, document_path=str(document_path),
                      max_steps=settings.max_steps, max_runtime_sec=settings.max_runtime_sec)
    ctx = RunContext(settings=settings, llm=OllamaClient(settings), logger=logger, state=state)

    orchestrator = Orchestrator(ctx, StrategyAnalyst(ctx), Decomposer(ctx), KPIBuilder(ctx),
                                TargetSetter(ctx), Reviewer(ctx))
    logger.log("run_start", "system", request=request, document=str(document_path), model=settings.model)
    try:
        orchestrator.run()
        state.status = "done"
    except LimitExceeded as e:
        state.status = "stopped_by_limit"
        state.errors.append(f"Остановлено защитой: {e}. Показаны частичные результаты.")
    except (PipelineError, AgentError) as e:
        state.status = "failed"
        state.errors.append(str(e))
    except Exception as e:  # непредвиденная ошибка — не теряем состояние и лог
        state.status = "failed"
        state.errors.append(f"Непредвиденная ошибка: {type(e).__name__}: {e}")
    finally:
        state.finished_at = time.time()
        state.metrics = quality_metrics(state, logger)
        state.save()
        logger.log("run_end", "system", status=state.status, steps=state.steps,
                   elapsed_sec=state.elapsed, errors=state.errors, metrics=state.metrics)
    return state, logger


def kpis_dataframe(state: TaskState) -> pd.DataFrame:
    goals = {g.id: g for g in state.goals}
    tasks = {t.id: t.title for t in state.tasks}
    rows = []
    for k in state.kpis:
        g = goals.get(k.goal_id)
        rows.append({
            "ID": k.id, "Направление": g.direction if g else "", "Цель": g.title if g else "",
            "Задача": tasks.get(k.task_id, ""), "KPI": k.name, "Формула": k.formula, "Ед.": k.unit,
            "Периодичность": k.periodicity, "База": k.baseline, "Год базы": k.baseline_year,
            "Цель (значение)": k.target, "Год цели": k.target_year, "Источник данных": k.data_source,
            "Обоснование": k.justification, "Статус": STATUS_TITLES.get(k.status, k.status),
            "SMART (S/M/A/R/T)": "/".join(str(v) for v in k.smart.values()) if k.smart else "",
            "Замечания": "; ".join(k.review_notes), "Доработок": k.revisions,
        })
    return pd.DataFrame(rows)


def load_dataframe(logger: RunLogger) -> pd.DataFrame:
    df = pd.DataFrame(logger.load_distribution())
    if not df.empty:
        df.insert(1, "Агент", df.agent.map(AGENT_TITLES).fillna(df.agent))
    return df
