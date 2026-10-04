"""Типизированные сообщения и сущности, которыми обмениваются агенты."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

DIRECTIONS = [
    "образование",
    "наука",
    "кадры",
    "финансы",
    "цифровизация",
    "международная деятельность",
    "молодёжная политика",
]
PERIODICITY = ["год", "полугодие", "квартал", "месяц"]


_DIRECTION_KEYS = {
    "образование": ("образов", "обучен", "учебн", "абитур", "студент"),
    "наука": ("наук", "научн", "исследов", "ниокр", "публикац"),
    "кадры": ("кадр", "персонал", "сотрудник", "преподават"),
    "финансы": ("финанс", "доход", "бюджет", "экономи"),
    "цифровизация": ("цифр", "информац", "онлайн", "it"),
    "международная деятельность": ("междун", "иностран", "интернац"),
    "молодёжная политика": ("молод", "воспит", "волонт", "внеучеб"),
}


def normalize_direction(value: str) -> str:
    """Приводит направление, придуманное моделью, к одному из DIRECTIONS."""
    v = (value or "").strip().lower().replace("ё", "е")
    for direction, keys in _DIRECTION_KEYS.items():
        if any(k in v for k in keys):
            return direction
    return "прочее"


# ---------- Сообщение между агентами ----------
class AgentMessage(BaseModel):
    sender: str
    receiver: str
    type: str
    payload: dict[str, Any] = {}
    ts: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ---------- Предметные сущности ----------
class Goal(BaseModel):
    id: str
    title: str
    direction: str
    description: str = ""


class Task(BaseModel):
    id: str
    goal_id: str
    title: str
    direction: str


class KPI(BaseModel):
    id: str
    task_id: str
    goal_id: str
    name: str
    formula: str
    unit: str
    periodicity: str = "год"
    data_source: str = ""
    metric_code: Optional[str] = None
    higher_is_better: bool = True
    baseline: Optional[float] = None
    baseline_year: Optional[int] = None
    target: Optional[float] = None
    target_year: Optional[int] = None
    justification: str = ""
    status: Literal["draft", "approved", "needs_revision", "needs_attention"] = "draft"
    review_notes: list[str] = []
    revisions: int = 0


# ---------- Схемы ответов LLM (проверяются pydantic) ----------
class PlanOut(BaseModel):
    horizon_year: int = Field(2030, ge=2025, le=2050)
    focus_directions: list[str] = []
    notes: str = ""


class GoalOut(BaseModel):
    title: str
    direction: str = ""
    description: str = ""


class GoalsOut(BaseModel):
    goals: list[GoalOut] = []


class TaskOut(BaseModel):
    title: str
    direction: str = ""


class TasksOut(BaseModel):
    tasks: list[TaskOut] = Field(min_length=1)


class KPIOut(BaseModel):
    name: str = Field(min_length=3)
    formula: str
    unit: str
    periodicity: str = "год"
    data_source: str = ""
    metric_code: Optional[str] = None
    higher_is_better: bool = True

    @field_validator("periodicity")
    @classmethod
    def _period(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in PERIODICITY else "год"

    @field_validator("metric_code", mode="before")
    @classmethod
    def _code(cls, v):
        if v in (None, "", "null", "None", "нет"):
            return None
        return str(v).strip()


class JustificationOut(BaseModel):
    justification: str


class ReviewOut(BaseModel):
    relevant: bool
    measurable: bool
    comment: str = ""
