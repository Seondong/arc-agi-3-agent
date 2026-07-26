"""Probe tu93 dynamics: per-step player/notch/HUD/goal, to author a world model."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

SOL = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
       "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]

def bbox(grid, val):
    cells = [(r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v == val]
    if not cells: return None
    rs=[r for r,_ in cells]; cs=[c for _,c in cells]
    return (min(rs), min(cs), max(rs), max(cs), len(cells))

def grid_of(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else []

arc = Arcade(operation_mode=OperationMode.OFFLINE)
gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
env = arc.make(gid)
raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(), reasoning={})
g = grid_of(raw)
# value inventory
from collections import Counter
inv = Counter(v for row in g for v in row)
print("value inventory:", dict(sorted(inv.items())))
print(f"{'step':>4} {'act':>8} {'player9(r,c..cnt)':>26} {'notch4':>18} {'(63,63)':>8} {'goal14':>18} state")
def notch(g): return bbox(g,4)
def line(i, act, g, raw):
    p=bbox(g,9); n=notch(g); h=g[63][63]; gl=bbox(g,14)
    print(f"{i:>4} {act:>8} {str(p):>26} {str(n):>18} {h:>8} {str(gl):>18} {raw.state.name} L{raw.levels_completed}")
line(-1,"RESET",g,raw)
for i,a in enumerate(SOL):
    act=GameAction.from_name(a)
    raw=env.step(act, data=act.action_data.model_dump(), reasoning={})
    g=grid_of(raw)
    line(i,a,g,raw)
