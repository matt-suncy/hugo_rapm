import numpy as np
import pandas as pd

from src import rapm


def _synthetic(n_players=40, n_games=300, stints_per_game=40, seed=0):
    rng = np.random.default_rng(seed)
    o_true = rng.normal(0, 3, n_players)
    d_true = rng.normal(0, 3, n_players)  # points allowed
    rows = []
    for g in range(n_games):
        for _ in range(stints_per_game):
            p = rng.choice(n_players, 10, replace=False)
            off, dfn = p[:5], p[5:]
            poss = int(rng.integers(5, 15))
            mean = 1.12 + (o_true[off].sum() + d_true[dfn].sum()) / 100
            pts = rng.poisson(mean * poss)
            rows.append({"game_id": g, "off_team": 0,
                         **{f"off{i + 1}": x for i, x in enumerate(sorted(off))},
                         **{f"def{i + 1}": x for i, x in enumerate(sorted(dfn))},
                         "poss": poss, "points": pts})
    df = pd.DataFrame(rows)
    for c in rapm.STAT_COLS:
        if c not in df:
            df[c] = 0
    return df, o_true, -d_true


def test_ridge_recovers_effects():
    poss, o_true, d_true = _synthetic()
    st = rapm.stints(poss)
    coefs, mu = rapm.fit(st, lam=50)
    coefs = coefs.set_index("player_id").sort_index()
    assert np.isclose(mu, np.average(st.y, weights=st.poss))
    assert np.corrcoef(coefs.off, o_true)[0, 1] > 0.9
    assert np.corrcoef(coefs["def"], d_true)[0, 1] > 0.9


def test_prior_mean_is_limit_of_strong_penalty():
    poss, *_ = _synthetic(n_games=20)
    st = rapm.stints(poss)
    d = rapm.Design(st)
    b0 = np.linspace(-1, 1, d.X.shape[1])
    beta, _ = rapm.solve(d.X, d.y, d.w, lam=1e9, b0=b0)
    assert np.allclose(beta, b0, atol=1e-3)


def test_bootstrap_shapes_and_cv():
    poss, *_ = _synthetic(n_games=30)
    st = rapm.stints(poss)
    bs = rapm.game_bootstrap(st, lam=100, reps=5, seed=1, track=[0, 1])
    assert set(bs.player_id) == {0, 1} and bs.rep.nunique() == 5
    cv = rapm.cv_lambda(st, [10, 100, 1000], folds=3, seed=1)
    assert len(cv) == 3 and (cv.wmse > 0).all()
