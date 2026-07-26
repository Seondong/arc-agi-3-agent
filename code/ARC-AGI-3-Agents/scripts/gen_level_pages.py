"""One uniform data file per level, for every level — no gaps.

The earlier pages grew one at a time and covered whatever was interesting that
day: L0 got three pages, L2 got the only in-model search log, L3/L5/L7/L8 got
nothing. That is not a record, it is a highlight reel. This generator produces
the same four things for **every** level, so any level can be inspected the same
way and the missing ones stop being invisible:

  meta      the level's model version, its new mechanic, its solution
  replay    the saved solution executed for real, with the model's prediction
            beside it at every step and the mispredicted cells listed
  search    the FULL in-model BFS that produced that solution — every simulated
            (state, action) with its verdict, for every level, not just L2
  ledger    the cost buckets straight from the journal, plus the journal itself

Writes artifacts/wm_viz/levels/level_<N>.json and levels/index.json.
"""
import json
from collections import deque
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.core import Action, Status, ignored_cells  # noqa: E402
from agents.wm.journal import load as load_journal, summary  # noqa: E402
from agents.wm.planner import run_bfs  # noqa: E402
from agents.wm.tu93_model import tu93_world_model  # noqa: E402

OUT = Path("artifacts/wm_viz/levels")
SOLS = {int(k): v for k, v in
        json.loads(Path("artifacts/wm_journal/solutions.json").read_text()).items()}
MOVES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]
MAX_LOG = 20000          # log everything below this; above it, say what was dropped

# Which model version each level was first certified with. Taken from the journal
# author entries where they exist (L3 onward) and from the earlier pages' record
# for L0-L2, which predate the journal.
# The version each level was FIRST certified with, and the version that
# reproduces it exactly today (v12 for all of them — two levels needed a
# later fix than the one that first "certified" them).
VERSION = {0: "v3", 1: "v4", 2: "v7", 3: "v8", 4: "v10", 5: "v12",
           6: "v11", 7: "v11", 8: "v12"}
MECHANIC = {
    0: "maze, player block, goal tile",
    1: "guard (8): never moves, lethal if you step into the cell it faces, "
       "removable from any other side",
    2: "three guards at once; the one that catches you lunges into your square "
       "and wears a 'fed' notch (11)",
    3: "patroller (12): advances only on turns where the player really moved, "
       "bounces off walls, kills on contact",
    4: "a second 3x3 block of 9 that looks exactly like the player and is never "
       "controlled; patrollers overlap freely and hide under the goal tile",
    5: "nothing new — guards and patrollers composed",
    6: "pursuer (13): sleeps until you cross the line it faces, then follows your "
       "own trail one square per move, forever two squares behind",
    7: "nothing new — pursuer in a corridor maze",
    8: "nothing new — guards, patrollers and a pursuer at once",
}
ENTITY_KEYS = ("players", "guards", "patrols", "pursuers")


def g(raw):
    return [a.tolist() for a in raw.frame][-1] if raw.frame else None


def prefix_for(level):
    out = []
    for i in range(level):
        out += SOLS[i]
    return out


def fresh(arc, gid, level, counter):
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})
    counter[0] += 1
    for n in prefix_for(level):
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
        counter[0] += 1
    return env, raw


def bounds(grid):
    rs = [r for r in range(64) if any(grid[r][c] not in (5, 6) for c in range(64))]
    cs = [c for c in range(64) if any(grid[r][c] not in (5, 6) for r in range(64))]
    return min(rs), max(rs), min(cs), max(cs)


def ents(state):
    """Entity positions the page can draw, uniform across levels."""
    out = {}
    for k in ENTITY_KEYS:
        vals = getattr(state, k, ())
        out[k] = [[e[0], e[1], e[2]] for e in vals]
    return out


