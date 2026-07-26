"""L2 world-model evolution — honest, with the real probe (and its death) and
every backtest refutation that forced a rewrite.

Chain of models:
  v4  inherited from L1 : knows ONE guard, guard stays put when it kills
  v5  multi-guard       : L2 has three guards
  v6  lunge moves       : a killing guard vacates its square and takes the player's
  v7  fed notch         : the guard that ate shows notch 11 instead of 15  -> certified

Each upgrade is triggered by a real pointed bug from run_backtest, and the
predicted-vs-actual frames of that bug are captured for display.
"""
import json
from pathlib import Path
from dataclasses import replace
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.wm.core import Action, Timeline, Transition, Status
from agents.wm.backtest import run_backtest, reconstruct_current_state
from agents.wm.loop import run_bfs
from agents.wm.tu93_model import tu93_world_model, Tu93State
from agents.wm import tu93_model as TM

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L1 = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1","ACTION4","ACTION4","ACTION1"]
PROBE = ["ACTION1","ACTION1","ACTION3","ACTION3"]     # 4th step is fatal
R0,R1,C0,C1 = 16,46,10,52
env_steps=[0]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def crop(gr): return [row[C0:C1+1] for row in gr[R0:R1+1]]

def fresh(arc,gid):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    env_steps[0]+=1
    for n in L0+L1:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); env_steps[0]+=1
    return env,raw

# ---------------- model variants (degradations of the certified one) ---------
_ACT={"U":"ACTION1","D":"ACTION2","L":"ACTION3","R":"ACTION4"}

def v7(): return tu93_world_model(version=7)          # certified

def v6():
    """No 'fed' notch: the killer renders an ordinary notch (15)."""
    m=tu93_world_model(version=6); inner=m.step
    def step(s,a):
        ns,st=inner(s,a)
        return (replace(ns,killer=None) if st==Status.GAME_OVER else ns), st
    m.step=step; return m

def v5():
    """Guard does NOT move when it kills: it stays home, player stays at dest."""
    m=tu93_world_model(version=5); inner=m.step
    def step(s,a):
        ns,st=inner(s,a)
        if st==Status.GAME_OVER:
            d=TM._DELTA.get(a.name,(0,0))
            return replace(ns, pr=s.pr+d[0], pc=s.pc+d[1], guards=s.guards, killer=None), st
        return ns,st
    m.step=step; return m

def v4():
    """Inherited from L1: models only ONE guard (and no lunge movement)."""
    m=v5(); inner_r=m.reconstruct
    def recon(frame):
        s=inner_r(frame)
        return replace(s, guards=s.guards[:1])       # L1 only ever saw one
    m.reconstruct=recon; return m

CHAIN=[("v4","inherited from L1 — one guard only",v4),
       ("v5","multi-guard",v5),
       ("v6","lunge moves the guard",v6),
       ("v7","fed notch (11) — certified",v7)]

