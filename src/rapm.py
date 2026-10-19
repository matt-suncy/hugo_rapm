"""Ridge RAPM: stint aggregation, design matrix, fit, grouped CV, bootstrap.

Model: for stint s, y_s = 100 * points / possessions,
    y_s = mu + sum_{p in offense} o_p + sum_{q in defense} d_q + e_s,  weight = possessions.
`d_q` is points *allowed*, so reported defense is -d_q (positive = good), and
total = offense + defense. mu is the unpenalized league-average intercept.

The solve uses normal equations (p ~ 1,200 columns, so dense p x p is cheap):
    (X'WX + lam I) b = X'W (y - mu - X b0)  ->  beta = b0 + b
With b0 = 0 this is standard RAPM; a nonzero b0 gives prior-informed RAPM (Test 3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.linalg as sla
import scipy.sparse as sp

OFF = [f"off{i}" for i in range(1, 6)]
DEF = [f"def{i}" for i in range(1, 6)]
STAT_COLS = ["poss", "points", "fga2", "fgm2", "fga3", "fgm3", "fta", "ftm", "tov",
             "oreb", "oreb_available"]


def stints(poss: pd.DataFrame, exclude_garbage: bool = False,
           value_col: str = "points") -> pd.DataFrame:
    """Aggregate possession rows to (game, offense five, defense five) stints.

    `value_col` lets Test 2 swap in luck-adjusted points. Stints with zero possessions
    (e.g. only a technical FT) are dropped.
    """
    if exclude_garbage:
        poss = poss[~poss.garbage_time]
    cols = list(dict.fromkeys([*STAT_COLS, value_col]))
    st = (poss.groupby(["game_id", "off_team", *OFF, *DEF], sort=False)[cols]
          .sum().reset_index())
    st = st[st.poss > 0].reset_index(drop=True)
    st["y"] = 100 * st[value_col] / st.poss
    return st


class Design:
    """Sparse design matrix with player <-> column bookkeeping."""

    def __init__(self, st: pd.DataFrame, players: np.ndarray | None = None) -> None:
        offp = st[OFF].to_numpy()
        defp = st[DEF].to_numpy()
        self.players = np.unique(np.concatenate([offp.ravel(), defp.ravel()])) \
            if players is None else np.asarray(players)
        idx = {p: i for i, p in enumerate(self.players)}
        n, m = len(st), len(self.players)
        oi = np.vectorize(idx.__getitem__)(offp)
        di = np.vectorize(idx.__getitem__)(defp) + m
        rows = np.repeat(np.arange(n), 10)
        cols = np.concatenate([oi, di], axis=1).ravel()
        self.X = sp.csr_matrix((np.ones(n * 10), (rows, cols)), shape=(n, 2 * m))
        self.y = st.y.to_numpy(float)
        self.w = st.poss.to_numpy(float)
        self.groups = st.game_id.to_numpy()
        self.m = m


def solve(X: sp.csr_matrix, y: np.ndarray, w: np.ndarray, lam: float,
          b0: np.ndarray | None = None, penalty: np.ndarray | None = None
          ) -> tuple[np.ndarray, float]:
    """Weighted ridge with unpenalized intercept, optional prior mean b0 and per-column
    penalty multipliers. Returns (beta, intercept)."""
    mu = float(np.average(y, weights=w))
    r = y - mu
    if b0 is not None:
        r = r - X @ b0
    Xw = X.multiply(w[:, None]).tocsr()
    A = (X.T @ Xw).toarray()
    A[np.diag_indices_from(A)] += lam * (penalty if penalty is not None else 1.0)
    rhs = Xw.T @ r
    b = sla.solve(A, rhs, assume_a="pos")
    return (b if b0 is None else b0 + b), mu


def coefficients(d: Design, beta: np.ndarray) -> pd.DataFrame:
    off, dfn = beta[: d.m], -beta[d.m:]
    return pd.DataFrame({"player_id": d.players, "off": off, "def": dfn, "total": off + dfn})


def fit(st: pd.DataFrame, lam: float, **kw) -> tuple[pd.DataFrame, float]:
    d = Design(st)
    beta, mu = solve(d.X, d.y, d.w, lam, **kw)
    return coefficients(d, beta), mu


def cv_lambda(st: pd.DataFrame, grid: list[float], folds: int, seed: int) -> pd.DataFrame:
    """Grouped (by game) K-fold CV; returns weighted MSE of points/100 per lambda."""
    d = Design(st)
    rng = np.random.default_rng(seed)
    games = np.unique(d.groups)
    fold_of = dict(zip(games, rng.permutation(len(games)) % folds, strict=True))
    f = np.vectorize(fold_of.__getitem__)(d.groups)
    out = []
    for lam in grid:
        sse = wsum = 0.0
        for k in range(folds):
            tr, te = f != k, f == k
            beta, mu = solve(d.X[tr], d.y[tr], d.w[tr], lam)
            pred = mu + d.X[te] @ beta
            sse += float(np.sum(d.w[te] * (d.y[te] - pred) ** 2))
            wsum += float(d.w[te].sum())
        out.append({"lambda": lam, "wmse": sse / wsum})
    return pd.DataFrame(out)


def game_bootstrap(st: pd.DataFrame, lam: float, reps: int, seed: int,
                   track: list[int] | None = None) -> pd.DataFrame:
    """Resample games with replacement, refit at fixed lambda.

    Returns long format (rep, player_id, off, def, total) for `track` players (all if None).
    Implemented by multiplying stint weights by each game's bootstrap count, which is
    equivalent to stacking duplicated games and avoids rebuilding X.
    """
    d = Design(st)
    rng = np.random.default_rng(seed)
    games, inv = np.unique(d.groups, return_inverse=True)
    keep = np.isin(d.players, track) if track is not None else np.ones(d.m, bool)
    res = []
    for rep in range(reps):
        counts = rng.multinomial(len(games), np.full(len(games), 1 / len(games)))
        w = d.w * counts[inv]
        nz = w > 0
        beta, _ = solve(d.X[nz], d.y[nz], w[nz], lam)
        c = coefficients(d, beta)[keep]
        c.insert(0, "rep", rep)
        res.append(c)
    return pd.concat(res, ignore_index=True)
