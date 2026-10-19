"""Stabilized ("padded") rates and per-stat padding k (analysis plan section 4.4).

    stable_rate = (m + k * p_lg) / (n + k)

is the posterior mean under a Beta(k p_lg, k (1 - p_lg)) prior. k is estimated three ways:
  1. beta-binomial maximum likelihood on player-season (makes, attempts): k = alpha + beta
  2. split-half reliability on trial-level data: reliability(n) = n / (n + k), so k is the
     sample size at which reliability is 0.5
  3. out-of-sample: the k that best predicts season N+1 rates from season N rates

Run as a module to estimate k for every stat in STATS and write
data/processed/stabilize_k.csv and reports/stabilize_k.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import betaln, expit, logit


def stable_rate(m, n, p_lg, k):
    return (np.asarray(m, float) + k * p_lg) / (np.asarray(n, float) + k)


def league_mean(m, n) -> float:
    return float(np.sum(m) / np.sum(n))


# --------------------------------------------------------------------------- method 1

def fit_beta_binomial(m, n) -> tuple[float, float]:
    """MLE of the beta-binomial prior. Returns (p_lg, k)."""
    m, n = np.asarray(m, float), np.asarray(n, float)
    keep = n > 0
    m, n = m[keep], n[keep]

    def nll(theta):
        p, k = expit(theta[0]), np.exp(theta[1])
        a, b = p * k, (1 - p) * k
        return -np.sum(betaln(m + a, n - m + b) - betaln(a, b))

    p0 = np.clip(m.sum() / n.sum(), 1e-3, 1 - 1e-3)
    res = minimize(nll, x0=[logit(p0), np.log(100.0)], method="Nelder-Mead",
                   options={"xatol": 1e-6, "fatol": 1e-8, "maxiter": 2000})
    return float(expit(res.x[0])), float(np.exp(res.x[1]))


# --------------------------------------------------------------------------- method 2

def split_half_k(trials: pd.DataFrame, min_trials: int, reps: int, seed: int,
                 player_col: str = "player_id", outcome_col: str = "made") -> dict:
    """Split each player's trials randomly in half, correlate half-rates across players.

    Under the beta-binomial model the half-sample reliability is r = n_h / (n_h + k), with
    n_h the harmonic-mean half size, so k = n_h (1 - r) / r.
    """
    rng = np.random.default_rng(seed)
    t = trials[[player_col, outcome_col]]
    size = t.groupby(player_col)[outcome_col].transform("size")
    t = t[size >= min_trials]
    pid = t[player_col].to_numpy()
    if len(np.unique(pid)) < 20:
        return {"k": np.nan, "r_half": np.nan, "n_half": np.nan, "players": 0}
    y = t[outcome_col].to_numpy(float)
    size = size[size >= min_trials].to_numpy()
    rs, nhs = [], []
    for _ in range(reps):
        order = pd.Series(rng.random(len(t))).groupby(pid).rank(method="first").to_numpy()
        half = (order > size / 2).astype(int)
        g = (pd.DataFrame({"p": pid, "h": half, "y": y})
             .groupby(["p", "h"]).y.agg(["mean", "size"]).unstack("h"))
        rs.append(np.corrcoef(g["mean"][0], g["mean"][1])[0, 1])
        nhs.append(g["size"].size / np.sum(1 / g["size"].to_numpy()))
    r, nh = float(np.mean(rs)), float(np.mean(nhs))
    k = nh * (1 - r) / r if r > 0 else np.inf
    return {"k": float(k), "r_half": r, "n_half": nh, "players": len(np.unique(pid))}


# --------------------------------------------------------------------------- method 3

def oos_k(totals: pd.DataFrame, k_grid: list[float], season_order: list[str]) -> dict:
    """Choose k minimizing next-season prediction error.

    `totals` has columns player_id, season, m, n. Error is the attempt-weighted squared
    error against season N+1's observed rate; N+1's own binomial noise adds the same
    constant for every k, so it doesn't move the argmin.
    """
    idx = {s: i for i, s in enumerate(season_order)}
    t = totals[totals.n > 0].copy()
    t["si"] = t.season.map(idx)
    nxt = t.assign(si=t.si - 1)
    pair = t.merge(nxt, on=["player_id", "si"], suffixes=("", "_next"))
    plg = t.groupby("season").apply(lambda d: d.m.sum() / d.n.sum(), include_groups=False)
    pair["p_lg"] = pair.season.map(plg)
    y = pair.m_next / pair.n_next
    w = pair.n_next
    errs = []
    for k in k_grid:
        pred = stable_rate(pair.m, pair.n, pair.p_lg, k)
        errs.append(float(np.sum(w * (y - pred) ** 2) / w.sum()))
    best = int(np.argmin(errs))
    return {"k": float(k_grid[best]), "pairs": len(pair),
            "curve": dict(zip(map(float, k_grid), errs, strict=True)),
            "at_edge": best in (0, len(k_grid) - 1)}


# --------------------------------------------------------------------------- driver

def _oreb_opportunities(t: pd.DataFrame, kind: str) -> pd.Series:
    """On-court offensive-rebound opportunities on `kind` ("TwoPt"/"ThreePt") misses.

    Backed out as rebounds / rebound%. Players with no such rebounds have no % to invert,
    so they get on-court possessions x the season's opportunities-per-possession rate.
    """
    reb, pct = t[f"Off{kind}Rebounds"], t[f"Off{kind}ReboundPct"]
    has = (reb > 0) & (pct > 0)
    backed = reb[has] / pct[has]
    rate = backed.sum() / t.OffPoss[has].sum()
    return backed.reindex(t.index).fillna(t.OffPoss * rate)


def season_counts(tot: pd.DataFrame) -> pd.DataFrame:
    """Per player-season (m, n) for every stat from pbpstats totals (zeros are omitted
    by the API, hence the fillna)."""
    num = tot.select_dtypes("number").columns.drop("EntityId")
    t = tot[["EntityId", *num]].fillna(0).groupby("EntityId").sum()
    fg_oreb = t.OffTwoPtRebounds + t.OffThreePtRebounds
    opp = _oreb_opportunities(t, "TwoPt") + _oreb_opportunities(t, "ThreePt")
    fga = t.FG2A + t.FG3A
    stats = {
        "fg3": (t.FG3M, t.FG3A),
        "ft": (t.FtPoints, t.FTA),
        "fg2_rim": (t.AtRimFGM, t.AtRimFGA),
        "fg2_nonrim": (t.FG2M - t.AtRimFGM, t.FG2A - t.AtRimFGA),
        "oreb": (fg_oreb, opp.round()),
        "tov": (t.Turnovers, fga + (0.44 * t.FTA).round() + t.Turnovers),
        # FTA / (FTA + FGA): a bounded monotone transform of FTA/FGA so it can be padded
        "ftr": (t.FTA, t.FTA + fga),
    }
    out = []
    for name, (m, n) in stats.items():
        out.append(pd.DataFrame({"player_id": t.index, "stat": name, "m": m.to_numpy(),
                                 "n": n.to_numpy()}))
    return pd.concat(out, ignore_index=True)


def shot_trials(shots: pd.DataFrame) -> dict[str, pd.DataFrame]:
    s = shots.rename(columns={"shooter_id": "player_id"})
    rim = s.area == "Restricted Area"
    return {"fg3": s[s.value == 3], "ft": s[s.value == 1],
            "fg2_rim": s[(s.value == 2) & rim], "fg2_nonrim": s[(s.value == 2) & ~rim]}


def main() -> None:
    from src import config, ingest

    cfg = config.load()
    sc = cfg["stabilize"]
    primary = cfg["seasons"]["primary"]
    seasons = [*cfg["seasons"]["totals_history"], primary]
    counts = pd.concat([season_counts(ingest.pbpstats_totals(s)).assign(season=s)
                        for s in seasons], ignore_index=True)
    counts = counts[counts.n > 0]
    counts.to_parquet(config.PROCESSED / "stat_counts_by_season.parquet", index=False)
    shots = pd.read_parquet(config.PROCESSED / f"shots_{primary}.parquet")
    trials = shot_trials(shots)

    rows, curves = [], []
    for stat, c in counts.groupby("stat", sort=False):
        bb = [fit_beta_binomial(d.m, d.n) for _, d in c.groupby("season")]
        oos = oos_k(c, sc["k_grid"], seasons)
        cur = c[c.season == primary]
        sh = (split_half_k(trials[stat], sc["split_half_min_trials"], sc["split_half_reps"],
                           cfg["seed"]) if stat in trials else {"k": np.nan, "r_half": np.nan})
        ks = [x for x in (np.median([k for _, k in bb]), sh["k"], oos["k"]) if np.isfinite(x)]
        rows.append({
            "stat": stat,
            "p_lg_primary": league_mean(cur.m, cur.n),
            "k_beta_binomial": float(np.median([k for _, k in bb])),
            "k_bb_range": f"{min(k for _, k in bb):.0f}-{max(k for _, k in bb):.0f}",
            "k_split_half": sh["k"], "r_half": sh["r_half"],
            "k_oos": oos["k"], "oos_at_grid_edge": oos["at_edge"],
            "k_chosen": float(np.exp(np.mean(np.log(ks)))),
            "max_ratio": float(max(ks) / min(ks)),
        })
        curves += [{"stat": stat, "k": k, "wmse": e} for k, e in oos["curve"].items()]
    res = pd.DataFrame(rows)
    res.to_csv(config.PROCESSED / "stabilize_k.csv", index=False)
    pd.DataFrame(curves).to_csv(config.PROCESSED / "stabilize_oos_curves.csv", index=False)

    lines = [
        "# Stabilization padding k (plan section 4.4)",
        "",
        f"Season totals: {seasons[0]} to {primary} (api.pbpstats.com). Split-half uses "
        f"{primary} trial-level shots from our parse (players with ≥"
        f"{sc['split_half_min_trials']} attempts).",
        "",
        "`k_chosen` is the geometric mean of the available estimates. `max_ratio` is the "
        "largest/smallest estimate; above ~2 the methods disagree and the stat needs a "
        "closer look before it feeds downstream tests.",
        "",
        res.to_markdown(index=False, floatfmt=".3g"),
        "",
        "Definitions: `oreb` = player FG offensive rebounds / FG-miss opportunities on court "
        "(opportunities backed out of pbpstats rebound %, imputed from possessions when the "
        "player has none of a type); `tov` = TOV / (FGA + 0.44 FTA + TOV); "
        "`ftr` = FTA / (FTA + FGA).",
    ]
    (config.REPORTS / "stabilize_k.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
