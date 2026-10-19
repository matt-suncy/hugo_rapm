# Analysis Plan: Why Hugo Gonzalez's RAPM Disagrees with DARKO and LEBRON

## 1. Context

Hugo Gonzalez (BOS, SG/wing) shows a large gap between descriptive plus-minus and predictive/box-informed impact metrics (source: nbarapm.com):

| Metric | Off | Def | Total | Total rank |
|---|---|---|---|---|
| DARKO | -1.8 | +1.1 | -0.7 | 261 |
| LEBRON | -2.0 | +1.8 | -0.1 | 182 |
| Time-decay RAPM | +1.9 | +1.4 | +3.4 | 33 |
| 1Y RAPM | +2.0 | +1.6 | +3.6 | 23 |

Observations driving this plan:

- **The gap is almost entirely offensive** (~4 pts/100). Defense roughly agrees across metrics.
- 1Y–5Y RAPM windows are nearly identical, so the effective sample is roughly one season (his 2025-26 rookie year, plus any 2026-27 games to date).
- RAPM shrinks toward 0 (league average). LEBRON/DARKO anchor to box-score-informed estimates. Zero-centered shrinkage can only attenuate, never flip the sign; a negative-centered prior can.

## 2. Goal

Determine how much of the gap comes from each of these competing explanations, and produce a forecast that can be checked during the 2026-27 season:

