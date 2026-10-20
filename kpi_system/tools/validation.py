"""Инструмент: формальная проверка KPI (правила SMART) и поиск дублей."""
from difflib import SequenceMatcher

from ..schemas import PERIODICITY

# KPI — это показатель, а не действие: «Доля …», а не «Повысить долю …»
ACTION_VERBS = ("повысить", "увеличить", "обеспечить", "создать", "развить", "развивать", "улучшить",
                "снизить", "сократить", "внедрить", "расширить", "сформировать", "привлечь", "провести")
# признаки того, что формула описывает способ расчёта
FORMULA_MARKERS = ("/", "÷", "*", "×", "+", "-", "−", "сумм", "количеств", "кол-во", "число", "доля",
                   "отношени", "средн", "итог")
RATIO_MARKERS = ("/", "÷", "доля", "отношени", "× 100", "*100", "×100", "* 100")
KNOWN_UNITS = ("%", "шт", "чел", "балл", "баллы", "млн руб", "тыс руб", "руб", "лет", "год", "дн", "дней",
               "ч", "раз", "ед", "проц")


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").replace(".", " ").split())


def check_kpi_formal(kpi: dict, task_title: str = "") -> dict:
    errors, warnings = [], []
    name, formula, unit = _norm(kpi.get("name", "")), _norm(kpi.get("formula", "")), _norm(kpi.get("unit", ""))

    # S — конкретность
    if len(name) < 5:
        errors.append("Слишком короткое или пустое название показателя")
    elif name.split()[0] in ACTION_VERBS:
        errors.append("Название сформулировано как действие («повысить…»), а не как показатель («доля…», «число…»)")
    if task_title and SequenceMatcher(None, name, _norm(task_title)).ratio() >= 0.9:
        errors.append("Название KPI дословно повторяет задачу — нужен измеримый показатель")

    # M — измеримость
    if len(formula) < 3:
        errors.append("Не указана формула расчёта")
    elif not any(m in formula for m in FORMULA_MARKERS):
        errors.append("Формула не описывает способ расчёта (нет операции, суммы, количества или доли)")
    if not unit:
        errors.append("Не указана единица измерения")
    elif not any(unit.startswith(u) for u in KNOWN_UNITS):
        warnings.append(f"Нестандартная единица измерения «{kpi.get('unit')}»")
    if unit == "%" and formula and not any(m in formula for m in RATIO_MARKERS):
        warnings.append("Процентный показатель, но формула не похожа на отношение")
    if not _norm(kpi.get("data_source", "")):
        warnings.append("Не указан источник данных")

    # T — привязка ко времени
    if kpi.get("periodicity") not in PERIODICITY:
        warnings.append("Нестандартная периодичность")

    # A — целевое значение
    base, target = kpi.get("baseline"), kpi.get("target")
    if target is None:
        warnings.append("Нет целевого значения: требуется сбор исходных данных")
    elif base is not None:
        if target == base:
            errors.append("Целевое значение не отличается от базового")
        elif kpi.get("higher_is_better", True) and target < base:
            errors.append("Целевое значение ниже базового при растущем показателе")
        elif not kpi.get("higher_is_better", True) and target > base:
            errors.append("Целевое значение выше базового при снижающемся показателе")
    if unit == "%" and target is not None and target > 100:
        errors.append("Процентный показатель больше 100%")
    return {"errors": errors, "warnings": warnings}


def find_duplicates(kpis: list[dict], threshold: float = 0.8) -> list[dict]:
    dups = []
    for i, a in enumerate(kpis):
        for b in kpis[i + 1:]:
            ratio = SequenceMatcher(None, _norm(a["name"]), _norm(b["name"])).ratio()
            if ratio >= threshold:
                dups.append({"first": a["id"], "second": b["id"], "similarity": round(ratio, 2)})
    return dups
