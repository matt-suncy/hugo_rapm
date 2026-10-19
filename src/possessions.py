"""Lineup reconstruction and possession table from CDN play-by-play.

Pipeline per game:
  1. Period starters: a player started the period if his first appearance in it is
     anything other than "SUB in". Players who play a whole period without recording
     an event are invisible to this rule; those periods are filled from pbpstats'
     per-period lineup list (see `_fill_starters`).
  2. Walk events in `orderNumber` order, applying substitutions.
  3. A possession is a maximal run of events with the same `possession` (team with the
     ball) value inside a period. Runs that contain no possession-defining event (only
     technical FTs, fouls, timeouts...) get weight 0, as does a period's final run if
     nothing happened in it.

Credit rules (pbpstats conventions):
  * Free-throw points go to the lineups on the floor at the time of the foul that
    produced them, so a substitution between FTs doesn't move credit.
  * The possession itself (weight 1) goes to the lineups on the floor at the run's last
    non-substitution event.
  * When credit lands on more than one lineup pair within a run, the run produces
    several rows sharing a `possession_id`; only one carries poss=1.

Outputs (data/processed/):
  possessions_<season>.parquet  one row per (possession, lineup pair)
  shots_<season>.parquet        one row per FGA / FTA with the row_id it is credited to
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict

import numpy as np
import pandas as pd

from src import config, ingest

_CLOCK = re.compile(r"PT(\d+)M([\d.]+)S")
FGA_TYPES = {"2pt", "3pt"}
# Events that make a `possession` run a real possession.
POSS_DEFINING = {"2pt", "3pt", "turnover", "freethrow", "rebound", "jumpball"}


class LineupError(Exception):
    pass


def clock_seconds(c: str) -> float:
    m = _CLOCK.match(c)
    return int(m.group(1)) * 60 + float(m.group(2)) if m else np.nan


def _ids(v) -> list[int]:
    if isinstance(v, str) and v.strip():
        return [int(x) for x in v.split(",")]
    return []


# --------------------------------------------------------------------------- starters

def player_teams(g: pd.DataFrame) -> dict[int, int]:
    """personId -> teamId for one game: main actors, assisters (shooter's team) and players
    who drew fouls (the fouler's opponent)."""
    both = set(g.teamId.dropna().astype(int))
    out: dict[int, int] = {}
    a = g[(g.assistPersonId > 0) & g.teamId.notna()]
    out.update(zip(a.assistPersonId.astype(int), a.teamId.astype(int), strict=True))
    if len(both) == 2:
        f = g[(g.foulDrawnPersonId > 0) & g.teamId.notna()]
        out.update((int(p), (both - {int(t)}).pop())
                   for p, t in zip(f.foulDrawnPersonId, f.teamId, strict=True))
    m = g[(g.personId > 0) & g.teamId.notna()]
    out.update(zip(m.personId.astype(int), m.teamId.astype(int), strict=True))
    return out


def infer_starters(p: pd.DataFrame, teams: dict[int, int]) -> dict[int, set[int]]:
    """Players whose first appearance in period `p` is not a sub-in, by team."""
    first: dict[int, str] = {}

    def see(pid: int, how: str) -> None:
        if pid and pid in teams and pid not in first:
            first[pid] = how

    for r in p.itertuples(index=False):
        a = r.actionType
        if a == "substitution":
            see(int(r.personId), r.subType)
            continue
        # Technicals and ejections can be called on bench players.
        if (a == "foul" and r.subType == "technical") or a == "ejection":
            continue
        if r.personId and r.personId > 0:
            see(int(r.personId), "event")
        for col in ("assistPersonId", "foulDrawnPersonId", "stealPersonId",
                    "blockPersonId", "jumpBallWonPersonId", "jumpBallLostPersonId"):
            v = getattr(r, col)
            if pd.notna(v) and v > 0:
                see(int(v), "event")
    out: dict[int, set[int]] = defaultdict(set)
    for pid, how in first.items():
        if how != "in":
            out[teams[pid]].add(pid)
    return out


def subbed_in_first(p: pd.DataFrame, teams: dict[int, int]) -> set[int]:
    first: dict[int, str] = {}
    for r in p.itertuples(index=False):
        if r.actionType == "substitution":
            first.setdefault(int(r.personId), r.subType)
    return {pid for pid, how in first.items() if how == "in"}


def _fill_starters(detected: set[int], excluded: set[int], period_lineups: list[frozenset],
                   prev_end: set[int]) -> set[int] | None:
    """Pick the period's starting five from pbpstats' lineup list for that period.

    Candidates must contain every detected starter and no player who first appeared via a
    sub-in. Ties are broken by overlap with the previous period's closing lineup.
    """
    cands = [lu for lu in period_lineups if detected <= lu and not (lu & excluded)]
    if not cands:
        return None
    cands.sort(key=lambda lu: -len(lu & prev_end))
    if len(cands) > 1 and len(cands[0] & prev_end) == len(cands[1] & prev_end):
        return None
    return set(cands[0])


def pbpstats_period_lineups(game_id: int, home: int, away: int) -> dict[tuple[int, int], list]:
    js = ingest.pbpstats("get-game-stats", {"GameId": f"{game_id:010d}", "Type": "Lineup"})
    out = {}
    for side, team in (("Home", home), ("Away", away)):
        for per, rows in js["stats"][side].items():
            if per.isdigit():
                out[(int(per), team)] = [frozenset(int(x) for x in r["EntityId"].split("-"))
                                         for r in rows]
    return out


# --------------------------------------------------------------------------- parsing

_STAT_FIELDS = ("points", "fga2", "fgm2", "fga3", "fgm3", "fta", "ftm", "tov", "oreb",
                "oreb_available", "poss")


def parse_game(g: pd.DataFrame, home: int, away: int, issues: list,
               lineup_source=None) -> tuple[list[dict], list[dict]]:
    """Parse one game's CDN events into possession rows and shot rows.

    Each event emits increments `(run, lineup_key, field, amount)`; rows are the sums per
    (run, lineup_key). A lineup_key is (offense team, offense five, defense five).

    `lineup_source` is a zero-arg callable returning pbpstats period lineups; it is only
    called when starter inference fails, so most games need no API request.
    """
    g = g.sort_values("orderNumber", kind="stable")
    gid = int(g.gameId.iat[0])
    teams = player_teams(g)
    for r in g[g.actionType == "substitution"].itertuples(index=False):
        teams[int(r.personId)] = int(r.teamId)
    other = {home: away, away: home}

    inc: dict[tuple, dict] = {}       # (global run, key) -> stats
    shot_list: list[tuple] = []        # ((global run, key), shot dict)
    run_meta: dict[int, dict] = {}
    prev_end = {home: set(), away: set()}
    pbp_lineups = None
    run_base = 0

    def add(run: int, key: tuple, f: str, n: int = 1) -> None:
        d = inc.setdefault((run, key), dict.fromkeys(_STAT_FIELDS, 0))
        d[f] += n

    for period, p in g.groupby("period", sort=True):
        starters = infer_starters(p, teams)
        excluded = subbed_in_first(p, teams)
        on: dict[int, set[int]] = {}
        for t in (home, away):
            s = set(starters.get(t, set()))
            if len(s) != 5:
                if pbp_lineups is None and lineup_source is not None:
                    pbp_lineups = lineup_source()
                filled = None
                if pbp_lineups is not None:
                    filled = _fill_starters(s, excluded, pbp_lineups.get((period, t), []),
                                            prev_end[t])
                issues.append({"game_id": gid, "period": period, "team": t,
                               "detected": len(s), "filled": filled is not None})
                if filled is None:
                    raise LineupError(f"{gid} P{period} team {t}: {len(s)} starters")
                s = filled
            on[t] = s

        # possession team per event; 0 means unknown -> fill from neighbours in the period
        pos = p.possession.replace(0, np.nan).ffill().bfill().astype(int).to_numpy()
        run_local = np.concatenate([[0], np.cumsum(pos[1:] != pos[:-1])])
        run_is_poss: dict[int, bool] = {}
        run_has_play: dict[int, bool] = {}  # FGA, non-technical FTA, or turnover
        run_last_key: dict[int, tuple] = {}
        foul_key = None
        pending_miss = None  # (run, key, shooting team) awaiting a rebound

        for i, r in enumerate(p.itertuples(index=False)):
            run = run_base + int(run_local[i])
            off = int(pos[i])
            if run not in run_meta:
                run_meta[run] = {"period": period, "start_clock": clock_seconds(r.clock),
                                 "start_margin": _margin(r, off, home)}
                foul_key = None
            a = r.actionType

            if a == "substitution":
                t, pid = int(r.teamId), int(r.personId)
                if r.subType == "out":
                    if pid not in on[t]:
                        issues.append({"game_id": gid, "period": period, "team": t,
                                       "detected": -1, "filled": False,
                                       "note": f"sub out of player not on floor: {pid}"})
                    on[t].discard(pid)
                else:
                    on[t].add(pid)
                continue

            for t in (home, away):
                if len(on[t]) != 5:
                    raise LineupError(f"{gid} P{period} team {t}: {len(on[t])} on floor "
                                      f"at {r.clock} ({r.description})")

            key = _key(off, on, other)
            if a != "freethrow":
                run_last_key[run] = key
            if a in POSS_DEFINING and not (a == "freethrow" and r.descriptor == "technical"):
                run_is_poss[run] = True
                if a != "rebound" and a != "jumpball":
                    run_has_play[run] = True
            if a == "foul" and r.subType != "technical" and int(r.teamId) != off:
                foul_key = key

            if a in FGA_TYPES and int(r.teamId) == off:
                v = 3 if a == "3pt" else 2
                made = r.shotResult == "Made"
                add(run, key, f"fga{v}")
                if made:
                    add(run, key, f"fgm{v}")
                    add(run, key, "points", v)
                    pending_miss = None
                else:
                    pending_miss = (run, key, off)
                shot_list.append(((run, key), _shot(r, gid, period, off, v, made)))
            elif a == "freethrow":
                made = r.shotResult == "Made"
                shooter = int(r.teamId)
                if shooter != off:      # technical FT by the team without the ball
                    credit = _key(shooter, on, other)
                elif foul_key is not None:
                    credit = foul_key
                else:
                    credit = key
                if shooter == off:
                    run_last_key[run] = credit
                add(run, credit, "fta")
                if made:
                    add(run, credit, "ftm")
                    add(run, credit, "points")
                shot_list.append(((run, credit), _shot(r, gid, period, shooter, 1, made)))
                n, of = str(r.subType).split(" of ")
                live = n == of and r.descriptor not in ("technical", "flagrant")
                pending_miss = (run, credit, shooter) if (live and not made) else None
            elif a == "rebound":
                if pending_miss is not None and "deadball" not in str(r.qualifiers):
                    mrun, mkey, shooting = pending_miss
                    add(mrun, mkey, "oreb_available")
                    if int(r.teamId) == shooting:
                        add(mrun, mkey, "oreb")
                    pending_miss = None
            elif a == "turnover" and int(r.teamId) == off:
                add(run, key, "tov")
                pending_miss = None

        # A period's last run with no shot/FT/turnover (ball inbounded with ~1s left) is
        # not counted, matching pbpstats' possession totals much more closely.
        last_run = run_base + int(run_local[-1])
        for run, k in run_last_key.items():
            if run_is_poss.get(run) and (run != last_run or run_has_play.get(run)):
                add(run, k, "poss")
        prev_end = {t: set(on[t]) for t in (home, away)}
        run_base += int(run_local[-1]) + 1

    rows, row_of = [], {}
    for (run, k), stats in sorted(inc.items(), key=lambda kv: kv[0][0]):
        row_id = f"{gid}_{len(rows)}"
        row_of[(run, k)] = row_id
        row = {"row_id": row_id, "game_id": gid, "possession_id": f"{gid}_{run}",
               **run_meta[run], "off_team": k[0], "def_team": other[k[0]]}
        row.update({f"off{i + 1}": x for i, x in enumerate(k[1])})
        row.update({f"def{i + 1}": x for i, x in enumerate(k[2])})
        row.update(stats)
        rows.append(row)
    shots = [{**s, "row_id": row_of[rk]} for rk, s in shot_list]
    return rows, shots


def _key(off: int, on: dict[int, set[int]], other: dict[int, int]) -> tuple:
    return (off, tuple(sorted(on[off])), tuple(sorted(on[other[off]])))


def _margin(r, off: int, home: int) -> float:
    if pd.isna(r.scoreHome) or pd.isna(r.scoreAway):
        return np.nan
    m = float(r.scoreHome) - float(r.scoreAway)
    return m if off == home else -m


def _shot(r, gid: int, period: int, team: int, value: int, made: bool) -> dict:
    return {"game_id": gid, "period": period, "clock": clock_seconds(r.clock),
            "team_id": team, "shooter_id": int(r.personId), "value": value,
            "made": bool(made), "area": r.area if value > 1 else None,
            "area_detail": r.areaDetail if value > 1 else None,
            "shot_distance": r.shotDistance, "x": r.x, "y": r.y,
            "descriptor": r.descriptor, "sub_type": r.subType,
            "assisted": bool(pd.notna(r.assistPersonId) and r.assistPersonId > 0),
            "qualifiers": r.qualifiers if isinstance(r.qualifiers, str) else ""}


# --------------------------------------------------------------------------- garbage time

def garbage_time_flags(df: pd.DataFrame, rule: dict) -> pd.Series:
    """Flag garbage-time possessions per game (see config.yaml `garbage_time`)."""
    df = df.sort_values(["game_id", "period", "start_clock"], ascending=[True, True, False])
    cond = pd.Series(False, index=df.index)
    late = df.period >= rule["period"]
    for rr in rule["rules"]:
        cond |= late & (df.start_clock <= rr["max_seconds_remaining"]) & (
            df.start_margin.abs() >= rr["min_margin"])
    if not rule.get("revert_if_close", True):
        return cond.reindex(df.index)
    # garbage only if the condition holds from here to the end of the game
    rev = cond[::-1].groupby(df.game_id[::-1]).cummin()[::-1]
    return rev.astype(bool)


# --------------------------------------------------------------------------- driver

def build(season: str, allow_api_fill: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = config.load()
    ev = ingest.archive("cdnnba", season)
    games = ingest.pbpstats_games(season).set_index("GameId")
    ev = ev[ev.gameId.isin(games.index)]
    all_rows, all_shots, issues, failed = [], [], [], []
    for gid, g in ev.groupby("gameId", sort=True):
        home, away = int(games.at[gid, "HomeTeamId"]), int(games.at[gid, "AwayTeamId"])
        src = (lambda gid=gid, h=home, a=away: pbpstats_period_lineups(gid, h, a)) \
            if allow_api_fill else None
        try:
            rows, shots = parse_game(g, home, away, issues, src)
        except LineupError as e:
            failed.append({"game_id": gid, "error": str(e)})
            continue
        all_rows += rows
        all_shots += shots
    poss = pd.DataFrame(all_rows)
    poss["season"] = season
    poss["garbage_time"] = garbage_time_flags(poss, cfg["garbage_time"])
    shots = pd.DataFrame(all_shots)
    config.ensure_dirs()
    poss.to_parquet(config.PROCESSED / f"possessions_{season}.parquet", index=False)
    shots.to_parquet(config.PROCESSED / f"shots_{season}.parquet", index=False)
    pd.DataFrame(issues).to_csv(config.PROCESSED / f"lineup_issues_{season}.csv", index=False)
    pd.DataFrame(failed, columns=["game_id", "error"]).to_csv(
        config.PROCESSED / f"failed_games_{season}.csv", index=False)
    print(f"[possessions] {season}: {poss.poss.sum():,} possessions, "
          f"{len(failed)} failed games, {sum(1 for i in issues if i['detected'] >= 0)} "
          f"periods needed starter fill")
    return poss, shots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=config.load()["seasons"]["primary"])
    ap.add_argument("--no-api-fill", action="store_true")
    a = ap.parse_args()
    build(a.season, allow_api_fill=not a.no_api_fill)


if __name__ == "__main__":
    main()
