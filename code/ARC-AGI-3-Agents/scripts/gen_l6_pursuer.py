"""L6 — the pursuer, and the counterfactual that pinned its rule down.

Captured from real engine runs:

  1. ONE CELL. The carried model reproduced L6 exactly until the player stepped
     into the column the 13-block faces. Then one cell disagreed: its notch had
     turned from 15 to 11 — the value a guard wears after it has eaten. A single
     cell refused certification, which is the reason the backtest demands exact
     frames instead of a similarity score.

  2. THE TRAJECTORY. Locked on, it walks the line it faces to the square where it
     saw the player, then reproduces the player's own path one square per move
     the player actually makes. A blocked action advances nothing.

  3. THE COUNTERFACTUAL. Trail-following and shortest-path chasing fit the
     trajectory equally well, so the player was driven round a four-square loop
     where they disagree. This script simulates the chaser that L6 could have
     been — a real BFS over the maze, recomputed every step — and records where
     it would have been at each step next to where the real thing was. On the
     last step the chaser is standing on the player.

Writes artifacts/wm_viz/l6_pursuer.json.
"""
import json
from collections import deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.backtest import run_backtest  # noqa: E402
from agents.wm.core import Action, Status, Timeline, Transition  # noqa: E402
from agents.wm.tu93_model import tu93_world_model  # noqa: E402

OUT = Path("artifacts/wm_viz/l6_pursuer.json")
SOLS = json.loads(Path("artifacts/wm_journal/solutions.json").read_text())
LEVEL = 6
TRIGGER = ["ACTION4", "ACTION4"]                      # 2nd step flips the notch
TRAJ = ["ACTION4", "ACTION4", "ACTION4", "ACTION4", "ACTION2", "ACTION2",
        "ACTION4", "ACTION1", "ACTION1"]              # 4th action is blocked
LOOP = ["ACTION4", "ACTION4", "ACTION3", "ACTION2", "ACTION3", "ACTION1"]
DEATH = ["ACTION4", "ACTION4", "ACTION4", "ACTION3"]
STEP = 6
DIRS = {"U": (-STEP, 0), "D": (STEP, 0), "L": (0, -STEP), "R": (0, STEP)}
env_steps = [0]


def g(raw):
    return [a.tolist() for a in raw.frame][-1] if raw.frame else None


def fresh(arc, gid):
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})
    env_steps[0] += 1
    for lvl in range(LEVEL):
        for n in SOLS[str(lvl)]:
            a = GameAction.from_name(n)
            raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
            env_steps[0] += 1
    return env, raw


def step(env, name):
    a = GameAction.from_name(name)
    raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
    env_steps[0] += 1
    return raw


def bounds(grid):
    rs = [r for r in range(64) if any(grid[r][c] not in (5, 6) for c in range(64))]
    cs = [c for c in range(64) if any(grid[r][c] not in (5, 6) for r in range(64))]
    return min(rs), max(rs), min(cs), max(cs)


def walls_from(grid):
    """The maze as the movers see it: every entity erased, only 5/6 stop you."""
    return [[v in (5, 6) for v in row] for row in grid]


