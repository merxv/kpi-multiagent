"""Оркестратор: только планирует и распределяет задачи между агентами, предметную работу не делает."""
from ..logger import short
from ..schemas import DIRECTIONS, KPI, AgentMessage, Goal, PlanOut, Task
from .base import AgentError, BaseAgent

SYSTEM = f"""Ты — оркестратор системы формирования KPI университета. Ты только планируешь работу.
Из запроса пользователя извлеки параметры:
- horizon_year: год, к которому должны быть достигнуты цели (если не указан — 2030);
- focus_directions: направления, на которых сделать акцент (из списка: {", ".join(DIRECTIONS)}),
  пустой список — если пользователь не ограничил направления;
- notes: одно предложение о плане работы.
Ответ строго JSON: {{"horizon_year": 2030, "focus_directions": [], "notes": "..."}}"""


class PipelineError(Exception):
    """Ошибка, после которой продолжать работу бессмысленно."""


class Orchestrator(BaseAgent):
    name = "orchestrator"
    role = "Планирует работу и распределяет задачи между агентами"

    def __init__(self, ctx, analyst, decomposer, builder, target_setter, reviewer):
        super().__init__(ctx)
        self.analyst, self.decomposer, self.builder = analyst, decomposer, builder
        self.target_setter, self.reviewer = target_setter, reviewer

    # ---------- обмен сообщениями ----------
    def dispatch(self, agent: BaseAgent, msg_type: str, **payload) -> dict:
        msg = AgentMessage(sender=self.name, receiver=agent.name, type=msg_type, payload=payload)
        self._record(msg)
        reply = agent.receive(msg)
        self._record(reply)
        return reply.payload

    def _record(self, msg: AgentMessage) -> None:
        self.ctx.state.messages.append(msg)
        self.ctx.logger.log("message", msg.sender, receiver=msg.receiver, msg_type=msg.type,
                            payload=short(msg.payload, 400))

    # ---------- сценарий ----------
    def run(self) -> None:
        st, cfg = self.ctx.state, self.ctx.settings

        st.status = "planning"
        plan = self.ask_llm(SYSTEM, f"Запрос пользователя: {st.request or 'сформировать KPI по стратегии'}", PlanOut)
        st.plan = plan.model_dump()
        st.save()

        st.status = "extracting_goals"
        res = self.dispatch(self.analyst, "extract_goals", document_path=st.document_path,
                            max_goals=cfg.max_goals, focus_directions=plan.focus_directions)
        st.goals = [Goal(**g) for g in res["goals"]]
        if not st.goals:
            raise PipelineError("В документе не найдено стратегических целей")
        st.save()

        st.status = "decomposing"
        for goal in st.goals:
            try:
                res = self.dispatch(self.decomposer, "decompose", goal=goal.model_dump(), n_tasks=cfg.tasks_per_goal)
                st.tasks += [Task(**t) for t in res["tasks"]]
            except AgentError as e:
                st.errors.append(f"Цель {goal.id} не декомпозирована: {e}")
        if not st.tasks:
            raise PipelineError("Не удалось сформировать ни одной задачи")
        st.save()

        st.status = "building_kpi"
        goals = {g.id: g for g in st.goals}
        for task in st.tasks:
            kpi = self._build_and_target(task, goals[task.goal_id], kpi_id=f"KPI-{task.id}")
            if kpi:
                st.kpis.append(kpi)
        st.save()

        st.status = "reviewing"
        pending = list(st.kpis)
        for round_no in range(cfg.max_revisions + 1):
            pending = self._review(pending)
            if not pending:
                break
            if round_no == cfg.max_revisions:
                for k in pending:  # лимит доработок исчерпан — помечаем для человека
                    k.status = "needs_attention"
                break
            st.status = f"revision_{round_no + 1}"
            tasks = {t.id: t for t in st.tasks}
            revised = []
            for k in pending:
                new = self._build_and_target(tasks[k.task_id], goals[k.goal_id], kpi_id=k.id,
                                             notes=k.review_notes, previous=k)
                if new:
                    new.revisions = k.revisions + 1
                    self._replace(new)
                    revised.append(new)
                else:
                    k.status = "needs_attention"
            pending = revised
        st.save()

    # ---------- вспомогательное ----------
    def _build_and_target(self, task: Task, goal: Goal, kpi_id: str, notes=None, previous: KPI | None = None):
        try:
            res = self.dispatch(self.builder, "build_kpi", task=task.model_dump(), goal=goal.model_dump(),
                                kpi_id=kpi_id, notes=notes,
                                previous=previous.model_dump(include={"name", "formula", "unit"}) if previous else None)
            res = self.dispatch(self.target_setter, "set_target", kpi=res["kpi"],
                                horizon_year=self.ctx.state.plan["horizon_year"])
            return KPI(**res["kpi"])
        except AgentError as e:
            self.ctx.state.errors.append(f"KPI для задачи {task.id} не сформирован: {e}")
            return None

    def _review(self, kpis: list[KPI]) -> list[KPI]:
        st = self.ctx.state
        res = self.dispatch(self.reviewer, "review", kpis=[k.model_dump() for k in kpis],
                            goals={g.id: g.title for g in st.goals}, tasks={t.id: t.title for t in st.tasks},
                            all_kpis=[k.model_dump(include={"id", "name"}) for k in st.kpis])
        reviewed = [KPI(**k) for k in res["kpis"]]
        for k in reviewed:
            self._replace(k)
        return [k for k in reviewed if k.status == "needs_revision"]

    def _replace(self, kpi: KPI) -> None:
        st = self.ctx.state
        st.kpis = [kpi if k.id == kpi.id else k for k in st.kpis]
