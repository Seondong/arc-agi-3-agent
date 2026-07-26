"""Solve any tu93 level with the world model, journaling live.

Usage: solve_level.py <level> [probe_actions_csv]

Carries the current model in, probes if asked, backtests on what was observed,
plans in-model (0 real actions), executes, and records everything to
artifacts/wm_journal/tu93_L<level>.jsonl.
"""
import sys, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.wm.core import Action, Timeline, Transition, Status
from agents.wm.backtest import run_backtest
from agents.wm.planner import run_bfs
from agents.wm.journal import Journal, summary
from agents.wm.tu93_model import tu93_world_model

SOLUTIONS_PATH = Path("artifacts/wm_journal/solutions.json")
MOVES = ["ACTION1","ACTION2","ACTION3","ACTION4"]
MODEL_VERSION_N = 11
MODEL_VERSION = f"v{MODEL_VERSION_N}"
steps=[0]

def load_solutions():
    if SOLUTIONS_PATH.exists():
        return {int(k):v for k,v in json.loads(SOLUTIONS_PATH.read_text()).items()}
    return {}

def save_solution(level, actions):
    s=load_solutions(); s[level]=actions
    SOLUTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOLUTIONS_PATH.write_text(json.dumps({str(k):v for k,v in sorted(s.items())}, indent=1))

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None

def prefix_for(level, sols):
    out=[]
    for i in range(level):
        if i not in sols: raise SystemExit(f"missing solution for L{i}; solve it first")
        out += sols[i]
    return out

def fresh(arc,gid,prefix):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={}); steps[0]+=1
    for n in prefix:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); steps[0]+=1
    return env,raw

def entities(grid):
    out={}
    for name,val in [("player",9),("goal",14),("guard",8),("patrol",12)]:
        cs=[(r,c) for r in range(64) for c in range(64) if grid[r][c]==val]
        if cs: out[name]=[min(r for r,_ in cs),min(c for _,c in cs)]
    unknown=sorted({v for row in grid for v in row}-{0,2,4,5,6,8,9,11,12,14,15})
    if unknown: out["UNKNOWN_VALUES"]=unknown
    return out

def main():
    level=int(sys.argv[1])
    probe=(sys.argv[2].split(",") if len(sys.argv)>2 and not sys.argv[2].startswith("--") and sys.argv[2] else [])
    sols=load_solutions()
    # Append by default: the journal is an audit trail, not a scratchpad.
    J=Journal("tu93",level,reset="--reset" in sys.argv)
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    prefix=prefix_for(level,sols)
    env,raw=fresh(arc,gid,prefix)
    init=g(raw); lv=raw.levels_completed
    if lv!=level:
        print(f"WARNING: expected to be on L{level} but levels_completed={lv}")
    ents=entities(init)
    J.observe(note=f"L{level} initial frame; levels_completed={lv}; entities={ents}", entities=ents)
    print(f"L{level} init: {ents}")

    model=tu93_world_model(version=MODEL_VERSION_N)
    s0=model.reconstruct(init)
    print(f"  model sees: guards={s0.guards} patrols={s0.patrols}")

    # ---- optional probing --------------------------------------------------
    tl=Timeline(init); prev=init
    for i,n in enumerate(probe):
        before=steps[0]
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); steps[0]+=1
        if raw is None or not raw.frame or raw.state.name=="GAME_OVER":
            # death returns no frame -> record None; only the status is checkable
            tl.record(Transition(step_index=i+1,action=Action(n),before_frame=prev,
                                 after_frame=None,status=Status.GAME_OVER))
            J.probe(actions=[n],hypothesis="does the carried model predict this move?",
                    observed="GAME_OVER",died=True,env_steps=steps[0]-before); break
        cur=g(raw)
        st=Status.LEVEL_COMPLETED if raw.levels_completed>lv else Status.RUNNING
        tl.record(Transition(step_index=i+1,action=Action(n),before_frame=prev,after_frame=cur,status=st))
        J.probe(actions=[n],hypothesis="does the carried model predict this move?",
                observed=str(entities(cur)),died=False,env_steps=steps[0]-before,entities=entities(cur))
        prev=cur

    # ---- certify -----------------------------------------------------------
    rep=run_backtest(model,tl)
    print(f"  backtest: {rep.summary()}")
    if rep.ok:
        J.author(version=MODEL_VERSION,rules=["carried model incl. guards + patrollers"],
                 code="see agents/wm/tu93_model.py",
                 changed="none",because=f"backtest {rep.matched}/{rep.total} exact on L{level} probes",
                 backtest={"matched":rep.matched,"total":rep.total,"ok":True})
    else:
        m=rep.first_mismatch
        J.refute(version=MODEL_VERSION,bug=m.summary(),step_index=m.step_index,action=m.action,
                 cells_off=m.changed_cells)
        J.note(text=f"L{level}: carried model refuted — a new mechanic is present. Investigate before planning.")
        print("  MODEL REFUTED — stopping before planning (uncertified models must not plan).")
        print("summary:",summary(J.entries())); return

    # ---- plan in-model -----------------------------------------------------
    env2,raw2=fresh(arc,gid,prefix)
    s=model.reconstruct(g(raw2))
    sims=[0]; deaths=[0]; inner=model.step
    def counting(st,a):
        ns,stat=inner(st,a); sims[0]+=1
        if stat==Status.GAME_OVER: deaths[0]+=1
        return ns,stat
    model.step=counting
    plan=run_bfs(model,s,[Action(a) for a in MOVES],max_depth=120)
    model.step=inner
    names=[a.name for a in (plan.actions or [])]
    J.plan(version=MODEL_VERSION,actions=names,
           stats={"sims":sims[0],"nodes":plan.nodes_expanded,"deaths":deaths[0],
                  "found":plan.found,"plan_len":len(names)})
    print(f"  in-model plan: found={plan.found} len={len(names)} sims={sims[0]} "
          f"nodes={plan.nodes_expanded} imagined_deaths={deaths[0]}")
    if not names:
        J.note(text=f"L{level}: no plan found in-model."); print("  NO PLAN"); return

    # ---- execute -----------------------------------------------------------
    before=steps[0]; lv2=raw2.levels_completed
    died=False
    for n in names:
        a=GameAction.from_name(n); raw2=env2.step(a,data=a.action_data.model_dump(),reasoning={}); steps[0]+=1
        if raw2 is None or not raw2.frame or raw2.state.name=="GAME_OVER":
            died=True; break
    cleared=(not died) and raw2.levels_completed>lv2
    J.execute(actions=names,result=("DIED" if died else ("CLEARED" if cleared else "no clear")),
              cleared=cleared,died_at=(len(names) if died else None),env_steps=steps[0]-before)
    print(f"  execution: {'DIED' if died else ('L%d CLEARED'%level if cleared else 'no clear')}")
    if cleared:
        save_solution(level,names)
        print(f"  saved solution for L{level} ({len(names)} actions)")
    print("summary:",summary(J.entries()))

if __name__=="__main__":
    main()