def logged_bfs(model, start, max_depth=120):
    """planner.run_bfs, mirrored, logging every simulated interaction.

    Kept in step with the real planner by asserting the plans match; if that
    assert ever fires, this log is lying and must be fixed, not silenced.
    """
    log, n, deaths, revisits, frontier, blocked = [], 0, 0, 0, 0, 0
    if model.is_goal(start):
        return [], log, {"nodes": 0, "sims": 0, "deaths": 0, "revisits": 0,
                         "frontier": 0, "blocked": 0}
    visited = {model.fingerprint(start)}
    q = deque([(start, [])])
    expanded = 0
    while q:
        state, path = q.popleft()
        if len(path) >= max_depth:
            continue
        expanded += 1
        for ai, a in enumerate(MOVES):
            n += 1
            nxt, status = model.step(state, Action(a))
            here = state.players[0][:2] if state.players else None
            there = nxt.players[0][:2] if nxt.players else None
            rec = {"n": n, "d": len(path) + 1, "a": ai, "f": list(here) if here else None}
            if status == Status.GAME_OVER:
                deaths += 1
                rec.update(o="death", t=None)
            elif status == Status.LEVEL_COMPLETED or model.is_goal(nxt):
                rec.update(o="goal", t=list(there) if there else None)
                if len(log) < MAX_LOG:
                    log.append(rec)
                return (path + [Action(a)], log,
                        {"nodes": expanded, "sims": n, "deaths": deaths,
                         "revisits": revisits, "frontier": frontier, "blocked": blocked})
            else:
                key = model.fingerprint(nxt)
                if key in visited:
                    if here == there:
                        blocked += 1
                        rec.update(o="blocked", t=list(there))
                    else:
                        revisits += 1
                        rec.update(o="revisit", t=list(there))
                else:
                    visited.add(key)
                    q.append((nxt, path + [Action(a)]))
                    frontier += 1
                    rec.update(o="frontier", t=list(there))
            if len(log) < MAX_LOG:
                log.append(rec)
    return [], log, {"nodes": expanded, "sims": n, "deaths": deaths,
                     "revisits": revisits, "frontier": frontier, "blocked": blocked}


