# Hugo Gonzalez: RAPM vs DARKO/LEBRON

Why does Hugo Gonzalez (BOS) rate around +3.5 in 1-year RAPM but around 0 in DARKO and LEBRON,
with almost the whole gap on offense? The full plan, with hypotheses H1–H6, Tests 0–8 and
their decision rules, is in [hugo_gonzalez_rapm_analysis_plan.md](hugo_gonzalez_rapm_analysis_plan.md).

## Run

```bash
uv sync            # Python 3.11 env from pyproject.toml / uv.lock
make all           # ingest -> possessions -> validate -> Test 0 -> k estimation
make test          # unit tests
```

All downloads are cached in `data/raw/` and logged with retrieval times in
`data/raw/manifest.csv`. Once the cache is filled, `make all` runs offline.

## Data sources

| Source | Used for | Retrieved |
|---|---|---|
| [shufinskiy/nba_data](https://github.com/shufinskiy/nba_data) `cdnnba_<year>` (NBA CDN play-by-play dumps) | lineups, possessions, shots | see manifest |
| api.pbpstats.com `get-games`, `get-totals`, `get-game-stats` | parse validation, season totals for k estimation, fallback for 5 OT period starters | see manifest |
| User-supplied multi-year RAPM spreadsheet (2020-21 to 2026-27) | Test 0 league-wide check | `config.yaml` `reference_rapm` |

stats.nba.com and cdn.nba.com are not reachable from the dev machine. Every substitution is
logged in [reports/data_gaps.md](reports/data_gaps.md).

## Status

| Step | State | Output |
|---|---|---|
| Ingest + possession table | done | `data/processed/possessions_2025-26.parquet`, `reports/validation_2025-26.md` |
| Test 0 baseline RAPM | done (1-year and multi-year fits) | `reports/test0_baseline.md` |
| §4.4 padding k | done | `reports/stabilize_k.md` |
| Tests 1–8 | not started | |
