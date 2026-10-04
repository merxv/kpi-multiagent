"""Инструмент: формальная проверка KPI (правила SMART) и поиск дублей."""
from difflib import SequenceMatcher

from ..schemas import PERIODICITY


def check_kpi_formal(kpi: dict) -> dict:
    errors, warnings = [], []
    if len(kpi.get("name", "").strip()) < 5:
        errors.append("Слишком короткое или пустое название показателя")
    if len(kpi.get("formula", "").strip()) < 3:
        errors.append("Не указана формула расчёта")
    if not kpi.get("unit", "").strip():
        errors.append("Не указана единица измерения")
    if kpi.get("periodicity") not in PERIODICITY:
        warnings.append("Нестандартная периодичность")
    if not kpi.get("data_source", "").strip():
        warnings.append("Не указан источник данных")

    base, target = kpi.get("baseline"), kpi.get("target")
    if target is None:
        warnings.append("Нет целевого значения: требуется сбор исходных данных")
    elif base is not None:
        if kpi.get("higher_is_better", True) and target < base:
            errors.append("Целевое значение ниже базового при растущем показателе")
        if not kpi.get("higher_is_better", True) and target > base:
            errors.append("Целевое значение выше базового при снижающемся показателе")
    if kpi.get("unit") == "%" and target is not None and target > 100:
        errors.append("Процентный показатель больше 100%")
    return {"errors": errors, "warnings": warnings}


def find_duplicates(kpis: list[dict], threshold: float = 0.8) -> list[dict]:
    dups = []
    for i, a in enumerate(kpis):
        for b in kpis[i + 1:]:
            ratio = SequenceMatcher(None, a["name"].lower(), b["name"].lower()).ratio()
            if ratio >= threshold:
                dups.append({"first": a["id"], "second": b["id"], "similarity": round(ratio, 2)})
    return dups
