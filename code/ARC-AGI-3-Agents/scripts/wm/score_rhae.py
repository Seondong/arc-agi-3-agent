"""Score what we have with the benchmark's own metric, not with our own numbers.

Everything reported so far — actions spent, levels cleared, frames exact — was
chosen by us. ARC-AGI-3 scores agents with Relative Human Action Efficiency, and
until this script existed we had never computed it, which made "tu93 solved in
185 actions" impossible to compare with any published result.

    level_score = min(1, human_baseline / our_actions) ** 2      # squared
    game_score  = weighted mean over ALL levels, weights 1..n     # unsolved = 0
    total       = mean over games

Two things the formula makes brutal and worth seeing:
  - the square: twice the human's actions scores 25%, not 50%
  - unsolved levels count as zero AND carry the largest weights, so coverage
    dominates efficiency

`--solved-only` additionally reports the score over the levels actually cleared.
That number is not RHAE and is labelled as such; it answers a different question
(how efficient are we where we succeed) and must never be quoted as the metric.
"""
import json

import _cli
from agents.wm.harness import load_solutions, open_arcade
from agents.wm.models import MODELS, short_id


def baselines(arc):
    return {e.game_id.split("-")[0]: list(e.baseline_actions or [])
            for e in arc.get_environments()}


def score_game(base, sols):
    """(rhae, solved_only, rows) for one game."""
    rows = []
    for lvl in range(len(base)):
        n = len(sols[lvl]) if lvl in sols else None
        b = base[lvl]
        s = min(1.0, b / n) ** 2 if n else 0.0
        rows.append({"level": lvl, "ours": n, "human": b, "score": s})
    if not rows:
        return 0.0, 0.0, rows
    w = range(1, len(rows) + 1)
    rhae = sum(r["score"] * wi for r, wi in zip(rows, w)) / sum(w)
    solved = [r for r in rows if r["ours"]]
    sw = range(1, len(solved) + 1)
    solved_only = (sum(r["score"] * wi for r, wi in zip(solved, sw)) / sum(sw)
                   if solved else 0.0)
    return rhae, solved_only, rows


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--all-games", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    arc = open_arcade()
    base = baselines(arc)
    games = sorted(MODELS) if a.all_games else [short_id(a.game)]

    out, total = [], []
    for g in games:
        sols = load_solutions(g)
        b = base.get(g, [])
        if not b:
            print(f"{g}: no human baseline available offline")
            continue
        rhae, solved_only, rows = score_game(b, sols)
        total.append(rhae)
        out.append({"game": g, "rhae": rhae, "solved_only": solved_only,
                    "levels": rows})
        if not a.json:
            print(f"\n=== {g} — {len(sols)}/{len(b)} levels solved")
            for r in rows:
                mark = "  " if r["ours"] else " ✗"
                ours = f"{r['ours']:>4}" if r["ours"] else "   —"
                print(f" {mark} L{r['level']}: ours {ours} vs human {r['human']:>4}"
                      f"  -> {r['score']:.3f}")
            print(f"    RHAE (the metric, unsolved = 0): {rhae * 100:.1f}")
            print(f"    over solved levels only (NOT the metric): "
                  f"{solved_only * 100:.1f}")
    if a.json:
        print(json.dumps({"games": out,
                          "mean_rhae": sum(total) / len(total) if total else 0.0},
                         indent=1))
    elif total:
        print(f"\nmean RHAE across {len(total)} game(s): "
              f"{sum(total) / len(total) * 100:.1f}")
        print("For scale: the published verification agent reaches ~99 on all 25 "
              "public games; raw GPT-5.6-sol without a harness averages ~13.")


if __name__ == "__main__":
    main()
