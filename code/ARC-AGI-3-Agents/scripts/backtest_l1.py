"""Certify the guard-aware world model on real L1 observations, then let its
in-model BFS plan L1 (0 real actions for planning) and execute the plan."""
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.wm.core import Action, Timeline, Transition, Status
from agents.wm.backtest import run_backtest, reconstruct_current_state
from agents.wm.loop import run_bfs
from agents.wm.tu93_model import tu93_world_model

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
# The exploration actually observed while probing the guard (incl. the fatal one).
OBS = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1"]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None

def fresh(arc, gid):
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(), reasoning={})
    for n in L0:
        a = GameAction.from_name(n); raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
    return env, raw

arc = Arcade(operation_mode=OperationMode.OFFLINE)
gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))

# ---- build an L1 timeline from real observations ----
env, raw = fresh(arc, gid)
init = g(raw)
tl = Timeline(init)
prev = init; prev_levels = raw.levels_completed
for i, n in enumerate(OBS):
    a = GameAction.from_name(n); raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
    cur = g(raw)
    status = Status.LEVEL_COMPLETED if raw.levels_completed > prev_levels else Status.RUNNING
    tl.record(Transition(step_index=i+1, action=Action(n), before_frame=prev,
                         after_frame=cur, status=status))
    prev = cur

model = tu93_world_model(version=3)
rep = run_backtest(model, tl)
print("L1 BACKTEST:", rep.summary())
if rep.first_mismatch:
    m = rep.first_mismatch
    pf, af = m.predicted_frame, m.actual_frame
    d = [(r,c,pf[r][c],af[r][c]) for r in range(len(af)) for c in range(len(af[0]))
         if pf[r][c]!=af[r][c] and r!=63][:10]
    print("  sample diffs:", d)

# ---- does the model correctly PREDICT the lethal move? ----
env2, raw2 = fresh(arc, gid)
s = model.reconstruct(g(raw2))
for n in ["ACTION1","ACTION4","ACTION4"]:
    s, _ = model.step(s, Action(n))
s_dead, st_dead = model.step(s, Action("ACTION4"))   # head-on into the guard
print(f"model predicts head-on approach -> {st_dead}  (reality: GAME_OVER)")

# ---- in-model BFS plan (0 real actions) ----
env3, raw3 = fresh(arc, gid)
tl3 = Timeline(g(raw3))
cur = reconstruct_current_state(model, tl3)
plan = run_bfs(model, cur, [Action(a) for a in ["ACTION1","ACTION2","ACTION3","ACTION4"]])
names = [a.name for a in (plan.actions or [])]
print(f"IN-MODEL BFS: found={plan.found} len={len(names)} plan={names}")

# ---- execute the plan for real ----
levels = raw3.levels_completed
ok = True
for n in names:
    a = GameAction.from_name(n); raw3 = env3.step(a, data=a.action_data.model_dump(), reasoning={})
    if raw3 is None or not raw3.frame:
        print("  execution died at", n); ok = False; break
print(f"EXECUTION: state={raw3.state.name} levels={raw3.levels_completed} "
      f"(was {levels}) -> {'L1 CLEARED' if raw3.levels_completed>levels else 'not cleared'}")
