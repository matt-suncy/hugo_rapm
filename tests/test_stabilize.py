import numpy as np
import pandas as pd

from src import stabilize as S


def _bb(k=150, p=0.36, players=600, seed=0):
    rng = np.random.default_rng(seed)
    true = rng.beta(p * k, (1 - p) * k, players)
    n = rng.integers(50, 600, players)
    return true, n, rng.binomial(n, true)


def test_stable_rate_formula():
    assert S.stable_rate(10, 20, 0.5, 20) == 0.5
    assert np.isclose(S.stable_rate(30, 100, 0.36, 100), (30 + 36) / 200)
    assert S.stable_rate(0, 0, 0.4, 50) == 0.4


def test_beta_binomial_recovers_k():
    _, n, m = _bb()
    p, k = S.fit_beta_binomial(m, n)
    assert abs(p - 0.36) < 0.01
    assert 100 < k < 225


def test_split_half_recovers_k():
    rng = np.random.default_rng(1)
    true, n, _ = _bb(players=400, seed=1)
    trials = pd.DataFrame({
        "player_id": np.repeat(np.arange(len(n)), n),
        "made": rng.random(n.sum()) < np.repeat(true, n),
    })
    out = S.split_half_k(trials, min_trials=100, reps=5, seed=2)
    assert 80 < out["k"] < 280


def test_oos_k_prefers_moderate_padding():
    rng = np.random.default_rng(3)
    k, p, players = 150, 0.36, 500
    true = rng.beta(p * k, (1 - p) * k, players)
    rows = []
    for s in ("a", "b", "c"):
        n = rng.integers(50, 600, players)
        rows.append(pd.DataFrame({"player_id": np.arange(players), "season": s,
                                  "m": rng.binomial(n, true), "n": n}))
    out = S.oos_k(pd.concat(rows), [1, 10, 50, 100, 150, 200, 400, 1000, 5000], ["a", "b", "c"])
    assert 50 <= out["k"] <= 400 and not out["at_edge"]
