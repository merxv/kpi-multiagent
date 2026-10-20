"""Запуск из командной строки:
    python main.py --doc data/sample_strategy.txt --request "KPI до 2030, акцент на науке"
"""
import argparse

from kpi_system import METRIC_TITLES, Settings, kpis_dataframe, load_dataframe, run_pipeline
from kpi_system.agents import AGENT_TITLES


def main() -> None:
    p = argparse.ArgumentParser(description="Формирование KPI на основе стратегии университета")
    p.add_argument("--doc", default="data/sample_strategy.txt", help="путь к документу стратегии")
    p.add_argument("--request", default="Сформируй KPI до 2030 года")
    p.add_argument("--max-goals", type=int)
    p.add_argument("--quiet", action="store_true", help="не печатать события")
    args = p.parse_args()

    settings = Settings()
    if args.max_goals:
        settings.max_goals = args.max_goals

    def on_event(e: dict) -> None:
        if e["kind"] in ("llm_call", "tool_call"):
            what = e.get("tool") or e.get("schema")
            print(f"  {AGENT_TITLES.get(e['agent'], e['agent']):<24} {e['kind']:<9} {what:<20} "
                  f"{e['status']} {e['duration_ms']} мс")

    state, logger = run_pipeline(args.doc, args.request, settings, None if args.quiet else on_event)

    print(f"\nСтатус: {state.status} | шагов: {state.steps} | время: {state.elapsed} с")
    for err in state.errors:
        print("  ! " + err)
    df = kpis_dataframe(state)
    if not df.empty:
        print("\n" + df[["ID", "KPI", "Ед.", "База", "Цель (значение)", "Статус"]].to_string(index=False))
    print("\nРаспределение нагрузки:")
    print(load_dataframe(logger)[["Агент", "llm_calls", "tool_calls", "total", "share"]].to_string(index=False))
    print(f"\nЛог: {logger.path}\nСостояние: runs/{state.run_id}.json")


if __name__ == "__main__":
    main()