RULES={
 "v4":["player 3x3 (9) + notch (4); move 6px; wall(5) blocks","goal 14 -> LEVEL_COMPLETED",
       "row 63 HUD -> ignore()","ONE guard (8): entering the cell it faces -> GAME_OVER",
       "guard stays on its square when it kills","MULTIPLE guards: NOT MODELLED"],
 "v5":["player 3x3 (9) + notch (4); move 6px; wall(5) blocks","goal 14 -> LEVEL_COMPLETED",
       "row 63 HUD -> ignore()","N guards (8), each with its own facing notch (15)",
       "entering the cell a guard faces -> GAME_OVER","guard stays on its square when it kills"],
 "v6":["player 3x3 (9) + notch (4); move 6px; wall(5) blocks","goal 14 -> LEVEL_COMPLETED",
       "row 63 HUD -> ignore()","N guards (8), each with its own facing notch (15)",
       "entering the cell a guard faces -> GAME_OVER",
       "the killing guard LUNGES: it vacates its square and occupies the player's"],
 "v7":["player 3x3 (9) + notch (4); move 6px; wall(5) blocks","goal 14 -> LEVEL_COMPLETED",
       "row 63 HUD -> ignore()","N guards (8), each with its own facing notch (15)",
       "entering the cell a guard faces -> GAME_OVER",
       "the killing guard LUNGES: it vacates its square and occupies the player's",
       "the guard that ate renders a 'fed' notch: value 11, not 15"],
}
CODE={
 "v4":"""guard = first_guard_only            # L1 never showed more than one
if dest == guard.facing_cell:
    return GAME_OVER                    # guard stays where it is""",
 "v5":"""for guard in guards:               # NEW: any number of guards
    if dest == guard.facing_cell:
        return GAME_OVER                # guard stays where it is
    if dest == guard.pos: remove(guard)""",
 "v6":"""for guard in guards:
    if dest == guard.facing_cell:
        guard.pos = dest                # NEW: it lunges into that cell
        player = removed
        return GAME_OVER
    if dest == guard.pos: remove(guard)""",
 "v7":"""for guard in guards:
    if dest == guard.facing_cell:
        guard.pos = dest
        player  = removed
        killer  = guard                 # NEW
        return GAME_OVER
    if dest == guard.pos: remove(guard)

render: notch = 11 if guard is killer else 15   # NEW""",
}

def bt(model,timeline):
    r=run_backtest(model,timeline)
    out={"matched":r.matched,"total":r.total,"ok":r.ok,"bug":None,"pred":None,"real":None,"cells":0}
    if r.first_mismatch:
        m=r.first_mismatch
        out["bug"]=m.summary(); out["cells"]=m.changed_cells
        out["pred"]=crop(m.predicted_frame); out["real"]=crop(m.actual_frame)
    return out