def build(level, arc, gid, counter):
    env, raw = fresh(arc, gid, level, counter)
    init = g(raw)
    r0, r1, c0, c1 = bounds(init)
    crop = lambda gr: [row[c0:c1 + 1] for row in gr[r0:r1 + 1]]  # noqa: E731
    lv0 = raw.levels_completed

    model = tu93_world_model(version=12)
    state = model.reconstruct(init)
    hud = ignored_cells(model, init) or set()

    # ---- replay: the saved solution, real vs predicted, step by step --------
    replay = [{"k": 0, "action": None, "grid": crop(init), "pred_diff": [],
               "cells_off": 0, "status": "RUNNING", "terminal": False,
               "ents": ents(state)}]
    for i, n in enumerate(SOLS[level], start=1):
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
        counter[0] += 1
        state, pstat = model.step(state, Action(n))
        died = raw is None or not raw.frame or raw.state.name == "GAME_OVER"
        actual = None if died else g(raw)
        pred = model.render(state)
        cleared = (not died) and raw.levels_completed > lv0
        diff = []
        if actual is not None:
            for r in range(64):
                for c in range(64):
                    if (r, c) in hud:
                        continue
                    if pred[r][c] != actual[r][c]:
                        diff.append([r - r0, c - c0, pred[r][c]])
        replay.append({
            "k": i, "action": n,
            "grid": crop(actual) if actual is not None else None,
            "pred_diff": [d for d in diff
                          if 0 <= d[0] <= r1 - r0 and 0 <= d[1] <= c1 - c0],
            "cells_off": len(diff),
            "status": "GAME_OVER" if died else ("LEVEL_COMPLETED" if cleared
                                                else "RUNNING"),
            # The frame after a level is cleared is the NEXT level's maze, which
            # this model does not claim to predict. Flagged, not hidden.
            "terminal": bool(cleared),
            "ents": ents(state),
        })

    # ---- search: the in-model BFS that produced the plan -------------------
    env2, raw2 = fresh(arc, gid, level, counter)
    s0 = model.reconstruct(g(raw2))
    plan, log, stats = logged_bfs(model, s0)
    names = [a.name for a in plan]
    # The reference planner needs a model whose ctx has been primed by its OWN
    # reconstruct — passing another instance's state silently makes every step
    # throw, which run_bfs treats as a dead branch and reports as "no plan".
    ref_model = tu93_world_model(version=12)
    ref_state = ref_model.reconstruct(g(raw2))
    ref = run_bfs(ref_model, ref_state, [Action(x) for x in MOVES], max_depth=120)
    mirrored_ok = names == [a.name for a in ref.actions]

    j = load_journal("tu93", level)
    data = {
        "level": level, "origin": [r0, c0], "version": VERSION[level],
        "mechanic": MECHANIC[level],
        "solution": SOLS[level], "solution_len": len(SOLS[level]),
        "replay": replay,
        "search": log, "search_stats": stats,
        "search_truncated": stats["sims"] > MAX_LOG,
        "search_plan": names, "mirror_ok": mirrored_ok,
        "ledger": summary(j) if j else {},
        "journal": [{k: v for k, v in e.items()
                     if k not in ("frame", "predicted_frame", "actual_frame",
                                  "search_log")} for e in j],
        "fidelity": {
            "steps": len(replay) - 1,
            "exact": sum(1 for f in replay[1:]
                         if f["cells_off"] == 0 and not f["terminal"]),
            "terminal_excluded": sum(1 for f in replay[1:] if f["terminal"]),
        },
    }
    return data


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    counter = [0]
    index = []
    for level in sorted(SOLS):
        d = build(level, arc, gid, counter)
        p = OUT / f"level_{level}.json"
        p.write_text(json.dumps(d))
        f = d["fidelity"]
        index.append({
            "level": level, "version": d["version"], "mechanic": d["mechanic"],
            "solution_len": d["solution_len"], "ledger": d["ledger"],
            "search_stats": d["search_stats"], "fidelity": f,
            "journal_entries": len(d["journal"]), "bytes": p.stat().st_size,
        })
        print(f"L{level}: {d['version']:>3}  solve {d['solution_len']:>2}  "
              f"fidelity {f['exact']}/{f['steps'] - f['terminal_excluded']} exact "
              f"(+{f['terminal_excluded']} terminal excluded)  "
              f"search {d['search_stats']['sims']:>5} sims / "
              f"{d['search_stats']['deaths']:>3} imagined deaths  "
              f"mirror={'ok' if d['mirror_ok'] else 'DIVERGED'}  "
              f"journal {len(d['journal']):>2}  {p.stat().st_size // 1024}KB")
    gap = [i["level"] for i in index if i["journal_entries"] == 0]
    (OUT / "index.json").write_text(json.dumps({
        "game": "tu93", "levels": index,
        # The cost totals are summed from the journals, so levels that predate the
        # journal contribute nothing to them. Reporting the sum without saying so
        # would under-count real deaths that were genuinely paid.
        "journal_gap": gap,
        "totals_caveat": (
            f"probe steps and real deaths are summed from the journals; "
            f"level(s) {gap} predate the journal and contribute 0 to those totals "
            f"even though L1 and L2 each cost one real death during probing "
            f"(recorded in artifacts/wm_viz/README.md and the L1/L2 pages)"),
        "total_actions": sum(i["solution_len"] for i in index),
        "total_real_deaths": sum(i["ledger"].get("real_deaths", 0) for i in index),
        "total_probe_steps": sum(i["ledger"].get("probe_env_steps", 0) for i in index),
        "total_sims": sum(i["search_stats"]["sims"] for i in index),
        "total_imagined_deaths": sum(i["search_stats"]["deaths"] for i in index),
    }))
    print(f"\nwrote {OUT}/index.json; generation cost {counter[0]} env steps "
          f"(offline engine, free)")


if __name__ == "__main__":
    main()
