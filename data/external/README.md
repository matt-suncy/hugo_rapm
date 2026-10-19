# Manually exported published metrics

nbarapm.com's robots.txt disallows `/api/`, so published league-wide RAPM is not scraped.
To enable Test 0's league-wide correlation check, export the 1Y RAPM table by hand and save it
as `nbarapm_rapm_<YYYY-MM-DD>.csv` (the retrieval date). The newest file is used.

Required columns (aliases accepted, see `ALIASES` in `src/analysis/test0_baseline.py`):
- `player_id` (nba.com id) **or** `name` (must match pbpstats names)
- `total` (RAPM total, pts/100)

DARKO / LEBRON snapshots for Test 8 monitoring go in `data/monitoring/metrics_snapshots.csv`.
