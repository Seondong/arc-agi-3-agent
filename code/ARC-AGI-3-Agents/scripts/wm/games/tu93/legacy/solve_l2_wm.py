"""Solve L2 with the world model: certify on a real probe trajectory, then plan
in-model (0 real actions) and execute."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[5]))
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.wm.core import Action, Timeline, Transition, Status
from agents.wm.backtest import run_backtest, reconstruct_current_state
from agents.wm.loop import run_bfs
from agents.wm.models.tu93 import tu93_world_model

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L1 = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1","ACTION4","ACTION4","ACTION1"]
PROBE = ["ACTION1","ACTION1","ACTION3","ACTION3"]   # safe exploration on L2

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None

def fresh(arc,gid):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    for n in L0+L1:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
    return env,raw

arc=Arcade(operation_mode=OperationMode.OFFLINE)
gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))

model=tu93_world_model(version=5)
env,raw=fresh(arc,gid)
init=g(raw)
s0=model.reconstruct(init)
print(f"reconstruct: player=({s0.pr},{s0.pc}) guards={s0.guards}")

# --- certify on a real probe trajectory ---
tl=Timeline(init); prev=init; prev_lv=raw.levels_completed
for i,n in enumerate(PROBE):
    a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
    if raw is None or not raw.frame:
        # engine dropped the frame on death — record the death against the last frame
        tl.record(Transition(step_index=i+1,action=Action(n),before_frame=prev,
                             after_frame=prev,status=Status.GAME_OVER))
        break
    cur=g(raw)
    if raw.state.name=="GAME_OVER":
        st=Status.GAME_OVER
    elif raw.levels_completed>prev_lv:
        st=Status.LEVEL_COMPLETED; prev_lv=raw.levels_completed
    else:
        st=Status.RUNNING
    tl.record(Transition(step_index=i+1,action=Action(n),before_frame=prev,after_frame=cur,status=st))
    prev=cur
    if st==Status.GAME_OVER: break
rep=run_backtest(model,tl)
print("L2 BACKTEST:",rep.summary())
if rep.first_mismatch:
    m=rep.first_mismatch; pf,af=m.predicted_frame,m.actual_frame
    d=[(r,c,pf[r][c],af[r][c]) for r in range(len(af)) for c in range(len(af[0]))
       if pf[r][c]!=af[r][c] and r!=63][:12]
    print("  sample diffs:",d)

# --- in-model BFS (0 real actions) ---
env2,raw2=fresh(arc,gid)
tl2=Timeline(g(raw2))
cur=reconstruct_current_state(model,tl2)
plan=run_bfs(model,cur,[Action(a) for a in ["ACTION1","ACTION2","ACTION3","ACTION4"]])
names=[a.name for a in (plan.actions or [])]
print(f"IN-MODEL BFS: found={plan.found} len={len(names)}")
print("  plan:",names)

# --- execute for real ---
lv=raw2.levels_completed
for n in names:
    a=GameAction.from_name(n); raw2=env2.step(a,data=a.action_data.model_dump(),reasoning={})
    if raw2 is None or not raw2.frame:
        print("  DIED during execution at",n); break
else:
    print(f"EXECUTION: state={raw2.state.name} levels={raw2.levels_completed} (was {lv}) -> "
          f"{'L2 CLEARED' if raw2.levels_completed>lv else 'NOT cleared'}")
