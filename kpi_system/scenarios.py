"""Тестовые сценарии: загрузка, запуск и автоматическая проверка ожидаемого результата."""
import dataclasses
import time
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from .config import ROOT, RUNS_DIR, Settings
from .logger import RunLogger
from .pipeline import run_pipeline
from .schemas import normalize_direction
from .state import TaskState

SCENARIOS_FILE = ROOT / "tests" / "scenarios" / "scenarios.yaml"


def load_scenarios(path: Path = SCENARIOS_FILE) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------- проверки: имя → (функция(state, logger, ожидание) -> (ok, факт)) ----------
def _errors(state: TaskState) -> str:
    return " | ".join(state.errors)


def _kpis_consistent(state: TaskState) -> tuple[bool, str]:
    bad = []
    for k in state.kpis:
        if k.target is None or k.baseline is None:
            continue
        wrong_way = k.target < k.baseline if k.higher_is_better else k.target > k.baseline
        if wrong_way or (k.unit == "%" and k.target > 100):
            bad.append(k.id)
    return not bad, ", ".join(bad) or "все согласованы"


CHECKS: dict[str, Callable[[TaskState, RunLogger, Any], tuple[bool, Any]]] = {
    "status": lambda s, l, e: (s.status in e, s.status),
    "error_contains": lambda s, l, e: (e.lower() in _errors(s).lower(), _errors(s)[:200] or "нет ошибок"),
    "no_unexpected_error": lambda s, l, e: ("Непредвиденная" not in _errors(s), _errors(s)[:200] or "нет ошибок"),
    "min_goals": lambda s, l, e: (len(s.goals) >= e, len(s.goals)),
    "max_goals": lambda s, l, e: (len(s.goals) <= e, len(s.goals)),
    "min_kpis": lambda s, l, e: (len(s.kpis) >= e, len(s.kpis)),
    "max_kpis": lambda s, l, e: (len(s.kpis) <= e, len(s.kpis)),
    "focus_directions": lambda s, l, e: (
        set(e) <= {normalize_direction(d) for d in s.plan.get("focus_directions", [])},
        s.plan.get("focus_directions")),
    "goal_directions_subset": lambda s, l, e: (
        bool(s.goals) and {g.direction for g in s.goals} <= set(e), sorted({g.direction for g in s.goals})),
    "horizon_year": lambda s, l, e: (
        s.plan.get("horizon_year") == e and all(k.target_year == e for k in s.kpis),
        f"план {s.plan.get('horizon_year')}, KPI {sorted({k.target_year for k in s.kpis})}"),
    "kpi_fields_complete": lambda s, l, e: (
        all(k.name and k.formula and k.unit for k in s.kpis),
        f"{sum(bool(k.name and k.formula and k.unit) for k in s.kpis)}/{len(s.kpis)} заполнены"),
    "targets_consistent": lambda s, l, e: _kpis_consistent(s),
    "min_approved_share": lambda s, l, e: (s.metrics.get("approved_share", 0) >= e, s.metrics.get("approved_share")),
    "min_goal_coverage": lambda s, l, e: (s.metrics.get("goal_coverage", 0) >= e, s.metrics.get("goal_coverage")),
    "max_agent_share": lambda s, l, e: (s.metrics.get("max_agent_share", 1) <= e,
                                        f"{s.metrics.get('max_agent_share')} ({s.metrics.get('max_agent')})"),
    "max_steps": lambda s, l, e: (s.steps <= e, s.steps),
    "max_elapsed_sec": lambda s, l, e: (s.elapsed <= e, s.elapsed),
    "max_revisions": lambda s, l, e: (all(k.revisions <= e for k in s.kpis), max((k.revisions for k in s.kpis), default=0)),
    "kpi_statuses_subset": lambda s, l, e: ({k.status for k in s.kpis} <= set(e), sorted({k.status for k in s.kpis})),
    "state_saved": lambda s, l, e: ((RUNS_DIR / f"{s.run_id}.json").exists() and l.path.exists(), "runs/ и logs/ записаны"),
}


def evaluate(state: TaskState, logger: RunLogger, expect: dict) -> list[dict]:
    results = []
    for name, expected in expect.items():
        if name not in CHECKS:
            results.append({"check": name, "expected": expected, "actual": "неизвестная проверка", "ok": False})
            continue
        try:
            ok, actual = CHECKS[name](state, logger, expected)
        except Exception as e:
            ok, actual = False, f"ошибка проверки: {e}"
        results.append({"check": name, "expected": expected, "actual": actual, "ok": bool(ok)})
    return results


def run_scenario(sc: dict, base: Optional[Settings] = None,
                 on_event: Optional[Callable[[dict], None]] = None) -> dict:
    settings = dataclasses.replace(base or Settings(), **sc.get("settings", {}))
    t0 = time.time()
    state, logger = run_pipeline(str(ROOT / sc["doc"]), sc.get("request", ""), settings, on_event)
    checks = evaluate(state, logger, sc.get("expect", {}))
    return {
        "id": sc["id"],
        "title": sc["title"],
        "expected_result": " ".join(str(sc.get("expected_result", "")).split()),
        "passed": all(c["ok"] for c in checks),
        "checks": checks,
        "run_id": state.run_id,
        "status": state.status,
        "errors": state.errors,
        "metrics": state.metrics,
        "load": logger.load_distribution(),
        "wall_sec": round(time.time() - t0, 1),
        "log_path": str(logger.path),
        "typical": bool(sc.get("typical")),
    }
