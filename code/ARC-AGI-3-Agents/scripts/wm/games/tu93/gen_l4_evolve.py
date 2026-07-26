"""L4 — the level that was blocked for a session on a question that did not exist.

Three things are captured here, all from real engine runs:

  1. THE MISREADING. The count of value-12 cells goes 32 -> 16 -> 24 and never
     returns. Read as entities, that says a patroller was destroyed. It was not:
     two entities on one square render as ONE block and a patroller on the goal
     square is hidden under it. The census below reports both numbers side by
     side — cells counted, and blocks actually alive — for 24 real steps.

  2. THE REAL BUG. v9 drove every 3x3 block of 9 as a player. On ACTION1 it
     lifted the second block out of its pocket through a clear doorway and, since
     it believed a player had moved, advanced every patroller too: 81 wrong cells
     from one wrong entity. Rebuilt here by constructing the same model with no
     inert blocks declared, so the refutation is regenerated, not remembered.

  3. THE DISCRIMINATOR. Three earlier probes could not tell "every block is a
     player" from "only one is": the second block is walled in on every direction
     those probes used. The fix is a probe that reaches, using only down/left/
     right, a square where the real player can legally move UP — and then presses
     up. Player rises, look-alike sits still.

Writes artifacts/wm_viz/l4_evolve.json.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[4]))
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.backtest import run_backtest  # noqa: E402
from agents.wm.core import Action, Status, Timeline, Transition, diff_cells  # noqa: E402
from agents.wm.models.tu93 import tu93_world_model  # noqa: E402

OUT = Path("artifacts/wm_viz/tu93/data/l4_evolve.json")
SOLS = json.loads(Path("artifacts/wm_journal/tu93/solutions.json").read_text())
LEVEL = 4
OSC = ["ACTION3", "ACTION4"] * 12
REFUTE = ["ACTION3", "ACTION3", "ACTION3", "ACTION1"]
APPROACH = ["ACTION3", "ACTION3", "ACTION3", "ACTION4", "ACTION3", "ACTION3",
            "ACTION3", "ACTION3", "ACTION4", "ACTION4", "ACTION2"]
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


def main():
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))

    # ---- 1. the census -----------------------------------------------------
    env, raw = fresh(arc, gid)
    init = g(raw)
    r0, r1, c0, c1 = bounds(init)
    crop = lambda gr: [row[c0:c1 + 1] for row in gr[r0:r1 + 1]]  # noqa: E731

    model = tu93_world_model(version=11)
    state = model.reconstruct(init)
    census = [{
        "k": 0, "action": None, "grid": crop(init),
        "cells12": sum(1 for row in init for v in row if v == 12),
        "patrols": [list(p) for p in state.patrols],
        "players": [list(p) for p in state.players],
    }]
    for i, n in enumerate(OSC, start=1):
        raw = step(env, n)
        cur = g(raw)
        state, _ = model.step(state, Action(n))
        census.append({
            "k": i, "action": n, "grid": crop(cur),
            "cells12": sum(1 for row in cur for v in row if v == 12),
            "patrols": [list(p) for p in state.patrols],
            "players": [list(p) for p in state.players],
        })
    # The model is exact over this run, so its entity list IS the honest reading
    # of the frame. Verify that rather than assert it.
    tl = Timeline(init)
    prev = init
    env2, raw2 = fresh(arc, gid)
    for i, n in enumerate(OSC, start=1):
        raw2 = step(env2, n)
        cur = g(raw2)
        tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                             after_frame=cur, status=Status.RUNNING))
        prev = cur
    rep = run_backtest(tu93_world_model(version=11), tl)

    # ---- 2. the refutation v9 (drives every 9-block) ----------------------
    env3, raw3 = fresh(arc, gid)
    init3 = g(raw3)
    tl3 = Timeline(init3)
    prev = init3
    for i, n in enumerate(REFUTE, start=1):
        raw3 = step(env3, n)
        cur = g(raw3)
        tl3.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                              after_frame=cur, status=Status.RUNNING))
        prev = cur
    # v9 == the same code with no inert look-alikes declared.
    v9 = tu93_world_model(version=9, inert=())
    rep9 = run_backtest(v9, tl3)
    rep11 = run_backtest(tu93_world_model(version=11), tl3)
    m = rep9.first_mismatch
    refutation = {
        "actions": REFUTE,
        "step_index": m.step_index, "action": m.action, "cells_off": m.changed_cells,
        "predicted": crop(m.predicted_frame), "actual": crop(m.actual_frame),
        "v9_summary": rep9.summary(), "v11_summary": rep11.summary(),
    }

    # ---- 3. the discriminating probe --------------------------------------
    env4, raw4 = fresh(arc, gid)
    approach = []
    for n in APPROACH:
        raw4 = step(env4, n)
    before = g(raw4)
    mdl = tu93_world_model(version=11)
    s = mdl.reconstruct(g(fresh(arc, gid)[1]))
    for n in APPROACH:
        s, _ = mdl.step(s, Action(n))
    v9s = v9.reconstruct(g(fresh(arc, gid)[1]))
    for n in APPROACH:
        v9s, _ = v9.step(v9s, Action(n))
    raw4 = step(env4, "ACTION1")
    after = g(raw4)
    v9_after, _ = v9.step(v9s, Action("ACTION1"))
    v11_after, _ = mdl.step(s, Action("ACTION1"))
    approach = {
        "actions": APPROACH,
        "before": crop(before), "after": crop(after),
        "v9_predicted": crop(v9.render(v9_after)),
        "v11_predicted": crop(mdl.render(v11_after)),
        "v9_cells_off": diff_cells(v9.render(v9_after), after,
                                   {(63, c) for c in range(64)}),
        "v11_cells_off": diff_cells(mdl.render(v11_after), after,
                                    {(63, c) for c in range(64)}),
    }

    data = {
        "level": LEVEL, "origin": [r0, c0],
        "census": census,
        "census_backtest": rep.summary(),
        "refutation": refutation,
        "discriminator": approach,
        "solution_len": len(SOLS[str(LEVEL)]),
        "env_steps": env_steps[0],
    }
    OUT.write_text(json.dumps(data))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes) using {env_steps[0]} env steps")
    print(f"  census backtest: {rep.summary()}")
    print(f"  v9 on the refuting probe : {rep9.summary()}")
    print(f"  v11 on the same probe    : {rep11.summary()}")
    print(f"  discriminator: v9 off by {approach['v9_cells_off']} cells, "
          f"v11 off by {approach['v11_cells_off']}")
    lo = min(c["cells12"] for c in census)
    print(f"  cells of 12: {census[0]['cells12']} -> min {lo}; "
          f"patrollers alive throughout: "
          f"{sorted({len(c['patrols']) for c in census})}")


if __name__ == "__main__":
    main()
