"""Probe L2 (black box). Tests whether the L1-learned guard rule transfers, and
how multiple guards behave. Reports each probe's real outcome."""
import sys
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION1" if False else "ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L1 = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1","ACTION4","ACTION4","ACTION1"]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def blocks(grid,val,size=3):
    """Find top-left corners of size x size blocks of `val`."""
    out=[]
    R,C=len(grid),len(grid[0])
    seen=set()
    for r in range(R-size+1):
        for c in range(C-size+1):
            if (r,c) in seen: continue
            if all(grid[r+i][c+j] in (val,15,4) for i in range(size) for j in range(size)) and \
               any(grid[r+i][c+j]==val for i in range(size) for j in range(size)):
                out.append((r,c))
                for i in range(size):
                    for j in range(size): seen.add((r+i,c+j))
    return out
def ptl(grid):
    cs=[(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==9]
    return (min(r for r,_ in cs),min(c for _,c in cs)) if cs else None

def run(arc,gid,path):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    for n in L0+L1+path:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
        if raw is None or not raw.frame: return raw,None
    return raw,g(raw)

arc=Arcade(operation_mode=OperationMode.OFFLINE)
gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
raw,grid=run(arc,gid,[])
print("L2 init: player",ptl(grid),"guards",blocks(grid,8),"levels",raw.levels_completed)

seq = sys.argv[1].split(",") if len(sys.argv)>1 else []
if seq:
    raw,grid=run(arc,gid,seq)
    if grid is None:
        print(f"path {'·'.join(x[-1] for x in seq)} -> {raw.state.name} (player gone)")
    else:
        print(f"path {'·'.join(x[-1] for x in seq)} -> {raw.state.name} L{raw.levels_completed} "
              f"player={ptl(grid)} guards={blocks(grid,8)}")
else:
    # walk the player around and confirm guards stay put
    for label,p in [("up x1",["ACTION1"]),("up x2",["ACTION1","ACTION1"]),
                    ("up x2 then left",["ACTION1","ACTION1","ACTION3"]),
                    ("left first",["ACTION3"]),("down",["ACTION2"])]:
        raw,gr=run(arc,gid,p)
        if gr is None: print(f"  {label:<18} -> {raw.state.name} (DIED)")
        else: print(f"  {label:<18} -> player={ptl(gr)} guards={blocks(gr,8)} {raw.state.name}")
