"""Веб-интерфейс: streamlit run app.py"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from kpi_system import METRIC_TITLES, Settings, kpis_dataframe, load_dataframe, run_pipeline
from kpi_system.agents import AGENT_TITLES
from kpi_system.config import DATA_DIR, RUNS_DIR
from kpi_system.llm import OllamaClient
from kpi_system.scenarios import load_scenarios, run_scenario

SAMPLE = DATA_DIR / "sample_strategy.txt"
UPLOADS = RUNS_DIR / "uploads"
LOAD_LIMIT = 0.40
SCENARIO_REPORT = Path(__file__).parent / "reports" / "scenarios" / "latest.json"

st.set_page_config(page_title="KPI из стратегии вуза", page_icon="🎯", layout="wide")
st.title("🎯 Формирование KPI на основе стратегии университета")
st.caption("Многоагентная система: оркестратор → аналитик стратегии → декомпозитор → конструктор KPI → "
           "агент целевых значений → проверяющий")

# ---------------- Настройки ----------------
with st.sidebar:
    section = st.radio("📂 Раздел", ["🚀 Прогон", "🧪 Тестовые сценарии"])
    st.header("⚙️ Модель")
    defaults = Settings()
    url = st.text_input("Ollama URL", defaults.ollama_url)
    model = st.text_input("Модель", defaults.model)
    if st.button("Проверить подключение"):
        ok, msg = OllamaClient(Settings(ollama_url=url, model=model)).ping()
        (st.success if ok else st.error)(msg)

    st.header("📏 Размер задачи")
    max_goals = st.slider("Максимум целей", 1, 8, defaults.max_goals)
    tasks_per_goal = st.slider("Задач на цель", 1, 4, defaults.tasks_per_goal)

    st.header("🛡️ Лимиты")
    max_steps = st.number_input("Лимит шагов (вызовов)", 10, 500, defaults.max_steps)
    max_runtime = st.number_input("Лимит времени, с", 60, 7200, defaults.max_runtime_sec)
    max_revisions = st.slider("Кругов доработки", 0, 3, defaults.max_revisions)

settings = Settings(ollama_url=url, model=model, max_goals=max_goals, tasks_per_goal=tasks_per_goal,
                    max_steps=int(max_steps), max_runtime_sec=int(max_runtime), max_revisions=max_revisions)


def show_scenario_results(results: list[dict]) -> None:
    passed = sum(r["passed"] for r in results)
    c = st.columns(3)
    c[0].metric("Сценариев", len(results))
    c[1].metric("Пройдено", f"{passed} из {len(results)}")
    c[2].metric("Доля успеха", f"{passed / max(len(results), 1):.0%}")
    st.dataframe(pd.DataFrame([{
        "ID": r["id"], "Сценарий": r["title"], "Результат": "✅" if r["passed"] else "❌",
        "Статус": r["status"], "Целей": r["metrics"].get("goals", 0), "KPI": r["metrics"].get("kpis", 0),
        "Макс. доля агента": f"{r['metrics'].get('max_agent_share', 0):.0%}",
        "Шагов": r["metrics"].get("steps", 0), "Время, с": r["wall_sec"],
    } for r in results]), use_container_width=True, hide_index=True)
    for r in results:
        with st.expander(f"{'✅' if r['passed'] else '❌'} {r['id']}. {r['title']}"):
            st.markdown(f"**Ожидаемый результат:** {r['expected_result']}")
            st.dataframe(pd.DataFrame([{"Проверка": ch["check"], "Ожидалось": str(ch["expected"]),
                                        "Фактически": str(ch["actual"]), "": "✅" if ch["ok"] else "❌"}
                                       for ch in r["checks"]]), use_container_width=True, hide_index=True)
            for e in r["errors"]:
                st.caption(f"Сообщение системы: {e}")


if section == "🧪 Тестовые сценарии":
    st.subheader("🧪 Тестовые сценарии")
    scenarios = load_scenarios()
    st.caption(f"{len(scenarios)} сценариев в tests/scenarios/scenarios.yaml. "
               "Полный прогон с отчётом: `python run_scenarios.py`")
    chosen = st.multiselect("Запустить сценарии", [f"{s['id']} · {s['title']}" for s in scenarios])
    if st.button("▶️ Запустить выбранные", disabled=not chosen):
        ids = {c.split(" · ")[0] for c in chosen}
        results, bar = [], st.progress(0.0)
        for i, sc in enumerate(s for s in scenarios if s["id"] in ids):
            with st.spinner(f"{sc['id']} {sc['title']}…"):
                results.append(run_scenario(sc, settings))
            bar.progress((i + 1) / len(ids))
        st.session_state["scenario_results"] = results
    if "scenario_results" in st.session_state:
        st.markdown("#### Результаты текущего запуска")
        show_scenario_results(st.session_state["scenario_results"])
    elif SCENARIO_REPORT.exists():
        report = json.loads(SCENARIO_REPORT.read_text(encoding="utf-8"))
        st.markdown(f"#### Последний полный прогон ({report['started'][:16].replace('T', ' ')}, {report['model']})")
        show_scenario_results(report["results"])
    else:
        st.info("Отчёта ещё нет. Запустите `python run_scenarios.py` или выберите сценарии выше.")
    st.stop()

# ---------------- Входные данные ----------------
c1, c2 = st.columns([1, 1])
with c1:
    source = st.radio("Документ стратегии", ["Пример (data/sample_strategy.txt)", "Загрузить свой"])
    doc_path = SAMPLE
    if source == "Загрузить свой":
        up = st.file_uploader("TXT, MD, PDF или DOCX", type=["txt", "md", "pdf", "docx"])
        if up:
            UPLOADS.mkdir(parents=True, exist_ok=True)
            doc_path = UPLOADS / up.name
            doc_path.write_bytes(up.getvalue())
        else:
            doc_path = None
with c2:
    request = st.text_area("Запрос к системе",
                           "Сформируй KPI до 2030 года, акцент на образовании и науке", height=110)

if doc_path and Path(doc_path).suffix in (".txt", ".md"):
    with st.expander("Посмотреть документ"):
        st.text(Path(doc_path).read_text(encoding="utf-8", errors="replace")[:6000])

# ---------------- Запуск ----------------
ICONS = {"llm_call": "🧠", "tool_call": "🔧", "message": "✉️", "agent_start": "▶️", "run_start": "🚀", "run_end": "🏁"}


def fmt(e: dict) -> str:
    who = AGENT_TITLES.get(e["agent"], e["agent"])
    t = e["ts"][11:19]
    if e["kind"] == "message":
        return f"{t} ✉️ {who} → {AGENT_TITLES.get(e['receiver'], e['receiver'])}: {e['msg_type']}"
    if e["kind"] in ("llm_call", "tool_call"):
        what = e.get("tool") or e.get("schema")
        mark = "✓" if e.get("status") == "ok" else "✗ " + str(e.get("error", ""))[:120]
        return f"{t} {ICONS[e['kind']]} {who}: {what} {mark} ({e['duration_ms']} мс)"
    return f"{t} {ICONS.get(e['kind'], '•')} {who}: {e['kind']}"


if st.button("🚀 Запустить", type="primary", disabled=doc_path is None):
    ok, msg = OllamaClient(settings).ping()
    if not ok:
        st.error(msg)
        st.stop()
    lines: list[str] = []
    with st.status("Агенты работают…", expanded=True) as status:
        live = st.empty()

        def on_event(e: dict) -> None:
            lines.append(fmt(e))
            live.code("\n".join(lines[-18:]), language=None)

        state, logger = run_pipeline(str(doc_path), request, settings, on_event)
        label = {"done": "Готово", "stopped_by_limit": "Остановлено по лимиту", "failed": "Ошибка"}[state.status]
        status.update(label=f"{label} · {state.steps} шагов · {state.elapsed} с",
                      state="complete" if state.status == "done" else "error", expanded=False)
    st.session_state["result"] = (state, logger)

# ---------------- Результаты ----------------
if "result" not in st.session_state:
    st.info("Нажмите «Запустить». Первый прогон на qwen2.5:7b обычно занимает несколько минут.")
    st.stop()

state, logger = st.session_state["result"]
for err in state.errors:
    st.warning(err)

m = st.columns(5)
m[0].metric("Статус", state.status)
m[1].metric("Целей", len(state.goals))
m[2].metric("Задач", len(state.tasks))
m[3].metric("KPI", len(state.kpis))
m[4].metric("Принято", sum(k.status == "approved" for k in state.kpis))

if state.metrics.get("kpis"):
    q = st.columns(len(METRIC_TITLES))
    for col, (key, title) in zip(q, METRIC_TITLES.items()):
        v = state.metrics.get(key)
        col.metric(title, "—" if v is None else (f"{v}" if key == "avg_smart" else f"{v:.0%}"))

tab_kpi, tab_goals, tab_load, tab_msgs, tab_log = st.tabs(
    ["📊 KPI", "🎯 Цели и задачи", "⚖️ Нагрузка агентов", "✉️ Сообщения", "📜 Лог"])

with tab_kpi:
    df = kpis_dataframe(state)
    if df.empty:
        st.write("KPI не сформированы.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        xlsx = RUNS_DIR / f"{state.run_id}.xlsx"
        df.to_excel(xlsx, index=False)
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Excel", xlsx.read_bytes(), file_name=f"kpi_{state.run_id}.xlsx")
        d2.download_button("⬇️ JSON (состояние)", state.model_dump_json(indent=2),
                           file_name=f"state_{state.run_id}.json")

with tab_goals:
    st.caption(f"План оркестратора: {json.dumps(state.plan, ensure_ascii=False)}")
    for g in state.goals:
        with st.expander(f"{g.id}. {g.title}  ·  {g.direction}", expanded=True):
            st.write(g.description)
            for t in (t for t in state.tasks if t.goal_id == g.id):
                st.markdown(f"- **{t.id}** {t.title}")

with tab_load:
    ld = load_dataframe(logger)
    if ld.empty:
        st.write("Нет вызовов.")
    else:
        worst = ld.share.max()
        (st.success if worst <= LOAD_LIMIT else st.error)(
            f"Максимальная доля одного агента: {worst:.0%} (требование ТЗ: ≤ {LOAD_LIMIT:.0%})")
        st.bar_chart(ld.set_index("Агент")[["llm_calls", "tool_calls"]], stack=True)
        show = ld.drop(columns="agent").assign(share=lambda d: (d.share * 100).round(1).astype(str) + "%")
        st.dataframe(show.rename(columns={"llm_calls": "Вызовы LLM", "tool_calls": "Вызовы инструментов",
                                          "total": "Всего", "share": "Доля"}),
                     use_container_width=True, hide_index=True)

with tab_msgs:
    st.caption("Структурированные сообщения (JSON) между агентами")
    for i, msg in enumerate(state.messages, 1):
        with st.expander(f"{i}. {AGENT_TITLES.get(msg.sender, msg.sender)} → "
                         f"{AGENT_TITLES.get(msg.receiver, msg.receiver)} · {msg.type}"):
            st.json(msg.model_dump())

with tab_log:
    ev = pd.DataFrame(logger.events)
    st.dataframe(ev, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Лог (JSONL)", logger.path.read_bytes(), file_name=logger.path.name)
