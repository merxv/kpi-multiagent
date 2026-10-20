"""Эксперимент: один агент (один промпт) против многоагентной системы.

Один агент получает тот же документ и те же данные (список метрик с историей), что и команда агентов,
но решает всю задачу одним запросом без инструментов и без проверяющего. Результат оценивается
теми же правилами, что и в многоагентной системе.

    python experiments/single_agent_baseline.py --runs 3
"""
import argparse
import json
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kpi_system import Settings  # noqa: E402
from kpi_system.config import ROOT  # noqa: E402
from kpi_system.llm import LLMError, OllamaClient  # noqa: E402
from kpi_system.tools import check_kpi_formal, compute_target, find_duplicates, read_document  # noqa: E402
from kpi_system.tools.metrics_data import METRICS_CSV  # noqa: E402

OUT = ROOT / "reports" / "experiments" / "single_agent.json"

# те же документы и размер задачи, что в сценариях S01, S04, S07
CASES = [
    {"id": "S01", "doc": "data/sample_strategy.txt", "max_goals": 4},
    {"id": "S04", "doc": "data/test_docs/single_goal.txt", "max_goals": 4},
    {"id": "S07", "doc": "data/test_docs/vague_strategy.txt", "max_goals": 3},
]
TASKS_PER_GOAL, HORIZON = 2, 2030

SYSTEM = """Ты — эксперт по стратегическому планированию университета.
По тексту стратегии сформируй систему KPI:
1) выдели стратегические цели (не более {max_goals});
2) для каждой цели сформулируй {n} задачи;
3) для каждой задачи — ОДИН измеримый KPI: название-показатель («Доля …», «Число …»), формула расчёта,
   единица, периодичность (год|полугодие|квартал|месяц), источник данных;
4) если KPI совпадает с одной из доступных метрик — укажи её metric_code, возьми базовое значение
   за последний год из истории и рассчитай целевое значение на {year} год; иначе metric_code, baseline и target = null.
Ответ строго JSON:
{{"kpis": [{{"goal": "...", "task": "...", "name": "...", "formula": "...", "unit": "...",
"periodicity": "год", "data_source": "...", "metric_code": null, "baseline": null, "target": null,
"higher_is_better": true}}]}}"""


def metrics_text(df: pd.DataFrame) -> str:
    rows = []
    for code, g in df.groupby("metric_code", sort=False):
        hist = ", ".join(f"{int(y)}: {v:g}" for y, v in zip(g.year, g.value))
        rows.append(f"- {code}: {g.metric_name.iloc[0]} ({g.unit.iloc[0]}); {hist}")
    return "\n".join(rows)


def evaluate(kpis: list[dict], last_values: dict[str, float], expected_n: int) -> dict:
    """Те же правила, что у проверяющего, + сверка базовых значений с фактическими данными."""
    n = len(kpis)
    formal_ok = sum(not check_kpi_formal(k, k.get("task", ""))["errors"] for k in kpis)
    named = [{"id": str(i), "name": k.get("name", "")} for i, k in enumerate(kpis)]
    linked = [k for k in kpis if k.get("metric_code") in last_values]
    base_ok = sum(isinstance(k.get("baseline"), (int, float)) and abs(k["baseline"] - last_values[k["metric_code"]]) < 1e-6
                  for k in linked)
    with_target = [k for k in kpis if isinstance(k.get("target"), (int, float))]
    consistent = sum(
        not isinstance(k.get("baseline"), (int, float))
        or ((k["target"] >= k["baseline"]) if k.get("higher_is_better", True) else (k["target"] <= k["baseline"]))
        for k in with_target)
    unlinked_numbers = sum(isinstance(k.get("baseline"), (int, float)) for k in kpis if k not in linked)
    return {
        "kpis": n,
        "expected_kpis": expected_n,
        "formal_pass_share": round(formal_ok / n, 3) if n else 0.0,
        "duplicates": len(find_duplicates(named)),
        "data_linked_share": round(len(linked) / n, 3) if n else 0.0,
        "baseline_correct_share": round(base_ok / len(linked), 3) if linked else None,
        "target_consistent_share": round(consistent / len(with_target), 3) if with_target else None,
        "invented_baselines": unlinked_numbers,  # числа «из ниоткуда» у KPI без данных
    }


def target_realism(kpis: list[dict], last_values: dict) -> dict:
    """Насколько цель отклоняется от трендовой оценки по фактическим данным (как считает агент целевых значений)."""
    devs = []
    for k in kpis:
        if k.get("metric_code") in last_values and isinstance(k.get("target"), (int, float)):
            ref = compute_target(k["metric_code"], HORIZON, bool(k.get("higher_is_better", True)))["target"]
            if ref:
                devs.append(abs(k["target"] - ref) / ref)
    return {"target_dev_mean": round(sum(devs) / len(devs), 3) if devs else None,
            "target_dev_over_25": sum(d > 0.25 for d in devs), "targets_checked": len(devs)}


def run_case(client: OllamaClient, case: dict, metrics: str, last_values: dict) -> dict:
    text = read_document(str(ROOT / case["doc"]))
    system = SYSTEM.format(max_goals=case["max_goals"], n=TASKS_PER_GOAL, year=HORIZON)
    user = f"Стратегия:\n{text}\n\nДоступные метрики (код: название; история значений):\n{metrics}"
    t0 = time.time()
    try:
        raw = client.chat_json(system, user)
        kpis = raw.get("kpis", [])
        if not isinstance(kpis, list):
            raise ValueError("поле kpis не является списком")
        kpis = [k for k in kpis if isinstance(k, dict)]
        ok, error = True, ""
    except (LLMError, ValueError, AttributeError) as e:
        kpis, ok, error = [], False, str(e)
    result = {"case": case["id"], "ok": ok, "error": error, "elapsed_sec": round(time.time() - t0, 1),
              "llm_calls": 1, **evaluate(kpis, last_values, case["max_goals"] * TASKS_PER_GOAL)}
    result.update(target_realism(kpis, last_values))
    result["kpis_list"] = kpis
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()

    settings = Settings()
    client = OllamaClient(settings)
    df = pd.read_csv(METRICS_CSV)
    last_values = df.sort_values("year").groupby("metric_code").value.last().to_dict()
    metrics = metrics_text(df)

    results = []
    for run in range(1, args.runs + 1):
        for case in CASES:
            r = run_case(client, case, metrics, last_values)
            r["run"] = run
            results.append(r)
            print(f"run {run} {case['id']}: ok={r['ok']} KPI={r['kpis']} formal={r['formal_pass_share']} "
                  f"dups={r['duplicates']} base_ok={r['baseline_correct_share']} {r['elapsed_sec']} с", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"model": settings.model, "results": results}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"Сохранено: {OUT}")


if __name__ == "__main__":
    main()
