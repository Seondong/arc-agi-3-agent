"""Probe L1 dynamics (black box): clear L0, then run an action list tracking the
player(9), the second block(8), their notches(4/15), the goal(14), HUD, state."""
import sys
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]

def g(raw): return [a.tolist() for a in raw.frame][-1]
def bb(grid,val):
    cs=[(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==val]
    if not cs: return None
    rs=[r for r,_ in cs]; cc=[c for _,c in cs]
    return (min(rs),min(cc))  # top-left
def z63(grid): return sum(1 for v in grid[63] if v==0)

seq = sys.argv[1].split(",") if len(sys.argv)>1 else ["ACTION1","ACTION4","ACTION4","ACTION4","ACTION4","ACTION4"]

arc=Arcade(operation_mode=OperationMode.OFFLINE)
gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
env=arc.make(gid)
raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
for n in L0:
    a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
grid=g(raw)
print(f"{'step':>4} {'act':>8} {'player9':>10} {'notch4':>10} {'block8':>10} {'notch15':>10} {'goal14':>10} {'hud0':>5} state")
def line(i,act,grid,raw):
    print(f"{i:>4} {act:>8} {str(bb(grid,9)):>10} {str(bb(grid,4)):>10} {str(bb(grid,8)):>10} "
          f"{str(bb(grid,15)):>10} {str(bb(grid,14)):>10} {z63(grid):>5} {raw.state.name} L{raw.levels_completed}")
line(-1,"L1-init",grid,raw)
for i,n in enumerate(seq):
    a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
    if not raw.frame:
        print(f"{i:>4} {n:>8}  (no frame) state={raw.state.name} L{raw.levels_completed}"); break
    grid=g(raw); line(i,n,grid,raw)
    if raw.state.name in ("GAME_OVER","WIN"): break
