"""Test 0: replicate baseline ridge RAPM on the primary season.

Acceptance (analysis plan section 5, Test 0): correlation with published RAPM >= 0.85 for
players with >= 500 possessions, and Hugo's total within 1.5 of the published value.
League-wide published values come from data/external/nbarapm_rapm_*.csv if present
(manual export; nbarapm.com disallows automated API access); otherwise only Hugo's
published numbers from config.yaml are checked.
"""

from __future__ import annotations

import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src import config, rapm  # noqa: E402
from src.analysis import common  # noqa: E402

# column aliases accepted in a manually exported published-RAPM CSV
ALIASES = {"player_id": ["player_id", "nba_id", "id", "PLAYER_ID"],
           "name": ["name", "player", "player_name", "Player"],
           "total": ["total", "rapm", "RAPM", "rapm_total", "Total"]}


def load_published() -> tuple[pd.DataFrame | None, str | None]:
    files = sorted(glob.glob(str(config.EXTERNAL / "nbarapm_rapm_*.csv")))
    if not files:
        return None, None
    df = pd.read_csv(files[-1])
    ren = {}
    for canon, opts in ALIASES.items():
        hit = next((c for c in opts if c in df.columns), None)
        if hit:
            ren[hit] = canon
    return df.rename(columns=ren), files[-1]


def main() -> None:
    cfg = config.load()
    season, hid = cfg["seasons"]["primary"], cfg["player"]["id"]
    rc = cfg["rapm"]
    poss = common.load_possessions(season)
    st = rapm.stints(poss, exclude_garbage=rc["exclude_garbage_time"])

    cv = rapm.cv_lambda(st, rc["lambda_grid"], rc["cv_folds"], cfg["seed"])
    lam = float(cv.loc[cv.wmse.idxmin(), "lambda"])

    coefs, mu = rapm.fit(st, lam)
    on = poss.melt(id_vars="poss", value_vars=rapm.OFF + rapm.DEF, value_name="player_id")
    coefs = coefs.merge(on.groupby("player_id").poss.sum().rename("poss_on").reset_index(),
                        on="player_id")
    coefs = coefs.merge(common.player_names(season), on="player_id", how="left")
    coefs["rank_all"] = coefs.total.rank(ascending=False, method="min").astype(int)
    q = coefs.poss_on >= rc["min_possessions_report"]
    coefs.loc[q, "rank_qualified"] = coefs[q].total.rank(ascending=False, method="min")
    coefs = coefs.sort_values("total", ascending=False)
    q = coefs.poss_on >= rc["min_possessions_report"]
    coefs.to_parquet(config.PROCESSED / f"rapm_{season}.parquet", index=False)
    cv.to_csv(config.PROCESSED / f"rapm_cv_{season}.csv", index=False)

    h = coefs[coefs.player_id == hid].iloc[0]
    pub = cfg["published_hugo"]["rapm_1y"]
    hugo_gap = float(h.total - pub["total"])

    published, pub_file = load_published()
    corr = n_corr = None
    if published is not None:
        key = "player_id" if "player_id" in published else "name"
        m = coefs[q].merge(published[[key, "total"]], on=key, suffixes=("", "_pub"))
        n_corr = len(m)
        corr = float(np.corrcoef(m.total, m.total_pub)[0, 1]) if n_corr > 2 else None

    hugo_ok = abs(hugo_gap) <= 1.5
    if corr is None:
        branch = ("PARTIAL: Hugo within 1.5 of published" if hugo_ok else
                  "FAIL: Hugo not within 1.5 of published") + \
                 "; league-wide correlation pending a published snapshot in data/external/"
    else:
        branch = "PASS" if (hugo_ok and corr >= 0.85) else "FAIL"

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.semilogx(cv["lambda"], cv.wmse, marker="o", color="#2a6f97")
    ax.axvline(lam, color="#999", ls="--", lw=1)
    ax.set_xlabel("λ (possession units)")
    ax.set_ylabel("held-out weighted MSE (pts/100)²")
    ax.set_title(f"Grouped-by-game {rc['cv_folds']}-fold CV, {season}")
    fig.tight_layout()
    config.FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(config.FIGURES / "test0_cv.png", dpi=150)
    plt.close(fig)

    n_q = int(q.sum())
    top = coefs[q].head(15)[["name", "team", "poss_on", "off", "def", "total"]]
    lines = [
        f"# Test 0: baseline RAPM replication ({season})",
        "",
        f"**Decision:** {branch}",
        "",
        f"- Stints: {len(st):,}; possessions: {int(st.poss.sum()):,}; players: {len(coefs)}",
        f"- League intercept: {mu:.2f} pts/100; CV-optimal λ = {lam:g}",
        f"- Garbage time excluded: {rc['exclude_garbage_time']}",
        "",
        "## Hugo Gonzalez",
        "",
        f"| | Off | Def | Total | Rank (≥{rc['min_possessions_report']} poss, n={n_q}) "
        "| Rank (all) |",
        "|---|---|---|---|---|---|",
        f"| Ours | {h.off:+.2f} | {h['def']:+.2f} | {h.total:+.2f} | "
        f"{int(h.rank_qualified) if pd.notna(h.rank_qualified) else '-'} | {h.rank_all} |",
        f"| nbarapm 1Y (plan) | {pub['off']:+.1f} | {pub['def']:+.1f} | {pub['total']:+.1f} | "
        f"{pub['rank']} | |",
        "",
        f"On-court possessions: {int(h.poss_on):,}. Gap to published total: {hugo_gap:+.2f}.",
        "",
        "## League-wide comparison",
        "",
        (f"Correlation with `{pub_file}` over {n_corr} players ≥{rc['min_possessions_report']} "
         f"possessions: **{corr:.3f}**" if corr is not None else
         "No published snapshot in `data/external/nbarapm_rapm_*.csv`; correlation not computed."
         " See README for the expected export format."),
        "",
        "## Top 15 (≥{} possessions)".format(rc["min_possessions_report"]),
        "",
        top.to_markdown(index=False, floatfmt="+.2f"),
        "",
        "![CV curve](figures/test0_cv.png)",
    ]
    (config.REPORTS / "test0_baseline.md").write_text("\n".join(lines) + "\n")
    common.save_result("test0", {
        "season": season, "lambda": lam, "intercept": mu, "n_stints": len(st),
        "hugo": {"off": h.off, "def": h["def"], "total": h.total, "poss_on": int(h.poss_on),
                 "rank_qualified": h.rank_qualified, "rank_all": int(h.rank_all)},
        "published_corr": corr, "published_n": n_corr, "hugo_gap_to_published": hugo_gap,
        "decision": branch})
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    main()
