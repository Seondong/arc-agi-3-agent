"""Black-box probe: is the second 9-block on L4 actually player-controlled?

The carried model drives every 9-block with one action. That rule was authored
from ACTION3 probes only — and ACTION3 cannot tell the two theories apart,
because the second block sits in a pocket with walls left, right and below. Its
ONLY free direction is up, and pressing ACTION1 from the start does nothing.

Two theories survive:
  T1  every block is driven; the second one just never had a legal move
  T2  the second block is driven only when the FIRST block also moves
  T3  the second block is not driven at all

Discriminator: put player 1 somewhere it can legally move UP, then press
ACTION1. T1/T2 predict the second block rises to (38,51); T3 predicts it stays.

Getting there uses ONLY down/left/right, so the disputed rule never fires during
the approach and the certified part of the model can be trusted to plan it.

Usage: probe_l4_second_block.py [target_row] [target_col]     (default 20 27)
"""
import json
import sys
from collections import deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.core import Action, Status  # noqa: E402
from agents.wm.journal import Journal  # noqa: E402
from agents.wm.tu93_model import tu93_world_model  # noqa: E402

SOLUTIONS_PATH = Path("artifacts/wm_journal/solutions.json")
SAFE_MOVES = ["ACTION2", "ACTION3", "ACTION4"]   # down / left / right only


def g(raw):
    return [a.tolist() for a in raw.frame][-1] if raw.frame else None


def prefix_for(level):
    sols = {int(k): v for k, v in json.loads(SOLUTIONS_PATH.read_text()).items()}
    out = []
    for i in range(level):
        out += sols[i]
    return out


def blocks(grid, body, notch_vals):
    cells = {(r, c) for r in range(64) for c in range(64)
             if grid[r][c] == body or grid[r][c] in notch_vals}
    found, claimed = [], set()
    for r, c in sorted(cells):
        if (r, c) in claimed:
            continue
        blk = {(r + i, c + j) for i in range(3) for j in range(3)}
        if not blk <= cells or not any(grid[rr][cc] == body for rr, cc in blk):
            continue
        claimed |= blk
        found.append((r, c))
    return found


def bfs_to(model, start, target, max_depth=30):
    """Shortest down/left/right sequence putting SOME player block on `target`."""
    acts = [Action(a) for a in SAFE_MOVES]
    seen = {model.fingerprint(start)}
    q = deque([(start, [])])
    while q:
        st, path = q.popleft()
        if len(path) >= max_depth:
            continue
        for a in acts:
            nxt, status = model.step(st, a)
            if status == Status.GAME_OVER:
                continue
            if any((r, c) == target for (r, c, _) in nxt.players):
                return path + [a.name]
            if status == Status.LEVEL_COMPLETED:
                continue
            k = model.fingerprint(nxt)
            if k not in seen:
                seen.add(k)
                q.append((nxt, path + [a.name]))
    return None


def main():
    target = (int(sys.argv[1]) if len(sys.argv) > 1 else 20,
              int(sys.argv[2]) if len(sys.argv) > 2 else 27)
    J = Journal("tu93", 4)

    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})
    for n in prefix_for(4):
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})

    model = tu93_world_model(version=9)
    s0 = model.reconstruct(g(raw))
    print(f"start players={s0.players}")
    path = bfs_to(model, s0, target)
    if path is None:
        print(f"no down/left/right route to {target} inside the model")
        J.note(text=f"L4 second-block probe: no safe down/left/right route to {target}.")
        return
    print(f"in-model approach to {target}: {len(path)} actions {path}")

    steps = 0
    for n in path:
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
        steps += 1
        if raw is None or not raw.frame or raw.state.name == "GAME_OVER":
            print(f"  DIED during approach at step {steps} ({n})")
            J.probe(actions=path[:steps],
                    hypothesis=f"reach {target} with down/left/right to test the "
                               "second block's up-move",
                    observed="GAME_OVER during approach", died=True, env_steps=steps)
            return
    before = blocks(g(raw), 9, (4,))
    print(f"  arrived: player blocks {before}")

    a = GameAction.from_name("ACTION1")
    raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
    steps += 1
    if raw is None or not raw.frame or raw.state.name == "GAME_OVER":
        print("  ACTION1 -> GAME_OVER")
        J.probe(actions=path + ["ACTION1"],
                hypothesis="does the second 9-block rise when player 1 moves up?",
                observed="GAME_OVER on the discriminating ACTION1", died=True,
                env_steps=steps)
        return
    after = blocks(g(raw), 9, (4,))
    moved_1 = before[0] != after[0]
    second_before = before[-1]
    second_after = after[-1]
    verdict = ("second block MOVED" if second_before != second_after
               else "second block STAYED")
    print(f"  after ACTION1: player blocks {after}")
    print(f"  player 1 moved: {moved_1};  {verdict} "
          f"({second_before} -> {second_after})")
    J.probe(actions=path + ["ACTION1"],
            hypothesis="the second 9-block is driven by the same action — does it "
                       "rise out of its pocket when player 1 also moves up?",
            observed=f"player1 {before[0]}->{after[0]} (moved={moved_1}); "
                     f"second block {second_before}->{second_after}: {verdict}",
            died=False, env_steps=steps,
            entities={"players_before": before, "players_after": after})


if __name__ == "__main__":
    main()
