"""Модульные тесты инструментов и защиты (без LLM): pytest -q"""
import pytest

from kpi_system.agents import BaseAgent
from kpi_system.agents.base import MAX_TOOLS
from kpi_system.config import DATA_DIR
from kpi_system.schemas import KPIOut, normalize_direction
from kpi_system.state import LimitExceeded, TaskState
from kpi_system.tools import (check_kpi_formal, compute_target, find_duplicates, list_metrics,
                              read_document, search_kpi_library, split_into_chunks)


def test_read_and_split_sample():
    text = read_document(str(DATA_DIR / "sample_strategy.txt"))
    chunks = split_into_chunks(text, max_chars=1500, max_chunks=10)
    assert len(chunks) >= 2
    assert all(len(c) <= 1500 for c in chunks)


def test_short_document_rejected():
    with pytest.raises(ValueError):
        read_document(str(DATA_DIR / "test_docs" / "too_short.txt"))


def test_unsupported_format(tmp_path):
    f = tmp_path / "x.xyz"
    f.write_text("a" * 200, encoding="utf-8")
    with pytest.raises(ValueError):
        read_document(str(f))


def test_library_search_finds_relevant():
    res = search_kpi_library("трудоустройство выпускников", "образование")
    assert res and res[0]["code"] == "EDU-02"


def test_compute_target_growth_and_cap():
    r = compute_target("graduate_employment", 2030, True)
    assert r["baseline"] == 81 and r["target"] > r["baseline"] and r["target"] <= 100


def test_compute_target_lower_is_better():
    r = compute_target("staff_avg_age", 2030, False)
    assert r["target"] < r["baseline"]


def test_compute_target_unknown_metric():
    with pytest.raises(KeyError):
        compute_target("no_such_metric", 2030)


def test_list_metrics_unique():
    codes = [m["metric_code"] for m in list_metrics()]
    assert len(codes) == len(set(codes)) >= 10


def test_formal_check_catches_errors():
    bad = {"name": "", "formula": "", "unit": "%", "baseline": 50, "target": 120, "higher_is_better": True}
    errors = check_kpi_formal(bad)["errors"]
    assert len(errors) >= 3


def test_duplicates():
    kpis = [{"id": "A", "name": "Доля иностранных студентов"},
            {"id": "B", "name": "Доля иностранных студентов (%)"},
            {"id": "C", "name": "Доходы от НИОКР"}]
    d = find_duplicates(kpis)
    assert len(d) == 1 and d[0]["second"] == "B"


def test_step_limit():
    st = TaskState(run_id="t", request="", document_path="", max_steps=2, max_runtime_sec=100)
    st.tick(); st.tick()
    with pytest.raises(LimitExceeded):
        st.tick()


def test_llm_schema_normalizes():
    k = KPIOut(name="Доля X", formula="a/b", unit="%", periodicity="ежегодно", metric_code="null")
    assert k.periodicity == "год" and k.metric_code is None


def test_direction_normalization():
    assert normalize_direction("Научная деятельность") == "наука"
    assert normalize_direction("Кадровая политика") == "кадры"


def test_tool_limit_per_agent():
    class Greedy(BaseAgent):
        def register_tools(self):
            return {str(i): print for i in range(MAX_TOOLS + 1)}
    with pytest.raises(ValueError):
        Greedy(ctx=None)


# ---------- правила проверяющего (SMART) ----------
GOOD_KPI = {"name": "Доля трудоустроенных выпускников", "formula": "Трудоустроенные / выпускники × 100",
            "unit": "%", "periodicity": "год", "data_source": "Мониторинг", "baseline": 81, "target": 90,
            "higher_is_better": True}


def test_good_kpi_has_no_errors():
    assert check_kpi_formal(GOOD_KPI, "Повысить трудоустройство выпускников")["errors"] == []


def test_action_verb_name_rejected():
    errors = check_kpi_formal({**GOOD_KPI, "name": "Повысить долю трудоустроенных"})["errors"]
    assert any("действие" in e for e in errors)


def test_formula_without_calculation_rejected():
    errors = check_kpi_formal({**GOOD_KPI, "formula": "по данным отдела кадров"})["errors"]
    assert any("способ расчёта" in e for e in errors)


def test_name_copying_task_rejected():
    errors = check_kpi_formal(GOOD_KPI, task_title="Доля трудоустроенных выпускников")["errors"]
    assert any("повторяет задачу" in e for e in errors)


def test_target_equal_to_baseline_rejected():
    errors = check_kpi_formal({**GOOD_KPI, "target": 81})["errors"]
    assert any("не отличается" in e for e in errors)


def test_smart_scores_clamped_and_required():
    from pydantic import ValidationError
    from kpi_system.schemas import ReviewOut
    r = ReviewOut(specific=7, measurable="4", achievable=0, relevant=True, time_bound=4.6)
    assert r.scores() == {"specific": 5, "measurable": 4, "achievable": 1, "relevant": 5, "time_bound": 5}
    with pytest.raises(ValidationError):
        ReviewOut(specific=4)  # нет measurable и relevant — ответ модели отправится на повтор


# ---------- сценарии ----------
def test_scenarios_file_valid():
    from kpi_system.scenarios import CHECKS, load_scenarios
    scenarios = load_scenarios()
    assert len(scenarios) >= 10
    assert len({s["id"] for s in scenarios}) == len(scenarios)
    for s in scenarios:
        assert s.get("expected_result") and s.get("expect")
        assert set(s["expect"]) <= set(CHECKS), s["id"]
        assert s["doc"]
