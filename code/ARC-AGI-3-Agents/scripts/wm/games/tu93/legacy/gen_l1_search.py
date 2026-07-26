"""Instrument the L1 black-box BFS and record the WHOLE search — every candidate
move tried, deaths (GAME_OVER) pruned, revisits, and the growing frontier — so the
viewer can show how the solution was found by trial-and-death, not handed over."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[5]))
import json
from collections import deque
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
MOVES = ["ACTION1","ACTION2","ACTION3","ACTION4"]
DELTA = {"ACTION1":(-6,0),"ACTION2":(6,0),"ACTION3":(0,-6),"ACTION4":(0,6)}
R0,R1,C0,C1 = 18,38,9,53
env_steps = [0]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def crop(grid): return [row[C0:C1+1] for row in grid[R0:R1+1]]
def tl(grid,val):
    cs=[(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==val]
    if not cs: return None
    return [min(r for r,_ in cs),min(c for _,c in cs)]
def cc(p): return [p[0]-R0,p[1]-C0] if p else None

def replay(arc,gid,path):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    for n in L0+path:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); env_steps[0]+=1
        if raw is None or not raw.frame: return None
    return raw

def main():
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    start=replay(arc,gid,[]); sgrid=g(start); sk=tuple(tl(sgrid,9))
    base=crop(sgrid)

    seen={sk}; q=deque([[]]); attempts=[]; tried=deaths=0; solved_path=None
    while q and solved_path is None:
        path=q.popleft()
        parent_raw=replay(arc,gid,path); parent_grid=g(parent_raw)
        ppl=tl(parent_grid,9)
        for mv in MOVES:
            tried+=1
            raw=replay(arc,gid,path+[mv])
            dr,dc=DELTA[mv]; dest=[ppl[0]+dr,ppl[1]+dc]
            rec={"n":tried,"depth":len(path)+1,"path":"·".join(a[-1] for a in path) or "(start)",
                 "action":mv,"enemy":cc(tl(parent_grid,8)),"parent_player":cc(ppl)}
            if raw is None or raw.state.name=="GAME_OVER":
                deaths+=1
                rec.update(outcome="death",grid=crop(parent_grid),dest=None,dead_cell=cc(dest),
                           result_player=None)
            elif raw.levels_completed>=2 or raw.state.name=="WIN":
                solved_path=path+[mv]
                rec.update(outcome="solved",grid=crop(g(raw)),dead_cell=None,
                           result_player=cc(tl(g(raw),9)))
            else:
                k=tuple(tl(g(raw),9))
                out="revisit" if k in seen else "frontier"
                rec.update(outcome=out,grid=crop(g(raw)),dead_cell=None,result_player=cc(list(k)))
                if out=="frontier": seen.add(k); q.append(path+[mv])
            rec["counts"]={"tried":tried,"deaths":deaths,"visited":len(seen),"frontier":len(q)}
            attempts.append(rec)
            if solved_path is not None: break

    data={"game":"tu93","level":1,
          "method":"BFS over the real engine (black box). Each candidate move = a real replay; a move that returns GAME_OVER is a death and is pruned.",
          "crop":{"rows":R1-R0+1,"cols":C1-C0+1},
          "base_grid":base,
          "totals":{"attempts":tried,"deaths":deaths,"positions":len(seen),"env_steps":env_steps[0]},
          "solution":solved_path,"solution_len":len(solved_path),
          "attempts":attempts}
    out=Path("artifacts/wm_viz/tu93/data/l1_search.json"); out.write_text(json.dumps(data),encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"attempts={tried} deaths={deaths} positions={len(seen)} env_steps={env_steps[0]} sol_len={len(solved_path)}")
    for a in attempts:
        if a["outcome"] in ("death","solved"):
            print(f"  #{a['n']:>2} d{a['depth']} {a['path']} +{a['action']} -> {a['outcome'].upper()}"
                  + (f" @dest {a['dead_cell']}" if a['outcome']=='death' else ""))

if __name__=="__main__":
    main()
