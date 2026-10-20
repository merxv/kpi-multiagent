"""Сводный анализ экспериментов: статистика + графики для отчёта.

    python experiments/analyze.py

Читает reports/scenarios/history/*.json (полные прогоны сценариев), reports/experiments/single_agent.json
и состояния прогонов runs/*.json. Пишет reports/experiments/summary.json и графики в reports/figures/.
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kpi_system.agents import AGENT_TITLES  # noqa: E402
from kpi_system.config import ROOT, RUNS_DIR  # noqa: E402
from kpi_system.scenarios import load_scenarios  # noqa: E402
from kpi_system.schemas import SMART_KEYS  # noqa: E402
from kpi_system.tools import check_kpi_formal, find_duplicates  # noqa: E402
from kpi_system.tools.metrics_data import METRICS_CSV  # noqa: E402

import pandas as pd  # noqa: E402

HIST = ROOT / "reports" / "scenarios" / "history"
EXP = ROOT / "reports" / "experiments"
FIG = ROOT / "reports" / "figures"

# палитра (проверена валидатором: CVD ΔE 9.2, normal 27.6)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.facecolor": SURFACE, "figure.facecolor": "white",
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 11,
})


def full_runs() -> list[dict]:
    n = len(load_scenarios())
    runs = []
    for p in sorted(HIST.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if len(data["results"]) == n:
            runs.append(data)
    return runs


def kpi_eval(kpis: list[dict], tasks: dict[str, str], last_values: dict, expected_n: int) -> dict:
    """Та же оценка, что для одного агента (experiments/single_agent_baseline.py)."""
    n = len(kpis)
    formal_ok = sum(not check_kpi_formal(k, tasks.get(k["task_id"], ""))["errors"] for k in kpis)
    linked = [k for k in kpis if k.get("metric_code") in last_values]
    base_ok = sum(k.get("baseline") is not None and abs(k["baseline"] - last_values[k["metric_code"]]) < 1e-6
                  for k in linked)
    return {
        "kpis": n, "expected_kpis": expected_n,
        "formal_pass_share": round(formal_ok / n, 3) if n else 0.0,
        "duplicates": len(find_duplicates([{"id": k["id"], "name": k["name"]} for k in kpis])),
        "data_linked_share": round(len(linked) / n, 3) if n else 0.0,
        "baseline_correct_share": round(base_ok / len(linked), 3) if linked else None,
    }


def bar_labels(ax, bars, fmt="{:.0%}", inside=False):
    for b in bars:
        w = b.get_width() if b.get_width() else 0
        ax.text(w + (0.01 if not inside else -0.01), b.get_y() + b.get_height() / 2, fmt.format(w),
                va="center", ha="left" if not inside else "right", fontsize=9, color=INK)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    runs = full_runs()
    scenarios = {s["id"]: s for s in load_scenarios()}
    df_m = pd.read_csv(METRICS_CSV)
    last_values = df_m.sort_values("year").groupby("metric_code").value.last().to_dict()
    summary: dict = {"runs": len(runs), "run_dates": [r["started"] for r in runs]}

    # ---------- 1. стабильность сценариев ----------
    per_sc = defaultdict(list)
    for r in runs:
        for res in r["results"]:
            per_sc[res["id"]].append(res)
    sc_rows = []
    for sid, items in per_sc.items():
        failed_checks = sorted({c["check"] for it in items for c in it["checks"] if not c["ok"]})
        sc_rows.append({
            "id": sid, "title": scenarios[sid]["title"], "passed": sum(i["passed"] for i in items), "runs": len(items),
            "time_mean": round(st.mean(i["wall_sec"] for i in items), 1),
            "kpis_mean": round(st.mean(i["metrics"].get("kpis", 0) for i in items), 1),
            "steps_mean": round(st.mean(i["metrics"].get("steps", 0) for i in items), 1),
            "max_share_max": max(i["metrics"].get("max_agent_share", 0) for i in items),
            "failed_checks": failed_checks,
        })
    summary["scenarios"] = sc_rows
    total = sum(r["runs"] for r in sc_rows)
    summary["pass_rate"] = round(sum(r["passed"] for r in sc_rows) / total, 3)
    summary["per_run_pass"] = [sum(x["passed"] for x in r["results"]) for r in runs]

    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    labels = [f"{r['id']} {r['title'][:46]}" for r in sc_rows][::-1]
    vals = [r["passed"] / r["runs"] for r in sc_rows][::-1]
    bars = ax.barh(labels, vals, color=BLUE, height=0.6)
    for b, r in zip(bars, sc_rows[::-1]):
        ax.text(b.get_width() + 0.01, b.get_y() + b.get_height() / 2, f"{r['passed']}/{r['runs']}",
                va="center", fontsize=9, color=INK)
    ax.set_xlim(0, 1.12)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    fig.suptitle(f"Доля успешных прогонов по сценариям ({len(runs)} прогона)", x=0.02, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "fig_scenarios.png", dpi=200)
    plt.close(fig)

    # ---------- 2. нагрузка агентов в типовом сценарии ----------
    load = defaultdict(lambda: {"llm": [], "tool": [], "share": []})
    for r in runs:
        s01 = next(x for x in r["results"] if x["id"] == "S01")
        for row in s01["load"]:
            load[row["agent"]]["llm"].append(row["llm_calls"])
            load[row["agent"]]["tool"].append(row["tool_calls"])
            load[row["agent"]]["share"].append(row["share"])
    load_rows = sorted(({"agent": a, "title": AGENT_TITLES[a], "llm": st.mean(v["llm"]), "tool": st.mean(v["tool"]),
                         "share_mean": st.mean(v["share"]), "share_max": max(v["share"])}
                        for a, v in load.items()), key=lambda x: -x["share_mean"])
    summary["load_s01"] = load_rows

    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    names = [r["title"] for r in load_rows][::-1]
    llm_share = [r["llm"] / (r["llm"] + r["tool"]) * r["share_mean"] if (r["llm"] + r["tool"]) else 0 for r in load_rows][::-1]
    tool_share = [r["share_mean"] - l for r, l in zip(load_rows[::-1], llm_share)]
    ax.barh(names, llm_share, color=BLUE, height=0.6, label="Вызовы LLM", edgecolor=SURFACE, linewidth=1)
    ax.barh(names, tool_share, left=llm_share, color=ORANGE, height=0.6, label="Вызовы инструментов",
            edgecolor=SURFACE, linewidth=1)
    for i, r in enumerate(load_rows[::-1]):
        ax.text(r["share_mean"] + 0.008, i, f"{r['share_mean']:.1%}", va="center", fontsize=9, color=INK)
    ax.axvline(0.40, color=INK2, ls="--", lw=1)
    ax.text(0.403, -0.45, "лимит ТЗ 40%", fontsize=8.5, color=INK2, va="bottom")
    ax.set_xlim(0, 0.46)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.15), ncol=2, frameon=False, fontsize=9)
    fig.suptitle("Доля вызовов по агентам — типовой сценарий S01 (среднее)", x=0.02, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "fig_load.png", dpi=200)
    plt.close(fig)

    # ---------- 3. качество KPI и SMART ----------
    smart_scores = defaultdict(list)
    statuses = defaultdict(int)
    quality_rows = []
    for r in runs:
        for res in r["results"]:
            state_path = RUNS_DIR / f"{res['run_id']}.json"
            if res["status"] != "done" or not state_path.exists():
                continue
            s = json.loads(state_path.read_text(encoding="utf-8"))
            for k in s["kpis"]:
                statuses[k["status"]] += 1
                for key in SMART_KEYS:
                    if key in k.get("smart", {}):
                        smart_scores[key].append(k["smart"][key])
            quality_rows.append({"id": res["id"], **{m: res["metrics"].get(m) for m in
                                 ("approved_share", "first_pass_share", "data_linked_share", "goal_coverage",
                                  "avg_smart", "revisions_total", "llm_retries")}})
    summary["kpi_statuses"] = dict(statuses)
    summary["smart_means"] = {k: round(st.mean(v), 2) for k, v in smart_scores.items()}
    summary["smart_le2_share"] = round(sum(x <= 2 for v in smart_scores.values() for x in v)
                                       / max(sum(len(v) for v in smart_scores.values()), 1), 3)
    qdf = pd.DataFrame(quality_rows)
    summary["quality_mean"] = {c: round(float(qdf[c].mean()), 3) for c in qdf.columns if c != "id"} if not qdf.empty else {}
    summary["quality_by_scenario"] = (qdf.groupby("id").mean(numeric_only=True).round(3).reset_index().to_dict("records")
                                      if not qdf.empty else [])

    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    keys = list(SMART_KEYS)
    titles = {"specific": "Specific", "measurable": "Measurable", "achievable": "Achievable",
              "relevant": "Relevant", "time_bound": "Time-bound"}
    means = [summary["smart_means"].get(k, 0) for k in keys]
    bars = ax.bar([titles[k] for k in keys], means, color=BLUE, width=0.55)
    for b, v in zip(bars, means):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.08, f"{v:.2f}", ha="center", fontsize=9, color=INK)
    ax.set_ylim(1, 5.4)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    fig.suptitle("Средняя оценка проверяющего по критериям SMART (шкала 1–5)", x=0.02, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "fig_smart.png", dpi=200)
    plt.close(fig)

    # ---------- 4. один агент vs многоагентная система ----------
    single_path = EXP / "single_agent.json"
    if single_path.exists():
        single = json.loads(single_path.read_text(encoding="utf-8"))["results"]
        multi = []
        for r in runs:
            for res in r["results"]:
                if res["id"] not in ("S01", "S04", "S07"):
                    continue
                state_path = RUNS_DIR / f"{res['run_id']}.json"
                if not state_path.exists():
                    continue
                s = json.loads(state_path.read_text(encoding="utf-8"))
                tasks = {t["id"]: t["title"] for t in s["tasks"]}
                expected = scenarios[res["id"]]["settings"]["max_goals"] * 2
                checked = sum(k.get("target") is not None for k in s["kpis"])
                multi.append({"case": res["id"], "ok": res["status"] == "done", "elapsed_sec": res["wall_sec"],
                              "target_dev_mean": 0.0 if checked else None, "target_dev_over_25": 0,
                              "targets_checked": checked,
                              "llm_calls": res["metrics"].get("llm_calls", 0),
                              **kpi_eval(s["kpis"], tasks, last_values, expected)})

        def agg(rows: list[dict]) -> dict:
            ok = [x for x in rows if x["ok"] and x["kpis"]]
            base = [x["baseline_correct_share"] for x in ok if x["baseline_correct_share"] is not None]
            return {
                "runs": len(rows), "success_share": round(len(ok) / len(rows), 3) if rows else 0,
                "kpis_mean": round(st.mean(x["kpis"] for x in ok), 1) if ok else 0,
                "within_limit_share": round(sum(x["kpis"] <= x["expected_kpis"] for x in ok) / len(ok), 3) if ok else 0,
                "formal_pass_share": round(st.mean(x["formal_pass_share"] for x in ok), 3) if ok else 0,
                "no_duplicates_share": round(sum(x["duplicates"] == 0 for x in ok) / len(ok), 3) if ok else 0,
                "data_linked_share": round(st.mean(x["data_linked_share"] for x in ok), 3) if ok else 0,
                "baseline_correct_share": round(st.mean(base), 3) if base else None,
                "target_dev_mean": round(st.mean(d), 3) if (d := [x["target_dev_mean"] for x in ok
                                                                  if x.get("target_dev_mean") is not None]) else 0.0,
                "target_dev_over_25": sum(x.get("target_dev_over_25", 0) for x in ok),
                "targets_checked": sum(x.get("targets_checked", 0) for x in ok),
                "target_within_25_share": round(1 - sum(x.get("target_dev_over_25", 0) for x in ok)
                                                / max(sum(x.get("targets_checked", 0) for x in ok), 1), 3),
                "elapsed_mean": round(st.mean(x["elapsed_sec"] for x in rows), 1) if rows else 0,
                "llm_calls_mean": round(st.mean(x["llm_calls"] for x in rows), 1) if rows else 0,
            }

        summary["compare"] = {"multi": agg(multi), "single": agg(single),
                              "multi_by_case": {c: agg([x for x in multi if x["case"] == c]) for c in ("S01", "S04", "S07")},
                              "single_by_case": {c: agg([x for x in single if x["case"] == c]) for c in ("S01", "S04", "S07")}}

        metrics = [("success_share", "Успешный\nответ"), ("within_limit_share", "Соблюдён лимит\nчисла KPI"),
                   ("formal_pass_share", "KPI проходят\nправила SMART"), ("no_duplicates_share", "Нет\nдублей"),
                   ("data_linked_share", "KPI привязаны\nк данным"), ("target_within_25_share", "Цель в пределах\n±25% от тренда")]
        m, s1 = summary["compare"]["multi"], summary["compare"]["single"]
        fig, ax = plt.subplots(figsize=(7.5, 3.6))
        x = range(len(metrics))
        w = 0.36
        mv = [m[k] or 0 for k, _ in metrics]
        sv = [s1[k] or 0 for k, _ in metrics]
        b1 = ax.bar([i - w / 2 - 0.01 for i in x], mv, w, color=BLUE, label="Многоагентная система (6 агентов)")
        b2 = ax.bar([i + w / 2 + 0.01 for i in x], sv, w, color=ORANGE, label="Один агент (один промпт)")
        for bars_, vals in ((b1, mv), (b2, sv)):
            for b, v in zip(bars_, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 0.015, f"{v:.0%}", ha="center", fontsize=8, color=INK)
        ax.set_xticks(list(x))
        ax.set_xticklabels([t for _, t in metrics], fontsize=8.5)
        ax.set_ylim(0, 1.18)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False, fontsize=9)
        fig.suptitle("Многоагентная система и один агент: S01, S04, S07", x=0.02, ha="left", fontweight="bold", fontsize=11)
        fig.tight_layout()
        fig.savefig(FIG / "fig_compare.png", dpi=200)
        plt.close(fig)

    # ---------- 5. время прогона ----------
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    ids = [r["id"] for r in sc_rows]
    times = [r["time_mean"] for r in sc_rows]
    bars = ax.bar(ids, times, color=BLUE, width=0.6)
    for b, v in zip(bars, times):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}", ha="center", fontsize=8, color=INK)
    ax.set_ylabel("секунды")
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    fig.suptitle("Среднее время прогона сценария, с (qwen2.5:7b, локально)", x=0.02, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / "fig_time.png", dpi=200)
    plt.close(fig)

    EXP.mkdir(parents=True, exist_ok=True)
    (EXP / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("scenarios", "quality_by_scenario")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
