"""Fully log the IN-MODEL search (the thing that replaces real-environment
trial-and-error), so it can be studied as a research object in its own right.

Records, per expansion: the (state, action) tried, the model's verdict
(death / blocked / revisit / frontier / goal), depth, and the resulting state.
Mirrors agents/wm/planner.run_bfs semantics exactly, then asserts it produced
the same plan as the real planner.

Also runs the SAME search under earlier, less accurate model versions and
executes each resulting plan for real — showing how model fidelity determines
whether in-model search is trustworthy at all.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[5]))
import json
from collections import deque
from dataclasses import replace
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.wm.core import Action, Status
from agents.wm.planner import run_bfs
from agents.wm.models.tu93 import tu93_world_model
from agents.wm.models import tu93 as TM

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L1 = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1","ACTION4","ACTION4","ACTION1"]
MOVES = ["ACTION1","ACTION2","ACTION3","ACTION4"]
R0,R1,C0,C1 = 16,46,10,52

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def crop(gr): return [row[C0:C1+1] for row in gr[R0:R1+1]]
def cc(p): return [p[0]-R0,p[1]-C0] if p else None

def fresh(arc,gid):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    for n in L0+L1:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
    return env,raw

# ---- model variants (same chain as the L2 evolve viz) -----------------------
def v7(): return tu93_world_model(version=7)
def v6():
    m=tu93_world_model(version=6); inner=m.step
    def step(s,a):
        ns,st=inner(s,a)
        return (replace(ns,killer=None) if st==Status.GAME_OVER else ns), st
    m.step=step; return m
def v5():
    m=tu93_world_model(version=5); inner=m.step
    def step(s,a):
        ns,st=inner(s,a)
        if st==Status.GAME_OVER:
            d=TM._DELTA.get(a.name,(0,0))
            return replace(ns,pr=s.pr+d[0],pc=s.pc+d[1],guards=s.guards,killer=None),st
        return ns,st
    m.step=step; return m
def v4():
    m=v5(); inner_r=m.reconstruct
    def recon(f):
        s=inner_r(f); return replace(s,guards=s.guards[:1])
    m.reconstruct=recon; return m
CHAIN=[("v4",v4),("v5",v5),("v6",v6),("v7",v7)]


def logged_bfs(model, start, moves, max_depth=60):
    """Mirror of planner.run_bfs, logging every simulated interaction."""
    log=[]; n=0
    if model.is_goal(start):
        return [], log, {"nodes":0,"sims":0,"deaths":0,"revisits":0,"frontier":0}
    visited={model.fingerprint(start)}
    q=deque([(start,[])]); expanded=0
    deaths=revisits=frontier=0
    while q:
        state,path=q.popleft()
        if len(path)>=max_depth: continue
        expanded+=1
        for a in moves:
            n+=1
            nxt,status=model.step(state,Action(a))
            rec={"n":n,"depth":len(path)+1,"expanded_at":expanded,
                 "from":[state.pr,state.pc],"action":a,
                 "guards_before":len(state.guards)}
            if status==Status.GAME_OVER:
                deaths+=1
                rec.update(outcome="death",to=None,guards_after=len(nxt.guards))
                log.append(rec); continue
            if status==Status.LEVEL_COMPLETED or model.is_goal(nxt):
                rec.update(outcome="goal",to=[nxt.pr,nxt.pc],guards_after=len(nxt.guards))
                log.append(rec)
                return path+[Action(a)],log,{"nodes":expanded,"sims":n,"deaths":deaths,
                        "revisits":revisits,"frontier":frontier}
            key=model.fingerprint(nxt)
            if key in visited:
                revisits+=1
                rec.update(outcome=("blocked" if (nxt.pr,nxt.pc)==(state.pr,state.pc) else "revisit"),
                           to=[nxt.pr,nxt.pc],guards_after=len(nxt.guards))
            else:
                visited.add(key); q.append((nxt,path+[Action(a)])); frontier+=1
                rec.update(outcome="frontier",to=[nxt.pr,nxt.pc],guards_after=len(nxt.guards))
            log.append(rec)
    return [],log,{"nodes":expanded,"sims":n,"deaths":deaths,"revisits":revisits,"frontier":frontier}


def execute(arc,gid,names):
    """Run a plan for real; report what happened."""
    env,raw=fresh(arc,gid); lv=raw.levels_completed
    for i,n in enumerate(names):
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
        if raw is None or not raw.frame or raw.state.name=="GAME_OVER":
            return {"result":"DIED","at":i+1,"cleared":False}
        if raw.levels_completed>lv:
            return {"result":"CLEARED","at":i+1,"cleared":True}
    return {"result":"no clear","at":len(names),"cleared":False}


def main():
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env,raw=fresh(arc,gid); init=g(raw)

    # ---- per-version search + real execution of the resulting plan ----------
    variants=[]
    main_log=None
    for key,factory in CHAIN:
        m=factory(); s=m.reconstruct(init)
        plan,log,stats=logged_bfs(m,s,MOVES)
        names=[a.name for a in plan]
        ex=execute(arc,gid,names) if names else {"result":"no plan","at":0,"cleared":False}
        variants.append({"version":key,"plan_len":len(names),"plan":names,
                         "stats":stats,"execution":ex,
                         "guards_modelled":len(s.guards)})
        if key=="v7": main_log=log
        print(f"{key}: sims={stats['sims']:>4} nodes={stats['nodes']:>3} "
              f"deaths={stats['deaths']:>2} revisits={stats['revisits']:>3} "
              f"plan={len(names):>2} -> real execution: {ex['result']}")

    # sanity: our mirrored BFS must match the real planner
    m=v7(); s=m.reconstruct(init)
    ref=run_bfs(m,s,[Action(x) for x in MOVES])
    mine=[a.name for a in logged_bfs(m,m.reconstruct(init),MOVES)[0]]
    assert mine==[a.name for a in ref.actions], "mirror diverged from planner.run_bfs"
    print(f"mirror check OK (matches planner.run_bfs, {ref.nodes_expanded} nodes)")

    data={"game":"tu93","level":2,
      "about":"Full log of the IN-MODEL search: the simulated interactions that replace "
              "real-environment trial and error. Zero real actions are consumed here.",
      "crop":{"rows":R1-R0+1,"cols":C1-C0+1},
      "base_grid":crop(init),
      "variants":variants,
      "search":main_log,
      "certified":"v7",
      "real_ref":{"note":"the earlier brute-force search over the REAL engine on L1",
                  "attempts":41,"deaths":2,"env_steps":1233}}
    out=Path("artifacts/wm_viz/tu93/data/inmodel_search.json"); out.write_text(json.dumps(data),encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(main_log)} logged interactions)")

if __name__=="__main__":
    main()
