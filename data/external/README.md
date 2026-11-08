# Manually supplied published metrics

nbarapm.com's robots.txt disallows `/api/`, and it offers no downloadable 1-year RAPM table,
so published metrics are supplied by hand.

- **Test 0 reference RAPM:** a multi-year (2020-21 to 2026-27) RAPM spreadsheet in
  `data/raw/RAPM 2020-2027 - Sheet1.csv`, configured in `config.yaml` under
  `reference_rapm` (path, sign convention, matching window). To swap in another table,
  point that block at the new file.
- **Test 8 monitoring:** DARKO / LEBRON / RAPM snapshots go in
  `data/monitoring/metrics_snapshots.csv`, one row per player-metric-date.
