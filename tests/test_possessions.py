import numpy as np
import pandas as pd
import pytest

from src import possessions as P

H, A = 1, 2
COLS = ["actionType", "subType", "personId", "teamId", "possession", "shotResult", "clock",
        "descriptor", "qualifiers", "assistPersonId", "foulDrawnPersonId",
        "jumpBallWonPersonId", "jumpBallLostPersonId", "scoreHome", "scoreAway"]


def _game(events: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(events, columns=COLS)
    df["gameId"], df["period"] = 99, 1
    df["orderNumber"] = np.arange(len(df)) * 10
    for c in ("stealPersonId", "blockPersonId", "area", "areaDetail", "shotDistance", "x", "y",
              "description"):
        df[c] = np.nan
    return df


N = np.nan
EVENTS = [
    # type, sub, person, team, poss, result, clock, descriptor, qual, ast, drawn, won, lost, sh, sa
    ("period", "start", 0, N, 0, N, "PT12M00.00S", N, N, N, N, N, N, 0, 0),
    ("jumpball", "recovered", 12, H, H, N, "PT11M58.00S", N, N, N, N, 11, 21, 0, 0),
    ("3pt", "Jump Shot", 13, H, H, "Made", "PT11M40.00S", N, N, 14, N, N, N, 3, 0),
    ("2pt", "Layup", 22, A, A, "Missed", "PT11M20.00S", N, N, N, N, N, N, 3, 0),
    ("rebound", "offensive", 23, A, A, N, "PT11M19.00S", N, N, N, N, N, N, 3, 0),
    ("2pt", "Layup", 24, A, A, "Made", "PT11M18.00S", N, N, N, N, N, N, 3, 2),
    ("3pt", "Jump Shot", 15, H, H, "Missed", "PT11M00.00S", N, N, N, N, N, N, 3, 2),
    ("rebound", "defensive", 25, A, A, N, "PT10M58.00S", N, N, N, N, N, N, 3, 2),
    ("substitution", "out", 21, A, A, N, "PT10M50.00S", N, N, N, N, N, N, 3, 2),
    ("substitution", "in", 26, A, A, N, "PT10M50.00S", N, N, N, N, N, N, 3, 2),
    ("foul", "personal", 11, H, A, N, "PT10M40.00S", "shooting", "2freethrow", N, 26, N, N,
     3, 2),
    ("substitution", "out", 12, H, A, N, "PT10M40.00S", N, N, N, N, N, N, 3, 2),
    ("substitution", "in", 16, H, A, N, "PT10M40.00S", N, N, N, N, N, N, 3, 2),
    ("freethrow", "1 of 2", 26, A, A, "Made", "PT10M40.00S", N, N, N, N, N, N, 3, 3),
    ("freethrow", "2 of 2", 26, A, A, "Made", "PT10M40.00S", N, N, N, N, N, N, 3, 4),
    ("turnover", "bad pass", 16, H, H, N, "PT10M20.00S", N, N, N, N, N, N, 3, 4),
    ("period", "end", 0, N, H, N, "PT00M00.00S", N, N, N, N, N, N, 3, 4),
]


@pytest.fixture(scope="module")
def parsed():
    rows, shots = P.parse_game(_game(EVENTS), H, A, issues=[])
    return pd.DataFrame(rows), pd.DataFrame(shots)


def test_possession_counts(parsed):
    rows, _ = parsed
    assert rows.groupby("off_team").poss.sum().to_dict() == {H: 3, A: 2}
    assert rows.groupby("off_team").points.sum().to_dict() == {H: 3, A: 4}


def test_starters_inferred_from_first_appearance():
    g = _game(EVENTS)
    s = P.infer_starters(g, P.player_teams(g))
    assert s[H] == {11, 12, 13, 14, 15}
    assert s[A] == {21, 22, 23, 24, 25}


def test_ft_credit_uses_lineup_at_foul(parsed):
    rows, _ = parsed
    ft = rows[rows.fta > 0].iloc[0]
    defense = {ft[f"def{i}"] for i in range(1, 6)}
    offense = {ft[f"off{i}"] for i in range(1, 6)}
    assert defense == {11, 12, 13, 14, 15}     # 12 was still on the floor at the foul
    assert offense == {22, 23, 24, 25, 26}
    assert ft.poss == 1 and ft.points == 2


def test_rebound_opportunities(parsed):
    rows, _ = parsed
    a1 = rows[(rows.off_team == A) & (rows.fga2 > 0)].iloc[0]
    assert (a1.oreb, a1.oreb_available) == (1, 1)
    h2 = rows[(rows.off_team == H) & (rows.fga3 > 0) & (rows.points == 0)].iloc[0]
    assert (h2.oreb, h2.oreb_available) == (0, 1)


def test_shots_link_to_rows(parsed):
    rows, shots = parsed
    assert len(shots) == 6  # 4 FGA + 2 FTA
    assert shots.row_id.isin(rows.row_id).all()


def test_garbage_time_reverts_if_game_gets_close():
    rule = {"period": 4, "rules": [{"max_seconds_remaining": 720, "min_margin": 25}],
            "revert_if_close": True}
    df = pd.DataFrame({
        "game_id": [1] * 4 + [2] * 3,
        "period": [4] * 7,
        "start_clock": [600, 500, 400, 300, 600, 500, 400],
        "start_margin": [26, 27, 10, 5, 30, 28, 26],
    })
    flags = P.garbage_time_flags(df, rule).sort_index().tolist()
    assert flags == [False, False, False, False, True, True, True]
