"""Backtest the hand-authored tu93 world model against the real L0 timeline,
then check its BFS reaches the goal. Fast iteration loop for authoring."""
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

SOL = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
       "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]

def grid_of(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else []

arc = Arcade(operation_mode=OperationMode.OFFLINE)
gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
env = arc.make(gid)
raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(), reasoning={})
init = grid_of(raw)
tl = Timeline(init)
prev_levels = 0
for i, name in enumerate(SOL):
    before = grid_of(raw) if i == 0 else tl.current_frame
    act = GameAction.from_name(name)
    raw = env.step(act, data=act.action_data.model_dump(), reasoning={})
    after = grid_of(raw)
    if raw.levels_completed > prev_levels:
        status = Status.LEVEL_COMPLETED; prev_levels = raw.levels_completed
    else:
        status = Status.RUNNING
    tl.record(Transition(step_index=i+1, action=Action(name),
                         before_frame=before, after_frame=after, status=status))

model = tu93_world_model()
report = run_backtest(model, tl)
print("BACKTEST:", report.summary())
if not report.ok and report.first_mismatch:
    m = report.first_mismatch
    print(f"  first bug @step {m.step_index} after {m.action}: "
          f"frame_bad={m.frame_mismatch} status_bad={m.status_mismatch} "
          f"pred={m.predicted_status} actual={m.actual_status} cells_off={m.changed_cells}")
    # show a few differing cells
    pf, af = m.predicted_frame, m.actual_frame
    diffs = [(r, c, pf[r][c], af[r][c]) for r in range(len(af)) for c in range(len(af[0]))
             if pf[r][c] != af[r][c]][:12]
    print("  sample diffs (r,c,pred,actual):", diffs)

# Independent BFS check from the start state
start_raw_env = arc.make(gid)
r0 = start_raw_env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(), reasoning={})
tl0 = Timeline(grid_of(r0))
cur = reconstruct_current_state(model, tl0)
actions = [Action(a) for a in ["ACTION1","ACTION2","ACTION3","ACTION4"]]
plan = run_bfs(model, cur, actions)
print(f"BFS: found={plan.found} len={len(plan.actions) if plan.actions else 0} "
      f"actions={[a.name for a in (plan.actions or [])]}")
