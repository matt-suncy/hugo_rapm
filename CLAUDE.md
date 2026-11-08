# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A basketball analytics study: why Hugo Gonzalez's (nba id 1642864, BOS) RAPM disagrees with
DARKO/LEBRON. `hugo_gonzalez_rapm_analysis_plan.md` is the spec. Its tests (0–8), hypotheses
(H1–H6) and section-6 decision rules define the work. Every test runner must report which
decision-rule branch fired.

## Commands

```bash
uv sync                      # env (Python 3.11); always run code via `uv run`
make all                     # ingest -> possessions -> validate -> test0 -> stabilize
make possessions SEASON=2025-26
make test                    # uv run pytest -q
uv run pytest tests/test_possessions.py::test_ft_credit_uses_lineup_at_foul   # single test
make lint                    # ruff, line length 100
```

Modules run as `python -m src.<module>` (e.g. `src.analysis.test0_baseline`). Imports are
`from src import ...`. pytest sets `pythonpath = ["."]`.

## Ground rules from the plan

- Never fabricate data. If a source is unavailable, add a row to `reports/data_gaps.md` with
  the fallback used.
- Raw pulls are cached in `data/raw/` and never re-downloaded or edited. Go through
  `src/ingest.py` (`archive()`, `pbpstats()`), which caches, rate-limits and logs every fetch
  to `data/raw/manifest.csv`.
- nbarapm.com's robots.txt disallows `/api/`, so don't scrape it. Published league-wide
  values are supplied by hand. Test 0's reference is a user-supplied **multi-year**
  (2020-21 to 2026-27) RAPM spreadsheet configured under `reference_rapm`. Its `Def`
  column is points allowed, so flip the sign. Compare it against our multi-year fit,
  never the 1-year one.
- All parameters (seasons, λ grid, garbage-time rule, seeds, bootstrap reps) live in
  `config.yaml`; don't hard-code them. In YAML, quote the keys `"off"`/`"on"`/`"no"`, since
  YAML 1.1 parses them as booleans.

## Data flow

1. **Source.** stats.nba.com and cdn.nba.com are blocked from the dev machine. Play-by-play
   comes from shufinskiy/nba_data `cdnnba_<start year>` archives (CDN live PBP, so 2025-26
   is `cdnnba_2025`; they start in 2020-21). api.pbpstats.com provides game possession
   counts and player season totals. Its `get-totals` caps at 500 rows, so `pbpstats_totals`
   re-queries per team, and traded players then have one row per team; aggregate by
   `EntityId`. The API omits zero-valued fields, so `fillna(0)`.
2. **`src/possessions.py`** reconstructs lineups (no source provides them):
   - Period starters are players whose first appearance in the period isn't a sub-in.
   - When that doesn't give 5, starters are filled from pbpstats' per-period lineup list.
   - A possession is a run of consecutive events with the same CDN `possession` value.
   - Each event emits `(run, lineup key, stat, n)` increments, and rows are their sums.
     One possession can therefore span several rows (lineup changes mid-possession), and
     only one row has `poss=1`.
   - FT points and possession credit go to the lineup on the floor at the foul.
   - A period's last run with no shot, FT or turnover isn't counted as a possession.
   - `shots_<season>.parquet` links each FGA/FTA to its possession row via `row_id`.
   - Garbage time is flagged per config and reverted if the game gets close again.
3. **`src/validate.py`** checks the parse against pbpstats (`reports/validation_<season>.md`).
   Points match exactly, player plus-minus is within ±5, and game possessions are within ±1
   for 95% of team-games. Compare players on OffPoss: pbpstats' DefPoss uses a different
   convention (its league sum is 0.75% above OffPoss). Re-run this after any parser change.
4. **`src/rapm.py`** aggregates rows to stints `(game, off five, def five)`. The target is
   100·points/poss, weighted by poss. Each player has separate O and D columns, and defense
   is reported sign-flipped so positive = good. `solve()` uses dense normal equations
   (about 1,200 columns) and takes an optional prior mean `b0` (prior-informed RAPM for
   Test 3) and per-column penalties. CV and bootstrap resample by **game**, never by stint.
5. **`src/stabilize.py`**: padded rates `(m + k·p_lg)/(n + k)`, with k estimated by
   beta-binomial MLE, split-half reliability and next-season out-of-sample error. Results
   go to `data/processed/stabilize_k.csv`; use those k values wherever the plan says
   "stabilized".
6. **`src/analysis/testN_*.py`**: one runner per plan test. Each writes `reports/testN_*.md`,
   figures in `reports/figures/`, and a machine-readable `reports/results/testN.json` (via
   `common.save_result`) so later tests and the final report read numbers, not markdown.
   `notebooks/` are meant to be thin wrappers over these.

The plan's deliverables tree names `src/luck.py`, `box_prior.py`, `context.py`, `factors.py`
and `simulate.py` for Tests 2–7. Their order of work is in plan section 8.
