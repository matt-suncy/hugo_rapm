"""Raw data acquisition. Everything is cached under data/raw/ and never re-downloaded.

Sources (see reports/data_gaps.md for why these and not stats.nba.com):
  * shufinskiy/nba_data GitHub archives: full-season CDN play-by-play (`cdnnba`) and
    ShotChartDetail (`shotdetail`) dumps, keyed by season start year.
  * api.pbpstats.com: per-game possession counts and player season totals, used as an
    independent check on our lineup/possession parsing and as box-score inputs.

Every download is logged to data/raw/manifest.csv with its UTC retrieval time.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from src import config

MANIFEST = config.RAW / "manifest.csv"
_UA = {"User-Agent": "hugo-rapm research (cached, rate-limited)"}
_last_request = 0.0


def _log(source: str, url: str, path: Path) -> None:
    new = not MANIFEST.exists()
    with open(MANIFEST, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["source", "url", "path", "retrieved_at_utc", "bytes"])
        w.writerow([source, url, path.relative_to(config.ROOT),
                    datetime.now(UTC).isoformat(timespec="seconds"), path.stat().st_size])


def _polite_get(url: str, params: dict | None = None, timeout: int = 120) -> requests.Response:
    global _last_request
    pause = config.load()["sources"]["request_pause_seconds"]
    wait = pause - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        try:
            r = requests.get(url, params=params, headers=_UA, timeout=timeout)
            _last_request = time.monotonic()
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * 2**attempt)
                continue
            r.raise_for_status()
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError):
            time.sleep(5 * 2**attempt)
    raise RuntimeError(f"GET failed after retries: {url} {params}")


# --------------------------------------------------------------------------- archives

def archive(kind: str, season: str) -> pd.DataFrame:
    """Load a shufinskiy archive (e.g. kind='cdnnba') as a DataFrame, downloading once.

    The .tar.xz is the immutable raw artifact; a parquet copy is cached next to it
    because decompressing ~200MB of CSV on every run is slow.
    """
    year = config.season_start_year(season)
    name = f"{kind}_{year}"
    d = config.RAW / "shufinskiy"
    d.mkdir(parents=True, exist_ok=True)
    tar, pq = d / f"{name}.tar.xz", d / f"{name}.parquet"
    if pq.exists():
        return pd.read_parquet(pq)
    if not tar.exists():
        url = f"{config.load()['sources']['shufinskiy_base']}/{name}.tar.xz"
        r = _polite_get(url, timeout=600)
        tar.write_bytes(r.content)
        _log("shufinskiy/nba_data", url, tar)
    df = pd.read_csv(tar, compression={"method": "tar", "mode": "r:xz"}, low_memory=False)
    df.to_parquet(pq, index=False)
    return df


# --------------------------------------------------------------------------- pbpstats

def pbpstats(endpoint: str, params: dict) -> dict:
    """Cached GET against api.pbpstats.com. Cache key = endpoint + sorted params."""
    key = endpoint + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    h = hashlib.sha1(key.encode()).hexdigest()[:16]
    d = config.RAW / "pbpstats"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{endpoint.strip('/').replace('/', '_')}_{h}.json"
    if path.exists():
        return json.loads(path.read_text())
    url = f"{config.load()['sources']['pbpstats_api']}/{endpoint.strip('/')}"
    r = _polite_get(url, params)
    path.write_text(r.text)
    _log("api.pbpstats.com", f"{url}?{key.split('?', 1)[1]}", path)
    return r.json()


def pbpstats_games(season: str) -> pd.DataFrame:
    """Regular-season games with pbpstats' home/away possession counts."""
    js = pbpstats("get-games/nba", {"Season": season, "SeasonType": "Regular Season"})
    df = pd.DataFrame(js["results"])
    df["GameId"] = df["GameId"].astype(int)
    return df


def pbpstats_totals(season: str, kind: str = "Player") -> pd.DataFrame:
    """Season totals by player (or team). The API caps rows at 500, so if the league-wide
    call hits the cap we re-query team by team and de-duplicate traded players' rows."""
    base = {"Season": season, "SeasonType": "Regular Season", "Type": kind}
    rows = pbpstats("get-totals/nba", base)["multi_row_table_data"]
    if kind == "Player" and len(rows) >= 500:
        teams = pbpstats_games(season)["HomeTeamId"].unique()
        per_team = []
        for t in sorted(teams):
            js = pbpstats("get-totals/nba", {**base, "TeamId": str(t)})
            for r in js["multi_row_table_data"]:
                per_team.append({**r, "QueryTeamId": str(t)})
        rows = per_team
    df = pd.DataFrame(rows)
    df["EntityId"] = df["EntityId"].astype(int)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seasons", nargs="*", help="defaults to primary + history")
    ap.add_argument("--totals-only", action="store_true")
    args = ap.parse_args()
    cfg = config.load()
    config.ensure_dirs()
    seasons = args.seasons or [cfg["seasons"]["primary"], *cfg["seasons"]["history"]]
    for s in sorted(set(seasons) | set(cfg["seasons"]["totals_history"])):
        print(f"[ingest] pbpstats totals {s}")
        pbpstats_totals(s)
    if args.totals_only:
        return
    for s in seasons:
        for kind in ("cdnnba", "shotdetail"):
            print(f"[ingest] {kind} {s}")
            archive(kind, s)
        pbpstats_games(s)


if __name__ == "__main__":
    main()
