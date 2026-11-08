# Data gaps and source substitutions

Logged per the plan's ground rule: nothing is fabricated; every unavailable source and its
fallback is listed here. Dates are when the gap was checked.

| Date | Planned source | Status | Fallback used | Impact |
|---|---|---|---|---|
| 2026-10-19 | `nba_api` / stats.nba.com (PBP, rotations, shot charts, box scores) | Requests time out from this machine (even with full browser headers) | Play-by-play: CDN live PBP dumps from github.com/shufinskiy/nba_data (`cdnnba_<year>`). Shots: same PBP (x/y, area, descriptor) plus `shotdetail_<year>`. Box/season totals: api.pbpstats.com `get-totals` | None for lineups: our parse matches pbpstats points exactly and player plus-minus within ±5 (see `reports/validation_2025-26.md`) |
| 2026-10-19 | cdn.nba.com live JSON directly | HTTP 403 | Same shufinskiy archives (they are CDN dumps) | None |
| 2026-10-19 | Lineups on court per possession | No source ships them (pbpstats possession endpoint has no lineups and caps at 500 rows) | Reconstructed from substitutions in `src/possessions.py`; 5 OT periods in 2025-26 needed pbpstats' per-period lineup list to identify a starter with no events | None measurable |
| 2026-10-19 | nbarapm.com league-wide RAPM, six-factor tab | robots.txt disallows `/api/`; not scraped | Hugo's published values from the analysis plan (config.yaml `published_hugo`) | — |
| 2026-11-08 | League-wide 1-year RAPM for Test 0 | nbarapm.com has no 1Y table to download | User-supplied multi-year RAPM spreadsheet, 2020-21 to 2026-27 (`data/raw/RAPM 2020-2027 - Sheet1.csv`, origin URL not recorded). Test 0 compares it with our own multi-year fit over 2020-21 to 2025-26 | League-wide check is multi-year, not 1Y. Our window lacks the reference's 2026-27 games (no PBP yet) |
| 2026-10-19 | 2026-27 regular season | Season has not started (opens 2026-10-20) | — | Test 8 monitoring has no data yet |
| 2026-10-19 | Historical lineup data 2018-19, 2019-20 | `cdnnba` archives start in 2020-21 | Winner's-curse / box-prior history uses 2020-21 onward; season totals (no lineups) still cover 2018-19 onward | Fewer season pairs for Test 1 step 3 |
| 2026-10-19 | pbpstats player DefPoss | Sums to 0.75% more than OffPoss league-wide (different convention) | Validate on OffPoss and game totals | None |
| 2026-11-08 | pbpstats game totals, 2024-25 games of 2025-03-25 | pbpstats points are lower than the play-by-play final score in 8 games that day; our totals match the final scores | None needed (validation-only source) | Shows up as point mismatches in `reports/validation_2024-25.md`, not a parser error |
| 2026-11-08 | Play-by-play for 4 of 7,230 games, 2020-21 to 2025-26 | 2 games have a substitution missing from the source (6 players on the floor); 2 OT periods have a starter we can't identify even with pbpstats' lineups | Games dropped; listed in `data/processed/failed_games_<season>.csv` and each season's validation report | Negligible (0.06% of games) |