def can_move(wall, r, c, d):
    """A 3x3 block at (r,c) takes a 6px step: the +3 strip and the +3..+6
    destination must both be clear — the same test the world model applies."""
    dr, dc = DIRS[d]
    for rr in (range(r + dr // 2, r + dr // 2 + 3) if dr else range(r, r + 3)):
        for cc in (range(c + dc // 2, c + dc // 2 + 3) if dc else range(c, c + 3)):
            if not (0 <= rr < 64 and 0 <= cc < 64) or wall[rr][cc]:
                return False
    for rr in range(r + dr, r + dr + 3):
        for cc in range(c + dc, c + dc + 3):
            if not (0 <= rr < 64 and 0 <= cc < 64) or wall[rr][cc]:
                return False
    return True


def chase_step(wall, src, dst):
    """One step of a shortest-path chaser: BFS the maze, take the first move."""
    if src == dst:
        return src
    prev, q = {src: None}, deque([src])
    while q:
        cur = q.popleft()
        if cur == dst:
            break
        for d in DIRS:
            if not can_move(wall, cur[0], cur[1], d):
                continue
            dr, dc = DIRS[d]
            nxt = (cur[0] + dr, cur[1] + dc)
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    if dst not in prev:
        return src
    path, cur = [], dst
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    return path[1] if len(path) > 1 else src


def run(arc, gid, actions, crop, model):
    """Step a sequence for real, tracking the model's view alongside it."""
    env, raw = fresh(arc, gid)
    state = model.reconstruct(g(raw))
    out = [{"k": 0, "action": None, "grid": crop(g(raw)),
            "player": list(state.players[0]),
            "pursuer": [list(p[:3]) + [p[3]] for p in state.pursuers],
            "dead": False}]
    for i, n in enumerate(actions, start=1):
        raw = step(env, n)
        if raw is None or not raw.frame or raw.state.name == "GAME_OVER":
            out.append({"k": i, "action": n, "grid": None, "player": None,
                        "pursuer": None, "dead": True})
            break
        state, _ = model.step(state, Action(n))
        out.append({"k": i, "action": n, "grid": crop(g(raw)),
                    "player": list(state.players[0]) if state.players else None,
                    "pursuer": [list(p[:3]) + [p[3]] for p in state.pursuers],
                    "dead": False})
    return out


def main():
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env, raw = fresh(arc, gid)
    init = g(raw)
    r0, r1, c0, c1 = bounds(init)
    crop = lambda gr: [row[c0:c1 + 1] for row in gr[r0:r1 + 1]]  # noqa: E731
    wall = walls_from(init)
    model = tu93_world_model(version=11)

    # ---- 1. the one-cell refutation ---------------------------------------
    env2, raw2 = fresh(arc, gid)
    tl = Timeline(g(raw2))
    prev = g(raw2)
    for i, n in enumerate(TRIGGER, start=1):
        raw2 = step(env2, n)
        cur = g(raw2)
        tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                             after_frame=cur, status=Status.RUNNING))
        prev = cur
    # v10 is the model as it stood before L6: it has no pursuer at all, so the
    # 13-block is scenery to it and its notch can never change.
    v10 = tu93_world_model(version=10)
    v10.reconstruct = (lambda f, _r=v10.reconstruct: _r(f))
    import agents.wm.tu93_model as TM
    saved = TM.PURSUER
    TM.PURSUER = -1                      # make the pursuer invisible to the model
    v10 = tu93_world_model(version=10)
    rep10 = run_backtest(v10, tl)
    TM.PURSUER = saved
    rep11 = run_backtest(tu93_world_model(version=11), tl)
    m = rep10.first_mismatch
    onecell = {
        "actions": TRIGGER, "step_index": m.step_index, "action": m.action,
        "cells_off": m.changed_cells,
        "predicted": crop(m.predicted_frame), "actual": crop(m.actual_frame),
        "v10_summary": rep10.summary(), "v11_summary": rep11.summary(),
    }

    # ---- 2. the trajectory -------------------------------------------------
    traj = run(arc, gid, TRAJ, crop, tu93_world_model(version=11))

    # ---- 3. the loop, against the chaser it is not -------------------------
    loop = run(arc, gid, LOOP, crop, tu93_world_model(version=11))
    chaser, live = None, []
    for fr in loop:
        if fr["pursuer"] and fr["pursuer"][0][3]:        # locked on
            if chaser is None:
                chaser = tuple(fr["pursuer"][0][:2])     # starts where the real one did
            else:
                chaser = chase_step(wall, chaser, tuple(fr["player"][:2]))
        live.append(list(chaser) if chaser else None)
        fr["chaser"] = list(chaser) if chaser else None
        fr["chaser_kills"] = bool(chaser and fr["player"]
                                  and list(chaser) == fr["player"][:2])

    # ---- 4. the death it actually cost -------------------------------------
    death = run(arc, gid, DEATH, crop, tu93_world_model(version=11))

    data = {
        "level": LEVEL, "origin": [r0, c0],
        "onecell": onecell, "trajectory": traj, "loop": loop, "death": death,
        "solution_len": len(SOLS[str(LEVEL)]), "env_steps": env_steps[0],
    }
    OUT.write_text(json.dumps(data))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes) using {env_steps[0]} env steps")
    print(f"  pre-L6 model on the trigger: {rep10.summary()}")
    print(f"  v11 on the same           : {rep11.summary()}")
    for fr in loop:
        print(f"    k={fr['k']} player={fr['player'][:2] if fr['player'] else None} "
              f"pursuer={fr['pursuer'][0][:2] if fr['pursuer'] else None} "
              f"chaser-would-be={fr['chaser']} kills={fr['chaser_kills']}")


if __name__ == "__main__":
    main()
