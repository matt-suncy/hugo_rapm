"""Config loading and canonical paths."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
EXTERNAL = DATA / "external"
MONITORING = DATA / "monitoring"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"


@lru_cache
def load(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def season_start_year(season: str) -> int:
    """'2025-26' -> 2025 (shufinskiy archives are keyed by the season's start year)."""
    return int(season[:4])


def ensure_dirs() -> None:
    for d in (RAW, PROCESSED, EXTERNAL, MONITORING, REPORTS, FIGURES):
        d.mkdir(parents=True, exist_ok=True)
