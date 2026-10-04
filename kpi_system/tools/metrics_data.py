"""Инструмент: фактические показатели вуза (CSV) и расчёт целевых значений по тренду."""
import pandas as pd

from ..config import DATA_DIR

METRICS_CSV = DATA_DIR / "university_metrics.csv"
MIN_ANNUAL_STEP = 0.02  # минимальное ежегодное улучшение, если тренд слабый


def _load() -> pd.DataFrame:
    return pd.read_csv(METRICS_CSV)


def list_metrics() -> list[dict]:
    df = _load()
    return df.drop_duplicates("metric_code")[["metric_code", "metric_name", "unit"]].to_dict("records")


def compute_target(metric_code: str, horizon_year: int, higher_is_better: bool = True) -> dict:
    df = _load()
    hist = df[df.metric_code == metric_code].sort_values("year")
    if hist.empty:
        raise KeyError(f"Нет данных по показателю {metric_code}")
    years, values = hist.year.tolist(), hist.value.astype(float).tolist()
    unit = hist.unit.iloc[0]
    baseline, last_year = values[-1], int(years[-1])
    span = max(horizon_year - last_year, 1)
    trend = (values[-1] - values[0]) / max(len(values) - 1, 1)
    projected = baseline + trend * span

    if higher_is_better:
        target = max(projected, baseline * (1 + MIN_ANNUAL_STEP * span))
    else:
        target = min(projected, baseline * (1 - MIN_ANNUAL_STEP * span))
    if unit == "%":
        target = min(target, 100.0)
    target = max(target, 0.0)

    return {
        "metric_code": metric_code,
        "unit": unit,
        "history": dict(zip(map(int, years), values)),
        "baseline": round(baseline, 2),
        "baseline_year": last_year,
        "target": round(target, 2),
        "target_year": horizon_year,
        "avg_annual_trend": round(trend, 2),
    }
