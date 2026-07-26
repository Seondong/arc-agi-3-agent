"""Clear L0 (known solution), then OBSERVE the L1 initial frame — black box only.
Never reads environment_files; only steps the engine and inspects returned frames."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[5]))
from collections import Counter
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
CH={0:'·',2:'▒',4:'◆',5:'█',6:'.',8:'♥',9:'@',14:'⊕'}

def g(raw): return [a.tolist() for a in raw.frame][-1]
def bbox(grid,val):
    cs=[(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==val]
    if not cs: return None
    rs=[r for r,_ in cs]; cc=[c for _,c in cs]
    return (min(rs),min(cc),max(rs),max(cc),len(cs))

arc=Arcade(operation_mode=OperationMode.OFFLINE)
gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
env=arc.make(gid)
raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
for n in L0:
    a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
print("after L0: levels_completed =", raw.levels_completed, "state =", raw.state.name)
grid=g(raw)
inv=Counter(v for row in grid for v in row)
print("L1 value inventory:", dict(sorted(inv.items())))
print("available actions:", [GameAction.from_id(a).name for a in (raw.available_actions or [])])
for val in sorted(inv):
    if val in (5,0): continue  # skip walls/floor bulk
    print(f"  value {val}: bbox {bbox(grid,val)}")
# compact map crop
rs=[r for r in range(64) if any(grid[r][c] not in (5,6) for c in range(64))]
cs=[c for c in range(64) if any(grid[r][c] not in (5,6) for r in range(64))]
r0,r1,c0,c1=min(rs),max(rs),min(cs),max(cs)
print(f"\nnon-wall region rows {r0}-{r1} cols {c0}-{c1}:")
hdr="     "+"".join(f"{c%10}" for c in range(c0,c1+1))
print(hdr)
for r in range(r0,r1+1):
    print(f"R{r:02d}  "+"".join(CH.get(grid[r][c],'?') for c in range(c0,c1+1)))
