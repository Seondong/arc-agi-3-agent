"""Observe any level's initial frame (black box). Usage: observe_level.py <level>"""
import sys
from collections import Counter
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

import json, pathlib
def _sols():
    p = pathlib.Path("artifacts/wm_journal/solutions.json")
    return {int(k): v for k, v in json.loads(p.read_text()).items()} if p.exists() else {}
SOL = _sols()
CH={0:'·',2:'▒',4:'◆',5:'█',6:'.',8:'♥',9:'@',11:'♠',12:'◘',14:'⊕',15:'♢'}

def g(raw): return [a.tolist() for a in raw.frame][-1]

def prefix_for(level):
    out=[]
    for i in range(level):
        if i not in SOL: raise SystemExit(f"no known solution for L{i}")
        out += SOL[i]
    return out

level=int(sys.argv[1]) if len(sys.argv)>1 else 3
arc=Arcade(operation_mode=OperationMode.OFFLINE)
gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
env=arc.make(gid)
raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
for n in prefix_for(level):
    a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
print(f"levels_completed={raw.levels_completed} state={raw.state.name}")
grid=g(raw)
inv=Counter(v for row in grid for v in row)
print("inventory:", dict(sorted(inv.items())))
known={0,2,4,5,6,8,9,11,14,15}
print("NEW values:", sorted(set(inv)-known) or "none")
def blocks(val):
    cells={(r,c) for r in range(64) for c in range(64) if grid[r][c]==val}
    tls=[];claimed=set()
    for r,c in sorted(cells):
        if (r,c) in claimed: continue
        b={(r+i,c+j) for i in range(3) for j in range(3)}
        if b<=cells: claimed|=b; tls.append((r,c))
    return tls, len(cells)
for v in sorted(inv):
    if v in (5,0,6,2): continue
    tls,n=blocks(v)
    print(f"  value {v}: {n} cells, 3x3 blocks at {tls}")
rs=[r for r in range(64) if any(grid[r][c] not in (5,6) for c in range(64))]
cs=[c for c in range(64) if any(grid[r][c] not in (5,6) for r in range(64))]
r0,r1,c0,c1=min(rs),max(rs),min(cs),max(cs)
print(f"\nregion rows {r0}-{r1} cols {c0}-{c1}:")
print("     "+"".join(f"{c%10}" for c in range(c0,c1+1)))
for r in range(r0,r1+1):
    print(f"R{r:02d}  "+"".join(CH.get(grid[r][c],'?') for c in range(c0,c1+1)))