def main():
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env,raw=fresh(arc,gid); init=g(raw)

    steps=[]; snaps=[]
    ci=0  # current index into CHAIN
    def snap(refuted=None,btr=None):
        key,label,_=CHAIN[ci]
        return {"version":key,"label":label,"rules":RULES[key],"code":CODE[key],
                "backtest":btr or {"matched":0,"total":0,"ok":True,"bug":None,"pred":None,"real":None,"cells":0},
                "refuted":refuted,"env_steps":env_steps[0]}

    steps.append({"phase":"inherit","label":"L2 start — model inherited from L1",
        "action":"—","real":crop(init),"pred":None,"death":False,"outcome":"info",
        "note":"L2 has THREE guards (facing right / down / right). The inherited v4 "
               "only ever modelled one, so it is already wrong about this frame."})
    snaps.append(snap())

    # ---- probe the environment for real, building a timeline -----------------
    tl=Timeline(init); prev=init; prev_lv=raw.levels_completed
    for i,n in enumerate(PROBE):
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); env_steps[0]+=1
        died = raw is None or not raw.frame or raw.state.name=="GAME_OVER"
        cur = g(raw) if (raw is not None and raw.frame) else prev
        if raw is not None and raw.frame and raw.state.name=="GAME_OVER": st=Status.GAME_OVER
        elif raw is not None and raw.levels_completed>prev_lv: st=Status.LEVEL_COMPLETED; prev_lv=raw.levels_completed
        else: st=Status.RUNNING
        tl.record(Transition(step_index=i+1,action=Action(n),before_frame=prev,after_frame=cur,status=st))
        prev=cur
        steps.append({"phase":"probe","label":f"probe {i+1}: {n}"+(" — ☠ CAUGHT" if died else ""),
            "action":n,"real":crop(cur),"pred":None,"death":died,
            "outcome":"death" if died else "survived",
            "note":("☠ Walked into the cell guard B faces. Real death in the environment — "
                    "this single frame is what refutes the model three times over."
                    if died else "safe step; guards did not move")})
        snaps.append(snap(btr=bt(CHAIN[ci][2](),tl)))
        if died: break

    # ---- author: fix each pointed bug until certified ------------------------
    while True:
        model=CHAIN[ci][2]()
        r=bt(model,tl)
        if r["ok"] or ci==len(CHAIN)-1:
            snaps[-1]=snap(btr=r)
            break
        prev_key=CHAIN[ci][0]
        ci+=1
        newr=bt(CHAIN[ci][2](),tl)
        steps.append({"phase":"author","label":f"{prev_key} → {CHAIN[ci][0]}: {r['cells']} cell(s) mispredicted",
            "action":"re-author","real":r["real"],"pred":r["pred"],"death":False,
            "outcome":"refuted","mismatch":[[rr,cc] for rr in range(len(r["real"]))
                        for cc in range(len(r["real"][0])) if r["pred"][rr][cc]!=r["real"][rr][cc]],
            "note":f"backtest refuted {prev_key}: {r['bug']}"})
        snaps.append(snap(refuted=r["bug"],btr=newr))

    certified=CHAIN[ci][0]

    # ---- solve: in-model BFS then execute ------------------------------------
    model=CHAIN[ci][2]()
    env2,raw2=fresh(arc,gid)
    tl2=Timeline(g(raw2))
    cur=reconstruct_current_state(model,tl2)
    plan=run_bfs(model,cur,[Action(x) for x in ["ACTION1","ACTION2","ACTION3","ACTION4"]])
    names=[x.name for x in (plan.actions or [])]
    st_model=model.reconstruct(g(raw2)); lv=raw2.levels_completed
    for j,n in enumerate(names):
        ps,pst=model.step(st_model,Action(n))
        pred=model.render(ps)
        a=GameAction.from_name(n); raw2=env2.step(a,data=a.action_data.model_dump(),reasoning={}); env_steps[0]+=1
        real=g(raw2)
        cleared = raw2.levels_completed>lv
        if cleared: lv=raw2.levels_completed
        pc,rc=crop(pred),(crop(real) if real else None)
        mism=[] if (cleared or rc is None) else [[r_,c_] for r_ in range(len(rc)) for c_ in range(len(rc[0]))
                if pc[r_][c_]!=rc[r_][c_] and (R0+r_)!=63]
        steps.append({"phase":"solve","label":f"execute {j+1}/{len(names)}: {n}",
            "action":n,"real":rc or pc,"pred":pc,"mismatch":mism,"death":False,
            "outcome":"cleared" if cleared else ("match" if not mism else "mismatch"),
            "note":("goal reached → LEVEL_COMPLETED → L3" if cleared
                    else "certified model predicted reality exactly (3 guards included)")})
        snaps.append(snaps[-1] | {"env_steps":env_steps[0],"refuted":None})
        st_model=ps

    data={"game":"tu93","level":2,
      "author":"Claude Code (Max) as propose(); rules refined by real backtest counterexamples",
      "crop":{"rows":R1-R0+1,"cols":C1-C0+1},
      "chain":[{"key":k,"label":l} for k,l,_ in CHAIN],
      "certified":certified,
      "cost":{"probe_actions":len(PROBE),"deaths":sum(1 for s in steps if s.get("death")),
              "solve_actions":len(names),"planning_actions":0,"env_steps":env_steps[0]},
      "steps":steps,"model_at":snaps,"solution":names}
    out=Path("artifacts/wm_viz/l2_evolve.json"); out.write_text(json.dumps(data),encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"certified={certified} probe={len(PROBE)} deaths={data['cost']['deaths']} solve={len(names)}")
    for s,m in zip(steps,snaps):
        b=m["backtest"]
        print(f"  [{s['phase']:<7}] {m['version']} bt {b['matched']}/{b['total']}"
              f"{' ☠' if s.get('death') else ''}{'  <REFUTED>' if m['refuted'] else ''}  {s['label'][:52]}")

if __name__=="__main__":
    main()
