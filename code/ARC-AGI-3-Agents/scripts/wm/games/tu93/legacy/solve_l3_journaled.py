"""Solve tu93 L3 the world-model way, journaling EVERY discovery as it happens.

This is the corrected workflow: the narrative is written by the solver at the
moment each thing is learned, into an append-only journal. The visualization
later reads that journal — no prose is hand-written into the viz generator, and
nothing depends on the author's context window surviving.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[5]))
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.wm.core import Action, Timeline, Transition, Status
from agents.wm.backtest import run_backtest
from agents.wm.planner import run_bfs
from agents.wm.journal import Journal
from agents.wm.models.tu93 import tu93_world_model

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L1 = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1","ACTION4","ACTION4","ACTION1"]
L2 = ["ACTION1","ACTION1","ACTION4","ACTION1","ACTION3","ACTION3","ACTION1","ACTION3","ACTION3",
      "ACTION2","ACTION4","ACTION2","ACTION3","ACTION3","ACTION3","ACTION2","ACTION4","ACTION2","ACTION4"]
PREFIX = L0 + L1 + L2
MOVES = ["ACTION1","ACTION2","ACTION3","ACTION4"]
R0,R1,C0,C1 = 14,50,8,56

steps_used = [0]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def crop(gr): return [row[C0:C1+1] for row in gr[R0:R1+1]] if gr else None

def entities(grid):
    """Everything the frame shows, without knowing what it means yet."""
    out = {}
    for name, val in [("player",9),("player_notch",4),("goal",14),
                      ("guard",8),("guard_notch",15),("fed_notch",11)]:
        cells = [(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==val]
        if cells:
            out[name] = {"count": len(cells),
                         "blocks": sorted({(min(r for r,_ in cells), min(c for _,c in cells))})
                         if name!="guard" else _guard_tls(grid)}
    unknown = sorted({v for row in grid for v in row} - {0,2,4,5,6,8,9,11,14,15})
    if unknown: out["UNKNOWN_VALUES"] = unknown
    return out

def _guard_tls(grid):
    cells = {(r,c) for r in range(64) for c in range(64) if grid[r][c] in (8,15,11)}
    tls, claimed = [], set()
    for r,c in sorted(cells):
        if (r,c) in claimed: continue
        block = {(r+i,c+j) for i in range(3) for j in range(3)}
        if block <= cells:
            claimed |= block; tls.append((r,c))
    return tls

def fresh(arc,gid):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    steps_used[0]+=1
    for n in PREFIX:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
        steps_used[0]+=1
    return env,raw

def run(env,names):
    """Execute actions for real, returning (raw, grid, died, cleared_levels)."""
    raw=None
    for n in names:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
        steps_used[0]+=1
        if raw is None or not raw.frame or raw.state.name=="GAME_OVER":
            return raw, None, True
    return raw, g(raw), False


def main():
    J = Journal("tu93", 3, reset=True)          # live provenance
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env,raw=fresh(arc,gid)
    init=g(raw)
    lv0=raw.levels_completed
    print(f"reached L3? levels_completed={lv0}")

    ents = entities(init)
    parts = []
    for k, v in ents.items():
        parts.append(f"{k}x{v['count']}" if isinstance(v, dict) and "count" in v else f"{k}={v}")
    J.observe(note=f"L3 initial frame. levels_completed={lv0}. Entities present: "
                   + ", ".join(parts) + ".",
              entities=ents, frame=crop(init))
    print("entities:", ents)

    # ---- carry the L2-certified model in and see whether it still holds -----
    model = tu93_world_model(version=7)
    s0 = model.reconstruct(init)
    J.author(version="v7", rules=[
        "player 3x3 (9) + facing notch (4); move 6px; wall(5) blocks",
        "goal 3x3 (14) -> LEVEL_COMPLETED",
        "row 63 = HUD bar -> ignore()",
        "N guards (8) each with facing notch (15); never move on their own",
        "entering the cell a guard faces -> it lunges into that cell -> GAME_OVER",
        "stepping onto a guard from another side removes it",
        "the guard that ate renders a 'fed' notch (11)",
    ], code="see agents/wm/tu93_model.py",
       changed="inherited unchanged from L2",
       because="carried forward; not yet tested against any L3 observation")

    # ---- probe: walk a few steps and see if the inherited model predicts them
    tl = Timeline(init); prev = init
    probe_actions = []
    for n in ["ACTION1","ACTION3","ACTION2","ACTION4"]:
        before = steps_used[0]
        raw2, grid2, died = run(env, [n])
        probe_actions.append(n)
        if died:
            tl.record(Transition(step_index=len(probe_actions), action=Action(n),
                                 before_frame=prev, after_frame=prev, status=Status.GAME_OVER))
            J.probe(actions=[n], hypothesis=f"does {n} behave as the L2 model predicts?",
                    observed="player was caught — GAME_OVER", died=True,
                    env_steps=steps_used[0]-before, frame=crop(prev))
            break
        moved = grid2 != prev
        st = Status.LEVEL_COMPLETED if raw2.levels_completed>lv0 else Status.RUNNING
        tl.record(Transition(step_index=len(probe_actions), action=Action(n),
                             before_frame=prev, after_frame=grid2, status=st))
        J.probe(actions=[n], hypothesis=f"does {n} behave as the L2 model predicts?",
                observed=("moved" if moved else "blocked (no change)"),
                died=False, env_steps=steps_used[0]-before,
                entities=entities(grid2), frame=crop(grid2))
        prev = grid2
        if st == Status.LEVEL_COMPLETED: break

    # ---- backtest the inherited model on what we just saw ------------------
    rep = run_backtest(model, tl)
    print("L3 backtest:", rep.summary())
    if rep.ok:
        J.author(version="v7", rules=["(unchanged)"], code="see agents/wm/tu93_model.py",
                 changed="nothing — inherited model survived L3 probing",
                 because=f"backtest {rep.matched}/{rep.total} exact on L3 observations",
                 backtest={"matched":rep.matched,"total":rep.total,"ok":True})
    else:
        m = rep.first_mismatch
        J.refute(version="v7", bug=m.summary(), step_index=m.step_index,
                 action=m.action, cells_off=m.changed_cells,
                 predicted_frame=crop(m.predicted_frame), actual_frame=crop(m.actual_frame))
        J.note(text="Inherited model failed on L3 — a new mechanic is present. "
                    "Next: identify the differing cells and author the rule.")

    # ---- plan in-model and execute -----------------------------------------
    env3,raw3 = fresh(arc,gid)
    s = model.reconstruct(g(raw3))
    sims=[0]; deaths=[0]
    inner = model.step
    def counting(st,a):
        ns,stat = inner(st,a); sims[0]+=1
        if stat==Status.GAME_OVER: deaths[0]+=1
        return ns,stat
    model.step = counting
    plan = run_bfs(model, s, [Action(a) for a in MOVES])
    model.step = inner
    names=[a.name for a in (plan.actions or [])]
    J.plan(version="v7", actions=names,
           stats={"sims":sims[0],"nodes":plan.nodes_expanded,"deaths":deaths[0],
                  "found":plan.found,"plan_len":len(names)})
    print(f"in-model plan: {len(names)} actions, {sims[0]} sims, {deaths[0]} imagined deaths")

    before=steps_used[0]
    lv=raw3.levels_completed
    raw4,grid4,died = run(env3,names)
    cleared = (not died) and raw4 is not None and raw4.levels_completed>lv
    J.execute(actions=names, result=("DIED" if died else ("CLEARED" if cleared else "no clear")),
              cleared=cleared, died_at=(len(names) if died else None),
              env_steps=steps_used[0]-before)
    print(f"execution: {'DIED' if died else ('L3 CLEARED' if cleared else 'no clear')}"
          f" (levels {lv} -> {raw4.levels_completed if raw4 and raw4.frame else 'n/a'})")

    from agents.wm.journal import summary
    print("journal:", J.path, "->", summary(J.entries()))

if __name__=="__main__":
    main()
