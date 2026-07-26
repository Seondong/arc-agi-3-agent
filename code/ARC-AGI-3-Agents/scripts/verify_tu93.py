"""Replay every saved tu93 solution from RESET and report the result.

This is the end-to-end check: no model, no planning, just the stored action
sequences against a fresh engine. It prints the per-level action count and the
final game state, so the claim "tu93 is solved" is something the reader can
re-run rather than take on trust.
"""
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

SOLUTIONS_PATH = Path("artifacts/wm_journal/solutions.json")


def main():
    sols = {int(k): v for k, v in json.loads(SOLUTIONS_PATH.read_text()).items()}
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})

    total = 0
    for level in sorted(sols):
        actions = sols[level]
        before = raw.levels_completed
        for n in actions:
            a = GameAction.from_name(n)
            raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
            total += 1
            if raw is None or raw.state.name == "GAME_OVER":
                print(f"L{level}: DIED after {len(actions)} actions")
                return
        ok = raw.levels_completed > before
        print(f"L{level}: {len(actions):3d} actions -> "
              f"{'CLEARED' if ok else 'NOT CLEARED'} "
              f"(levels_completed={raw.levels_completed}, state={raw.state.name})")

    print(f"\ntotal {total} actions across {len(sols)} levels; "
          f"final state = {raw.state.name}")


if __name__ == "__main__":
    main()
