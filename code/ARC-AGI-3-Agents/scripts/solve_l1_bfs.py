"""Black-box BFS solve of tu93 L1. Clears L0, then searches the real engine for
a path that clears L1, pruning any move that ends the game (enemy contact).
Never reads environment_files; the engine's GAME_OVER is the only death signal.
Surviving trajectories keep the enemy static, so player position keys the visited set."""
from collections import deque
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
MOVES = ["ACTION1","ACTION2","ACTION3","ACTION4"]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def ppos(grid):
    cs=[(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==9]
    if not cs: return None
    return (min(r for r,_ in cs), min(c for _,c in cs))

def replay(arc, gid, path):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    for n in L0+path:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
        if raw is None or not raw.frame: return None
    return raw

def main():
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    start=replay(arc,gid,[])
    sk=ppos(g(start))
    print("L1 start player:", sk, "levels:", start.levels_completed)
    seen={sk}; q=deque([[]]); nodes=0
    while q:
        path=q.popleft(); nodes+=1
        for mv in MOVES:
            raw=replay(arc,gid,path+[mv])
            if raw is None or raw.state.name=="GAME_OVER":
                continue  # dead branch (enemy or invalid)
            if raw.levels_completed>=2 or raw.state.name=="WIN":
                seq=path+[mv]
                print(f"\nSOLVED L1 in {len(seq)} actions ({nodes} nodes)")
                print("state:", raw.state.name, "levels:", raw.levels_completed)
                print("L1_ACTIONS="+",".join(seq))
                return
            k=ppos(g(raw))
            if k is None or k in seen: continue
            seen.add(k); q.append(path+[mv])
        if nodes%25==0: print(f"  nodes {nodes}, frontier {len(q)}, visited {len(seen)}")
        if nodes>4000: print("gave up"); return

if __name__=="__main__":
    main()
