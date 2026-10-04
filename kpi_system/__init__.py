"""Многоагентная система формирования KPI на основе стратегии университета."""
from .config import Settings
from .pipeline import kpis_dataframe, load_dataframe, run_pipeline

__all__ = ["Settings", "run_pipeline", "kpis_dataframe", "load_dataframe"]
