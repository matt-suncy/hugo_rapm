"""Shared helpers for the per-test runners in src/analysis/."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from src import config, ingest

RESULTS = config.REPORTS / "results"


def load_possessions(season: str) -> pd.DataFrame:
    path = config.PROCESSED / f"possessions_{season}.parquet"
    if not path.exists():
        raise SystemExit(f"{path} missing; run `make possessions` first")
    return pd.read_parquet(path)


def player_names(season: str) -> pd.DataFrame:
    """player_id -> name, team(s), from pbpstats season totals."""
    t = ingest.pbpstats_totals(season)
    return (t.groupby("EntityId")
             .agg(name=("Name", "first"),
                  team=("TeamAbbreviation", lambda s: "/".join(sorted(set(s.dropna())))))
             .rename_axis("player_id").reset_index())


def save_result(test: str, payload: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {"test": test, "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
               **payload}
    (RESULTS / f"{test}.json").write_text(json.dumps(payload, indent=2, default=float))


def load_result(test: str) -> dict:
    path = RESULTS / f"{test}.json"
    if not path.exists():
        raise SystemExit(f"{path} missing; run that test first")
    return json.loads(path.read_text())
