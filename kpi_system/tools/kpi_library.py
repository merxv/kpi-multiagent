"""Инструмент: справочник типовых KPI вузов в SQLite (наполняется из data/kpi_library.csv)."""
import csv
import re
import sqlite3

from ..config import DATA_DIR

DB_PATH = DATA_DIR / "kpi_library.db"
SEED_CSV = DATA_DIR / "kpi_library.csv"


def _connect() -> sqlite3.Connection:
    fresh = not DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if fresh:
        conn.execute(
            "CREATE TABLE kpi (code TEXT PRIMARY KEY, name TEXT, direction TEXT, formula TEXT,"
            " unit TEXT, metric_code TEXT, description TEXT)"
        )
        with SEED_CSV.open(encoding="utf-8") as f:
            rows = [tuple(r.values()) for r in csv.DictReader(f)]
        conn.executemany("INSERT INTO kpi VALUES (?,?,?,?,?,?,?)", rows)
        conn.commit()
    return conn


def _stems(text: str) -> set[str]:
    """Грубый стемминг: первые 5 букв слов длиннее 3 символов."""
    return {w[:5] for w in re.findall(r"[а-яёa-z]+", text.lower()) if len(w) > 3}


def search_kpi_library(query: str, direction: str = "", limit: int = 5) -> list[dict]:
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM kpi")]
    q = _stems(query)
    scored = []
    for r in rows:
        score = len(q & _stems(f"{r['name']} {r['description']}"))
        if direction and r["direction"] == direction:
            score += 1
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]
