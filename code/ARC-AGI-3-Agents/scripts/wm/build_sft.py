"""Turn the corpus into chat-format SFT data, and hold a game out.

The only capability our data uniquely carries is repair: given a world model and
a pointed counterexample, write the corrected model. Of the three harnesses
studied, only ours and baseline1 can produce that pair at all, because only
those two run a replay verifier. So that is what gets distilled.

The split is BY GAME. Training on ka59 and testing on ka59 measures
memorisation, which with six repair pairs is all we would be measuring.

Usage:
  build_sft.py --holdout ka59 --out artifacts/wm_sft
"""
import json
import random
from pathlib import Path

import _cli

DATASET = Path("artifacts/wm_dataset")

SYSTEM = """You repair executable world models for grid games.

A world model is a python module defining `build(version=1)` which returns an
object with these methods:
  reconstruct(frame)   -> state          built from ONE frame, the level's first
  step(state, action)  -> (state, status)  status is "RUNNING",
                                           "LEVEL_COMPLETED" or "GAME_OVER"
  render(state)        -> frame          the full grid
  is_goal(state)       -> bool           the win condition
  fingerprint(state)   -> hashable       keys a planner's visited set
  ignore(frame)        -> [(r, c)]       cells excluded from checking

An action arrives as `Action(name, x, y)`. Directional actions have x=y=None.
ACTION6 is a coordinate action: `action.x` is the column, `action.y` the row.

You are given a model and a counterexample: a recorded step the model got wrong.
A counterexample points at one of two things. Mispredicted CELLS mean the
dynamics are wrong. A mispredicted STATUS -- the model said the level was
completed and it was not -- means the dynamics are right and `is_goal` is wrong.

Change the rule the counterexample names. Keep everything the evidence forces.
Reply with the complete corrected module in one fenced python block."""


def user_turn(ex):
    inp = ex.get("input") or {}
    parts = [f"GAME: {ex.get('game')}, level {ex.get('level')}.", "", "COUNTEREXAMPLE:",
             inp.get("bug", "")]
    cells = inp.get("cells") or []
    if cells:
        shown = ", ".join(f"[{c[0]},{c[1]},{c[2]},{c[3]}]" for c in cells[:60])
        parts += ["", f"{len(cells)} cell(s) wrong [row, col, predicted, actual]:",
                  shown + (" ..." if len(cells) > 60 else "")]
    else:
        parts += ["", "No cell is mispredicted. The board was reproduced exactly and "
                      "the VERDICT was wrong, so the fault is in `is_goal`."]
    parts += ["", "THE MODEL AS IT STANDS:", "```python",
              inp.get("model_source_before", ""), "```", "",
              "Return the corrected module."]
    return "\n".join(parts)


def assistant_turn(ex):
    src = (ex.get("target") or {}).get("model_source_after", "")
    return f"```python\n{src}\n```"


def load_repairs():
    out = []
    for f in sorted(DATASET.glob("*.jsonl")):
        for line in f.open():
            try:
                e = json.loads(line)
            except Exception:                                  # noqa: BLE001
                continue
            if e.get("type") != "repair":
                continue
            inp, tgt = e.get("input") or {}, e.get("target") or {}
            if inp.get("model_source_before") and tgt.get("model_source_after"):
                out.append(e)
    return out


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--holdout", default="ka59",
                   help="game kept out of training entirely")
    p.add_argument("--out", default="artifacts/wm_sft")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()

    reps = load_repairs()
    if not reps:
        raise SystemExit("no repair pairs; run export_dataset.py first")

    train = [e for e in reps if e.get("game") != a.holdout]
    test = [e for e in reps if e.get("game") == a.holdout]
    random.Random(a.seed).shuffle(train)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("valid", train[:1]), ("test", test)):
        path = out / f"{name}.jsonl"
        with path.open("w") as fh:
            for e in rows:
                fh.write(json.dumps({"messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user_turn(e)},
                    {"role": "assistant", "content": assistant_turn(e)},
                ]}, ensure_ascii=False) + "\n")
        print(f"  {name:6} {len(rows):3} example(s) -> {path}")

    # The eval needs the machinery to score with, not just the text.
    (out / "test_meta.json").write_text(json.dumps([
        {"game": e.get("game"), "level": e.get("level"), "source": e.get("source"),
         "bug": (e.get("input") or {}).get("bug", ""),
         "before": (e.get("input") or {}).get("model_source_before", ""),
         "after": (e.get("target") or {}).get("model_source_after", "")}
        for e in test], ensure_ascii=False, indent=1))

    by_game = {}
    for e in reps:
        by_game[e.get("game")] = by_game.get(e.get("game"), 0) + 1
    print(f"\n  repair pairs by game: {by_game}")
    print(f"  holdout: {a.holdout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
