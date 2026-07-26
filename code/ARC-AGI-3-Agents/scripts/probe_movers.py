"""Black-box probe: a per-step census of every moving thing on a level.

Replays saved solutions to a level, steps the actions given on the command line,
and after each one prints every 3x3 entity block with its facing, plus the raw
cell count per value. Counting CELLS is not the same as counting entities — two
entities on one square render as a single block and one standing on the goal is
hidden under it, which is exactly the trap that produced a wrong "a patroller was
destroyed" reading on L4.

Unknown values are censused too, so a new mechanic shows up as an entity with a
position and a facing on its first appearance.

Usage: probe_movers.py ACTION3,ACTION3,... [--level N] [--quiet-journal]

Black box only: the census is read out of the returned frame, never from
environment_files/.
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.journal import Journal  # noqa: E402

SOLUTIONS_PATH = Path("artifacts/wm_journal/solutions.json")
PLAYER, GOAL = 9, 14
NOTCHES = (15, 11)          # entity facing notches (11 = a guard that has eaten)
MAZE = {0, 2, 5, 6}         # floor / door / wall / border — never an entity
BODIES = (8, 12, 13)        # known entity bodies; anything unknown is added below
NOTCH_OFF = {"U": (0, 1), "D": (2, 1), "L": (1, 0), "R": (1, 2)}


def g(raw):
    return [a.tolist() for a in raw.frame][-1] if raw.frame else None


def load_solutions():
    return {int(k): v for k, v in json.loads(SOLUTIONS_PATH.read_text()).items()}


def prefix_for(level, sols):
    out = []
    for i in range(level):
        if i not in sols:
            raise SystemExit(f"missing solution for L{i}")
        out += sols[i]
    return out


def blocks(grid, body, notch_vals):
    """3x3 blocks of `body` (one cell may be a facing notch), with the facing."""
    cells = {(r, c) for r in range(64) for c in range(64)
             if grid[r][c] == body or grid[r][c] in notch_vals}
    found, claimed = [], set()
    for r, c in sorted(cells):
        if (r, c) in claimed:
            continue
        blk = {(r + i, c + j) for i in range(3) for j in range(3)}
        if not blk <= cells:
            continue
        if not any(grid[rr][cc] == body for rr, cc in blk):
            continue
        claimed |= blk
        facing, notch = "?", None
        for rr, cc in blk:
            if grid[rr][cc] in notch_vals:
                notch = grid[rr][cc]
                for f, o in NOTCH_OFF.items():
                    if o == (rr - r, cc - c):
                        facing = f
        found.append((r, c, facing, notch))
    return found


def census(grid):
    present = {v for row in grid for v in row} - MAZE - {GOAL} - set(NOTCHES) - {4}
    bodies = sorted(set(BODIES) & present | (present - set(BODIES)) | {PLAYER})
    ents, counts = {}, {}
    for v in bodies:
        notch = (4,) if v == PLAYER else NOTCHES
        ents[v] = blocks(grid, v, notch)
        counts[v] = sum(1 for r in range(64) for c in range(64) if grid[r][c] == v)
    goal = [(r, c) for r in range(64) for c in range(64) if grid[r][c] == GOAL]
    goal_tl = (min(r for r, _ in goal), min(c for _, c in goal)) if goal else None
    hud = sum(1 for c in range(64) if grid[63][c] != 0)   # energy bar length
    return {"ents": ents, "counts": counts, "goal": goal_tl, "hud": hud,
            "patrols": ents.get(12, []), "players": ents.get(PLAYER, [])}


def fmt(cs):
    out = []
    for v, blks in cs["ents"].items():
        body = " ".join(f"({r},{c},{f}" + (f",notch{n})" if n not in (15, 4, None)
                                                    else ")") for r, c, f, n in blks)
        # 8 visible cells per un-occluded entity (9 body cells minus the notch);
        # fewer means two share a square or one is hidden under the goal
        tag = "" if cs["counts"][v] == 8 * len(blks) else f"[{cs['counts'][v]}cells]"
        out.append(f"{v}x{len(blks)}{tag}: {body or '-'}")
    return "   ".join(out) + f"   hud={cs['hud']}"


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    level = 4
    if "--level" in sys.argv:
        level = int(sys.argv[sys.argv.index("--level") + 1])
        argv = [a for a in argv if a != str(level)]
    actions = argv[0].split(",") if argv and argv[0] else []
    journal = "--quiet-journal" not in sys.argv

    sols = load_solutions()
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})
    for n in prefix_for(level, sols):
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})

    J = Journal("tu93", level) if journal else None
    cs = census(g(raw))
    print(f"L{level} step 0 (goal {cs['goal']}):")
    print("   ", fmt(cs))

    for i, n in enumerate(actions, start=1):
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
        if raw is None or not raw.frame or raw.state.name == "GAME_OVER":
            print(f"  step {i} {n}: GAME_OVER")
            if J:
                J.probe(actions=[n], hypothesis="per-step census of every mover",
                        observed="GAME_OVER", died=True, env_steps=1)
            return
        cs = census(g(raw))
        print(f"  step {i} {n} (levels_completed={raw.levels_completed}):")
        print("   ", fmt(cs))
        if J:
            J.probe(actions=[n],
                    hypothesis="how does every moving entity respond to this action?",
                    observed=fmt(cs), died=False, env_steps=1,
                    entities={str(v): b for v, b in cs["ents"].items()})


if __name__ == "__main__":
    main()
