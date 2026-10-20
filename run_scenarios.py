"""Автопрогон тестовых сценариев с отчётом.

    python run_scenarios.py                 # все сценарии
    python run_scenarios.py --only S01,S08  # выбранные

Результат: reports/scenarios/latest.md (отчёт), latest.json (сырые данные),
history/<время>.json и reports/typical_run/ — логи типового сценария.
"""
import argparse
import json
import shutil
from datetime import datetime

from kpi_system import Settings
from kpi_system.agents import AGENT_TITLES
from kpi_system.config import ROOT, RUNS_DIR
from kpi_system.quality import METRIC_TITLES
from kpi_system.scenarios import load_scenarios, run_scenario

REPORTS = ROOT / "reports"
OUT_DIR = REPORTS / "scenarios"
TYPICAL_DIR = REPORTS / "typical_run"


def pct(v) -> str:
    return "—" if v is None else f"{v:.0%}"


def render_markdown(results: list[dict], settings: Settings, started: str) -> str:
    passed = sum(r["passed"] for r in results)
    lines = [
        "# Отчёт по тестовым сценариям",
        "",
        f"- Дата прогона: {started}",
        f"- Модель: `{settings.model}` ({settings.ollama_url})",
        f"- Сценариев: **{len(results)}**, пройдено: **{passed}** ({passed / len(results):.0%})",
        f"- Общее время: {sum(r['wall_sec'] for r in results):.0f} с",
        "",
        "## Сводка",
        "",
        "| ID | Сценарий | Результат | Статус | Целей | KPI | Принято | Макс. доля агента | Шагов | Время, с |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        m = r["metrics"]
        lines.append(f"| {r['id']} | {r['title']} | {'✅ пройден' if r['passed'] else '❌ не пройден'} | "
                     f"{r['status']} | {m.get('goals', 0)} | {m.get('kpis', 0)} | {pct(m.get('approved_share'))} | "
                     f"{pct(m.get('max_agent_share'))} | {m.get('steps', 0)} | {r['wall_sec']} |")

    lines += ["", "## Подробно", ""]
    for r in results:
        lines += [f"### {r['id']}. {r['title']} — {'✅' if r['passed'] else '❌'}", "",
                  f"**Ожидаемый результат:** {r['expected_result']}", "",
                  "| Проверка | Ожидалось | Фактически | |", "|---|---|---|---|"]
        for c in r["checks"]:
            actual = str(c["actual"]).replace("|", "/").replace("\n", " ")
            lines.append(f"| `{c['check']}` | {c['expected']} | {actual} | {'✅' if c['ok'] else '❌'} |")
        if r["errors"]:
            lines += ["", "Сообщения системы: " + "; ".join(e.replace("|", "/") for e in r["errors"])]
        lines += ["", f"Лог: `{r['log_path']}`", ""]

    ok_runs = [r for r in results if r["status"] == "done" and r["metrics"].get("kpis")]
    if ok_runs:
        lines += ["## Качество результатов (успешные прогоны с KPI)", "",
                  "| ID | " + " | ".join(METRIC_TITLES.values()) + " |",
                  "|---|" + "---|" * len(METRIC_TITLES)]
        for r in ok_runs:
            m = r["metrics"]
            cells = [str(m.get(k)) if k == "avg_smart" else pct(m.get(k)) for k in METRIC_TITLES]
            lines.append(f"| {r['id']} | " + " | ".join(cells) + " |")

    typical = next((r for r in results if r["typical"]), None)
    if typical and typical["load"]:
        lines += ["", f"## Распределение нагрузки — типовой сценарий {typical['id']}", "",
                  "| Агент | Вызовы LLM | Вызовы инструментов | Всего | Доля | ≤ 40% |", "|---|---|---|---|---|---|"]
        for row in typical["load"]:
            lines.append(f"| {AGENT_TITLES.get(row['agent'], row['agent'])} | {row['llm_calls']} | {row['tool_calls']} | "
                         f"{row['total']} | {row['share']:.1%} | {'✅' if row['share'] <= 0.4 else '❌'} |")
        lines += ["", "Полный лог: `reports/typical_run/run_log.jsonl`"]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Прогон тестовых сценариев")
    ap.add_argument("--only", help="ID сценариев через запятую, например S01,S08")
    args = ap.parse_args()

    scenarios = load_scenarios()
    if args.only:
        wanted = {s.strip().upper() for s in args.only.split(",")}
        scenarios = [s for s in scenarios if s["id"] in wanted]

    settings = Settings()
    started = datetime.now()
    results = []
    for i, sc in enumerate(scenarios, 1):
        print(f"[{i}/{len(scenarios)}] {sc['id']} {sc['title']} …", flush=True)
        r = run_scenario(sc, settings)
        results.append(r)
        mark = "ПРОЙДЕН" if r["passed"] else "НЕ ПРОЙДЕН"
        print(f"    {mark} · статус {r['status']} · KPI {r['metrics'].get('kpis', 0)} · {r['wall_sec']} с")
        for c in r["checks"]:
            if not c["ok"]:
                print(f"      ✗ {c['check']}: ожидалось {c['expected']}, фактически {c['actual']}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "history").mkdir(exist_ok=True)
    stamp = started.strftime("%Y%m%d_%H%M%S")
    payload = json.dumps({"started": started.isoformat(timespec="seconds"), "model": settings.model,
                          "results": results}, ensure_ascii=False, indent=2, default=str)
    (OUT_DIR / "history" / f"{stamp}.json").write_text(payload, encoding="utf-8")
    if not args.only:  # «последний отчёт» перезаписываем только полным прогоном
        (OUT_DIR / "latest.json").write_text(payload, encoding="utf-8")
        md = render_markdown(results, settings, started.strftime("%d.%m.%Y %H:%M"))
        (OUT_DIR / "latest.md").write_text(md, encoding="utf-8")

    typical = next((r for r in results if r["typical"] and r["passed"]), None)
    if typical:
        TYPICAL_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(typical["log_path"], TYPICAL_DIR / "run_log.jsonl")
        shutil.copy(RUNS_DIR / f"{typical['run_id']}.json", TYPICAL_DIR / "run_state.json")

    passed = sum(r["passed"] for r in results)
    print(f"\nИтог: пройдено {passed} из {len(results)} ({passed / max(len(results), 1):.0%})")
    if not args.only:
        print(f"Отчёт: {OUT_DIR / 'latest.md'}")


if __name__ == "__main__":
    main()
