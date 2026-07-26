"""Replay every saved solution through the model and demand an exact frame at
every step of every level.

This is the regression the earlier one was missing. Certifying on a two-step
probe says almost nothing: two of the nine levels turned out to mispredict on
their own solution path — a guard sharing a square with a patroller, and a
patroller sharing one with a pursuer — and the short probes never put two
enemies on the same square, so nothing complained.

The frame after a level is cleared is the NEXT level's maze, which the model does
not claim to predict; those steps are reported separately rather than counted as
failures.

Usage: backtest_all.py [--verbose]
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.core import Action, Status, diff_cells, ignored_cells  # noqa: E402
from agents.wm.tu93_model import tu93_world_model  # noqa: E402

SOLS = {int(k): v for k, v in
        json.loads(Path("artifacts/wm_journal/solutions.json").read_text()).items()}


def g(raw):
    return [a.tolist() for a in raw.frame][-1] if raw.frame else None


def main():
    verbose = "--verbose" in sys.argv
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})

    bad_total = 0
    for level in sorted(SOLS):
        model = tu93_world_model(version=12)
        state = model.reconstruct(g(raw))
        hud = ignored_cells(model, g(raw)) or set()
        lv0 = raw.levels_completed
        exact = terminal = 0
        bugs = []
        for i, n in enumerate(SOLS[level], start=1):
            a = GameAction.from_name(n)
            raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
            state, _ = model.step(state, Action(n))
            if raw is None or not raw.frame:
                bugs.append((i, n, "engine returned no frame"))
                break
            actual = g(raw)
            cleared = raw.levels_completed > lv0
            off = diff_cells(model.render(state), actual, hud)
            if cleared:
                terminal += 1                      # next level's maze; not modelled
            elif off == 0:
                exact += 1
            else:
                bugs.append((i, n, f"{off} cell(s)"))
        checked = len(SOLS[level]) - terminal
        bad_total += len(bugs)
        mark = "ok " if not bugs else "BUG"
        print(f"{mark} L{level}: {exact}/{checked} exact "
              f"(+{terminal} terminal frame{'s' if terminal != 1 else ''} excluded)"
              + (f"  first bug: step {bugs[0][0]} after {bugs[0][1]} — {bugs[0][2]}"
                 if bugs else ""))
        if verbose and bugs:
            for b in bugs:
                print(f"      step {b[0]:>2} {b[1]}: {b[2]}")

    print(f"\n{'ALL LEVELS EXACT' if not bad_total else str(bad_total) + ' mispredicted steps'}"
          f"; final state = {raw.state.name}")
    return 0 if not bad_total else 1


if __name__ == "__main__":
    sys.exit(main())
