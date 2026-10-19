# Data gaps and source substitutions

Logged per the plan's ground rule: nothing is fabricated; every unavailable source and its
fallback is listed here. Dates are when the gap was checked.

| Date | Planned source | Status | Fallback used | Impact |
|---|---|---|---|---|
| 2026-10-19 | `nba_api` / stats.nba.com (PBP, rotations, shot charts, box scores) | Requests time out from this machine (even with full browser headers) | Play-by-play: CDN live PBP dumps from github.com/shufinskiy/nba_data (`cdnnba_<year>`). Shots: same PBP (x/y, area, descriptor) plus `shotdetail_<year>`. Box/season totals: api.pbpstats.com `get-totals` | None for lineups: our parse matches pbpstats points exactly and player plus-minus within ±5 (see `reports/validation_2025-26.md`) |
| 2026-10-19 | cdn.nba.com live JSON directly | HTTP 403 | Same shufinskiy archives (they are CDN dumps) | None |
| 2026-10-19 | Lineups on court per possession | No source ships them (pbpstats possession endpoint has no lineups and caps at 500 rows) | Reconstructed from substitutions in `src/possessions.py`; 5 OT periods in 2025-26 needed pbpstats' per-period lineup list to identify a starter with no events | None measurable |
| 2026-10-19 | nbarapm.com league-wide RAPM, six-factor tab | robots.txt disallows `/api/`; not scraped | Hugo's published values from the analysis plan (config.yaml `published_hugo`); league-wide check needs a manual CSV in `data/external/` | Test 0 league-wide correlation **pending** |
| 2026-10-19 | 2026-27 regular season | Season has not started (opens 2026-10-20) | — | Test 8 monitoring has no data yet |
| 2026-10-19 | Historical lineup data 2018-19, 2019-20 | `cdnnba` archives start in 2020-21 | Winner's-curse / box-prior history uses 2020-21 onward; season totals (no lineups) still cover 2018-19 onward | Fewer season pairs for Test 1 step 3 |
| 2026-10-19 | pbpstats player DefPoss | Sums to 0.75% more than OffPoss league-wide (different convention) | Validate on OffPoss and game totals | None |