| ID | Hypothesis | Short name |
|---|---|---|
| H1 | Small sample / sampling noise, amplified by selection (winner's curse) | Noise |
| H2 | Shooting luck (teammate 3P%/FT% hot, opponent 3P% cold while he's on) | Luck |
| H3 | Real off-ball value box scores miss (offensive rebounding, cutting, screening, turnover avoidance) | Real non-box value |
| H4 | Prior location/strength: box prior is negative and heavily weighted | Prior |
| H5 | Lineup context: collinearity with teammates, fit/interaction effects RAPM attributes to him | Context |
| H6 | Minutes selection: impact concentrated in favorable minutes that won't scale with a bigger role | Scaling |

These are not mutually exclusive. The deliverable is a decomposition with uncertainty, not a single winner.

## 3. Ground rules for the agent

- **Never fabricate data.** If a source is unavailable, paywalled, or blocked, log it in `reports/data_gaps.md` and use the documented fallback.
- Respect site terms and rate limits. Cache all raw pulls to disk; never re-download what's cached.
- Pin seasons explicitly: `2025-26` regular season (primary), `2026-27` regular season to date (secondary/monitoring).
- Every test must end with a **decision rule** result: state which branch fired and what it implies (see section 6).
- Set random seeds. All numbers in the final report must be reproducible from `make all` (or an equivalent single entry point).

## 4. Data

### 4.1 Required

| Dataset | Use | Suggested source | Notes |
|---|---|---|---|
| Play-by-play + on-court lineups, 2025-26 and 2026-27 | Build stint/possession matrix | `pbpstats` (Python) or `nba_api` PlayByPlayV3 + rotation data | Need 10 players on court per possession |
| Possession-level outcomes | Points, plus event detail for factors | Derived from PBP | Tag each possession: points, shot type, FTs, turnover, OREB |
| Shot-level data | Luck adjustment | `nba_api` ShotChartDetail | Shooter, location, zone, make/miss |
| Player FT% / 3P% career and season | Luck adjustment | `nba_api` | Use for shooter-skill baselines |
| Box score totals per player-season | Box prior construction | `nba_api` / Basketball Reference | Per-100 rates |
| Published metrics (DARKO, LEBRON, nbarapm RAPM) | Validation + monitoring | nbarapm.com, darko.app, BBall Index | Snapshots with dates; scraping may be restricted, so manual CSV export is an acceptable fallback |

### 4.2 Optional / may be unavailable

| Dataset | Use | Fallback if unavailable |
|---|---|---|
| Per-shot closest-defender distance | Shot-quality luck model | Public data generally only has **aggregated** closest-defender buckets (0–2, 2–4, 4–6, 6+ ft) by player/team via `nba_api` shot dashboards. Use those buckets for team-level expected 3P%, or fall back to zone + shooter-skill model |
| Synergy play-type data | Test 6 | `nba_api` SynergyPlayTypes endpoint if it returns data; otherwise skip and document |
| nbarapm six-factor breakdown | Cross-check Test 5 | Compute our own factor RAPM (Test 5 does this anyway) |

### 4.3 Core data structure

Build a **possession-level** table (preferred over stints for flexibility):

```
possession_id, game_id, season, period, clock, score_margin,
off_team, def_team, off_players[5], def_players[5],
points, fga2, fgm2, fga3, fgm3, fta, ftm, tov, oreb_available, oreb,
shooter_id (if shot), shot_zone, garbage_time_flag
```

Then aggregate to stints for RAPM fitting: design matrix X with +1 for each offensive player's offense column, +1 for each defensive player's defense column (separate O and D coefficients per player), target = points per 100 possessions, weight = possessions.

### 4.4 Shared method: stabilized ("padded") rates

Reference: Basketball Index, "Creating More Predictive Stats" (https://www.bball-index.com/creating-more-predictive-stats/). Their Stable Stats add a fixed number of league-average "fake" attempts to each player's sample, so small samples are pulled toward average and large samples barely move. Each stat gets its own padding amount, because stats stabilize at different rates (e.g., blocks much faster than 3P%). The article does **not** publish its padding values (its 100-attempt example is explicitly made up), so we must estimate our own.

**Formula.** For a rate stat with makes `m`, attempts `n`, league mean `p_lg`, and padding `k`:

```
stable_rate = (m + k * p_lg) / (n + k)
```

This is exactly the posterior mean of a beta-binomial model with prior Beta(k·p_lg, k·(1−p_lg)). Implement it in `src/stabilize.py` and use it everywhere this plan says "shrunk" or "stabilized."

**Estimating `k` per stat** (do at least two methods and check they roughly agree):
1. *Beta-binomial fit:* fit Beta(α, β) to player-season makes/attempts by maximum likelihood (or method of moments correcting for binomial noise); then `k = α + β`.
2. *Split-half reliability:* for players with enough attempts, randomly split each player's attempts into halves, compute the correlation of the halves' rates across players, and find the attempt count `n*` where reliability r = 0.5 (Spearman-Brown). Then `k ≈ n*`.
3. *Out-of-sample check:* choose `k` that minimizes error predicting season N+1 rate from season N (weighted by N+1 attempts) over 2018-19 → 2024-25.

**Report `k` for:** 3P%, FT%, 2P% (rim and non-rim if available), OREB%, TOV%, FTr, and any box rate used in Test 3.

**Optional refinement:** pad toward a role-appropriate mean (e.g., position, or rookie wings) rather than the league mean, and compare out-of-sample error against the league-mean version. Keep whichever predicts better.

**Conceptual tie-in for the report:** ridge RAPM is the same idea applied to impact. It effectively pads every player with league-average (zero) possessions. Box-prior metrics instead pad toward a box-score estimate. That framing connects this section to Test 3.

## 5. Tests

### Test 0 — Replicate baseline RAPM

**Purpose:** Prove the pipeline is sound before trusting any downstream result.

**Method**
1. Fit ridge RAPM (separate O/D coefficients, intercept = league average) on 2025-26, weighted by possessions.
2. Choose λ by cross-validation on held-out games (grouped by game, not by stint, to avoid leakage).
3. Optionally fit a time-decay version (exponential weights by game date) to compare against nbarapm's timedecay RAPM.

**Outputs**
- Hugo's O/D/total coefficients and league rank.
- Correlation of our coefficients vs nbarapm's for all players with ≥ 500 possessions.

**Acceptance:** Correlation with published RAPM ≥ ~0.85 and Hugo's total within ~1.5 pts of the published value. If not, debug lineup parsing before continuing. Exact match is not expected (different λ, priors, data cleaning).

---

### Test 1 — Uncertainty and winner's curse (H1)

**Method**
1. **Bootstrap SEs.** Resample games with replacement (≥ 500 reps), refit ridge with fixed λ, record Hugo's O/D/total. Report the 80% and 95% percentile intervals. *Do not use analytic OLS standard errors; ridge estimates are biased by design, so those SEs are misleading.*
2. **λ sensitivity.** Refit across a grid of λ (e.g., 0.25×, 0.5×, 1×, 2×, 4× the CV-optimal value). Plot Hugo's estimate vs λ. Large swings indicate fragility.
3. **Winner's curse check.** Among players with similar possession counts to Hugo (±30%), compute how often a player ranked in the top ~10% of RAPM in season N stays there in season N+1 (use prior seasons, e.g., 2018-19 → 2024-25). This gives an empirical regression-to-the-mean rate for "low-minute RAPM standouts."
4. **Split-half reliability.** Randomly split 2025-26 games into halves, fit RAPM on each, correlate player coefficients for low-minute players. Repeat ~100 times.

**Outputs:** Interval plot, λ-sensitivity plot, historical persistence rate, split-half correlation.

---

### Test 2 — Shot-quality luck adjustment, no box prior (H2 vs H4)

This is the key experiment: it separates **luck** from **prior** as the cause of the gap.

**Method**
1. **Expected 3P model.** For each 3PA, estimate make probability:
   - *Shooter skill:* the shooter's **stabilized 3P%** (section 4.4), computed **excluding the current game** (or, more strictly, from data before that game) so a player's own outcome doesn't leak into his expected value.
   - *Preferred:* stabilized shooter skill × shot context (corner vs above-break, catch-and-shoot vs pull-up if available, defender-distance bucket if available). Fit as a logistic model with logit(stable 3P%) as an offset or feature.
   - *Fallback:* stabilized 3P% × zone adjustment.
   - Validate calibration on held-out shots (reliability plot, Brier score). Compare against using raw 3P% as shooter skill. Stabilized should calibrate better for low-volume shooters; if it doesn't, investigate `k`.
2. **Expected FT.** Replace each FT make/miss with the shooter's stabilized FT% (its own `k`, which should be much smaller than 3P%'s).
3. **Adjust makes, not attempts.** Keep every shot attempt in the data. Replace each 3P/FT outcome with its expected value (expected points). Do **not** filter to only open shots, and do not adjust shot generation; creating open looks is a real skill.
4. Apply the adjustment to **both** teams' shooting (teammates' 3s while he's on, and opponents' 3s while he's on).
5. Refit ridge RAPM on luck-adjusted points (same λ procedure, **no box prior**).
6. Diagnostics: on-court team 3P% vs expected 3P% with Hugo on/off; opponent 3P% vs expected with Hugo on/off.

**Outputs:** Hugo's luck-adjusted O/D/total with bootstrap intervals; on/off actual-vs-expected shooting table.

---

### Test 3 — Prior location vs strength (H4)

**Purpose:** Quantify the earlier back-of-envelope argument: is LEBRON low because its prior is *negative* (location), *heavily weighted* (strength), or both?

**Method**
1. Build a simple box prior: regress multi-year RAPM on per-100 box stats for established players (BPM-style; a handful of features is fine: usage, TS%, AST%, TOV%, OREB%, DREB%, STL%, BLK%, 3PA rate, FTr). Use **stabilized** versions of the rate features (section 4.4) so low-minute players' prior isn't driven by box-score noise. Produce a box-based O and D estimate for Hugo with both raw and stabilized inputs and report the difference.
2. Fit **prior-informed RAPM**: ridge with penalty on (β − β_prior) instead of β, i.e., shrink toward the box estimate. Equivalent trick: subtract the prior's contribution from the target, fit standard ridge, then add the prior back.
3. Fit a 2D grid: prior mean scaled by {0, 0.5, 1.0} × prior strength λ_prior across a range. Plot Hugo's offensive estimate as a surface/heatmap.
4. Solve for the implied data weight `w` in the normal-normal approximation `estimate = w·x + (1−w)·m`, where x is his raw/low-λ on/off signal and m is the prior mean. Report the `w` that reproduces published LEBRON offense (≈ −2.0) for plausible m values.
5. Run steps 2–4 on both raw and luck-adjusted (Test 2) targets.

**Outputs:** Hugo's box-prior O/D estimate, heatmap of estimate vs (prior location, prior strength), implied `w` table.

**Note for the report:** DARKO is mostly a box-score model with plus-minus as a secondary input, so "prior strength" is an imperfect description of it. Box stats are also data that accumulate every game. Treat Test 3 as primarily an explanation of LEBRON; describe DARKO as "measuring a different thing."

---

### Test 4 — Lineup context and collinearity (H5)

**Method**
1. **Teammate overlap.** For each teammate, compute the share of Hugo's possessions they shared. List his top 10 five-man lineups by possessions with net rating.
2. **Collinearity diagnostics.** Compute correlation between Hugo's on-court indicator and each teammate's, and the condition number of the BOS-player submatrix. Flag any teammate with overlap correlation > ~0.7.
3. **λ sensitivity revisited.** If Hugo's estimate moves strongly with λ (Test 1 step 2) *and* overlap is concentrated, collinearity is likely contributing.
4. **Leave-one-teammate-out.** For each high-overlap teammate, drop possessions where both played together, refit, and check Hugo's estimate. Large drops suggest credit-sharing issues.
5. **Interaction check (fit effects).** Add pairwise interaction terms for Hugo × top-3 teammates (with strong regularization) and see whether Hugo's main effect shrinks.

**Outputs:** Overlap table, lineup table, leave-one-out table, interaction-model comparison.

---

### Test 5 — Factor decomposition (H3 vs H2)

**Purpose:** Find *where* his offensive value comes from. Factors stabilize at very different rates, which is the payoff.

**Method**
1. Compute per-possession factor outcomes for the offense while he's on/off:
   - Shooting efficiency (eFG% on shot-ending possessions)
   - Turnover rate (TOV per possession)
   - Offensive rebound rate (OREB / available OREB opportunities)
   - Free throw rate (FTA or FTM per FGA)
   - Optionally split shooting into 2P and 3P (gives a "six factor" style view)
2. Fit **factor-level RAPM**: one ridge model per factor, using the appropriate denominator (e.g., OREB model only on missed-shot possessions). Convert each factor coefficient to points per 100 so they roughly sum to offensive RAPM.
3. Repeat for defense for completeness.
4. Cross-check against nbarapm's 6factor tab if accessible.
5. Look at Hugo's own box stats for those factors (e.g., his personal OREB% vs the team's OREB% with him on). If team OREB% rises more than his own boards explain, that suggests crashing/boxing-out value the box score misses. Use stabilized versions of his personal rates (section 4.4) alongside raw ones.
6. Use the per-factor `k` values from section 4.4 to quantify stability: report, for each factor, how many possessions/opportunities Hugo has relative to that factor's `k`. Factors where his sample is well above `k` deserve more trust than factors where it's below.

**Outputs:** Factor contribution bar chart (O and D), stability notes per factor, personal-vs-team factor comparison.

---

### Test 6 — Play-type profile (H3), optional

**Method:** If Synergy play-type data is available via `nba_api`, pull Hugo's frequency and points-per-possession by play type (cut, putback, spot-up, transition, P&R ball handler, etc.) with league percentiles.

**Caveat:** This describes *his own* possessions, so it's closer to box-score information than on/off. Use it to corroborate a mechanism (e.g., elite cutting/putback efficiency on low volume), not as an impact estimate.

**Outputs:** Play-type table with percentiles, or a logged data gap.

---

### Test 7 — Minutes context and scaling (H6)

**Method**
1. **Context splits** (raw and luck-adjusted on/off, plus RAPM refits where sample allows):
   - With vs without BOS's top-5 minutes players
   - By opponent lineup quality (average opponent RAPM or minutes-share of the opposing five; bucket into terciles)
   - Excluding garbage time (define with a parameter; e.g., margin ≥ 25 in Q4 or ≥ 20 in final 5 minutes, and document the choice). NOTE that garbage time should follow RAPM standards i.e. minutes that were deemed garbage time can be reverted if the game ends up being close.
   - By period/quarter
2. **Report possessions per split**; flag any split with too few possessions to interpret.
3. **Scaling simulation.** Simulate how his RAPM estimate evolves with more possessions under three "true effect" scenarios:
   - S1: true O impact = current RAPM (~+2)
   - S2: true O impact = LEBRON/DARKO level (~−2)
   - S3: true impact degrades with role, e.g., his effect vs starter-heavy opponents applies to marginal minutes

   Approach: take the fitted league model, inject Hugo's assumed true effect, generate synthetic possession outcomes for a projected 2026-27 workload (e.g., 15, 20, 25 MPG) with realistic lineup assignment, refit ridge, and record the distribution of his estimated RAPM. Repeat ≥ 200 times per scenario.
4. Translate into a **prediction**: by what possession count should RAPM have clearly separated S1 from S2?

**Outputs:** Split table, simulation fan charts per scenario, "possessions needed to discriminate" estimate.

---

### Test 8 — Monitoring during 2026-27 (all hypotheses)

**Method**
1. Weekly (or every ~10 games) snapshot of Hugo's DARKO, LEBRON, and nbarapm RAPM with retrieval date; store as an append-only CSV.
2. Recompute our own RAPM, luck-adjusted RAPM, and bootstrap interval on the updated data.
3. Track minutes per game and the context splits from Test 7.
4. Compare trajectories against Test 7 scenario predictions.

**Expected signatures**
- If RAPM is right: LEBRON drifts up (its plus-minus component gains weight), RAPM interval tightens around a positive value. DARKO may stay low if his box stats stay weak.
- If predictive metrics are right: RAPM falls toward ~0 or below as the interval tightens.
- If scaling concern is right: per-possession impact falls as minutes and opponent quality rise.

**Outputs:** `data/monitoring/metrics_snapshots.csv`, trajectory chart, short update note per snapshot. (Scheduling this as a recurring job is out of scope for the coding agent unless requested.)

## 6. Decision rules

Each test must report which branch fired.

| Test | Result | Interpretation |
|---|---|---|
| 1 | 80% interval comfortably above 0, stable across λ, decent split-half reliability | Noise is not the main story; investigate mechanisms |
| 1 | Interval spans 0, or estimate swings strongly with λ, or historical persistence of similar standouts is low | Noise/winner's curse is substantial; treat RAPM as weak evidence |
| 2 | Luck-adjusted RAPM stays near +3 | Gap is driven by prior/model differences, not shooting luck |
| 2 | Luck-adjusted RAPM collapses toward 0 | Gap was mostly shooting luck |
| 2 | Partial drop | Report the share of the gap explained by luck |
| 3 | Box-prior offense strongly negative and implied `w` low | Both prior location and strength drive LEBRON's number |
| 3 | Box prior near 0 but LEBRON still low | Something else in LEBRON (luck adjustment, role/rookie adjustments) is responsible |
| 4 | Estimate drops sharply in leave-one-out or interaction model | Credit-sharing/fit effects inflate his RAPM |
| 4 | Estimate robust | Context is not a major driver |
| 5 | Offensive value concentrated in team eFG% | Be suspicious; slow-stabilizing and luck-prone |
| 5 | Value concentrated in OREB% / TOV% | More likely real, stabilizes faster, and explains why box metrics miss it |
| 7 | Impact holds vs starter-heavy opponents and outside garbage time | Likely to scale with a bigger role |
| 7 | Impact concentrated in bench-vs-bench or garbage time | Expect per-minute impact to fall as minutes rise |

## 7. Deliverables

```
hugo_rapm/
├── README.md                     # how to run, data sources, retrieval dates
├── Makefile (or run_all.py)      # single entry point
├── config.yaml                   # seasons, player IDs, λ grid, garbage-time rule, seeds
├── data/
│   ├── raw/                      # cached pulls, never edited
│   ├── processed/                # possession + stint tables (parquet)
│   └── monitoring/
├── src/
│   ├── ingest.py                 # PBP, lineups, shots, box scores
│   ├── possessions.py            # possession table + factor tagging
│   ├── rapm.py                   # ridge fit, CV, prior-informed variant, bootstrap
│   ├── stabilize.py              # padded rates + k estimation (section 4.4)
│   ├── luck.py                   # expected 3P / FT models
│   ├── box_prior.py
│   ├── context.py                # overlap, splits, leave-one-out, interactions
│   ├── factors.py
│   └── simulate.py
├── notebooks/                    # one per test, thin wrappers over src/
└── reports/
    ├── final_report.md           # summary, decision-rule table, charts
    └── data_gaps.md
```

**Final report structure**
1. One-paragraph answer: estimated share of the gap attributable to noise, luck, prior, context, and real non-box value (with uncertainty; ranges are fine).
2. Decision-rule table with the branch that fired for each test.
3. Key charts: bootstrap interval, λ sensitivity, raw vs luck-adjusted RAPM, prior heatmap, factor decomposition, scaling fan chart.
4. Falsifiable predictions for 2026-27 with the possession count at which they should be checkable.
5. Limitations and data gaps.

## 8. Suggested order of work

1. Ingest + possession table + Test 0 (blocks everything else), plus `k` estimation from section 4.4 (needed by Tests 2, 3, 5)
2. Test 1 (cheap, frames how much to trust everything after)
3. Test 2 (key experiment)
4. Tests 5 and 4 (mechanism and context)
5. Test 3 (needs Test 2 outputs)
6. Test 7 simulation
7. Test 6 if data is available
8. Final report, then Test 8 monitoring setup
