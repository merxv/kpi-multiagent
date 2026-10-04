from .base import AgentError, BaseAgent, RunContext
from .decomposer import Decomposer
from .kpi_builder import KPIBuilder
from .orchestrator import Orchestrator, PipelineError
from .reviewer import Reviewer
from .strategy_analyst import StrategyAnalyst
from .target_setter import TargetSetter

AGENT_TITLES = {
    "orchestrator": "Оркестратор",
    "strategy_analyst": "Аналитик стратегии",
    "decomposer": "Декомпозитор целей",
    "kpi_builder": "Конструктор KPI",
    "target_setter": "Агент целевых значений",
    "reviewer": "Проверяющий",
}

__all__ = [
    "AgentError", "BaseAgent", "RunContext", "Orchestrator", "PipelineError", "StrategyAnalyst",
    "Decomposer", "KPIBuilder", "TargetSetter", "Reviewer", "AGENT_TITLES",
]
