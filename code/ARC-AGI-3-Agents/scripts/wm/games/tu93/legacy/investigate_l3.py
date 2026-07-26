"""Investigate L3's new entity (value 12), journaling every probe as it runs.

L3 layout (observed): player (40,21), goal (22,21), a value-8 guard at (16,27)
facing DOWN, and a NEW value-12 block at (22,39) with its own notch (15) facing
DOWN. The only corridor to the goal runs up column 39 — straight into the
value-12 block from below, i.e. from the side it faces.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[5]))
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction
from agents.wm.journal import Journal, summary

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L1 = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1","ACTION4","ACTION4","ACTION1"]
L2 = ["ACTION1","ACTION1","ACTION4","ACTION1","ACTION3","ACTION3","ACTION1","ACTION3","ACTION3",
      "ACTION2","ACTION4","ACTION2","ACTION3","ACTION3","ACTION3","ACTION2","ACTION4","ACTION2","ACTION4"]
PREFIX = L0+L1+L2
R0,R1,C0,C1 = 14,46,18,50

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def crop(gr): return [row[C0:C1+1] for row in gr[R0:R1+1]] if gr else None
def tl(grid,val):
    cs=[(r,c) for r in range(64) for c in range(64) if grid[r][c]==val]
    return (min(r for r,_ in cs),min(c for _,c in cs)) if cs else None
def state_of(grid):
    return {"player":tl(grid,9),"guard8":tl(grid,8),"block12":tl(grid,12),
            "goal":tl(grid,14),"notch15_count":sum(1 for r in range(64) for c in range(64) if grid[r][c]==15)}

steps=[0]
def fresh(arc,gid):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={}); steps[0]+=1
    for n in PREFIX:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); steps[0]+=1
    return env,raw

def walk(env,names):
    raw=None
    for n in names:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); steps[0]+=1
        if raw is None or not raw.frame or raw.state.name=="GAME_OVER":
            return raw,None,True
    return raw,g(raw),False

def main():
    J=Journal("tu93",3,reset=True)
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env,raw=fresh(arc,gid); init=g(raw)
    st=state_of(init)
    J.observe(note=("L3 initial frame. A NEW entity appears: value 12, a 3x3 block at "
                    f"{st['block12']} carrying its own notch (15) — the same shape signature as the "
                    f"value-8 guard at {st['guard8']}. Player {st['player']}, goal {st['goal']}. "
                    "The only corridor to the goal runs up column 39, straight into the value-12 "
                    "block from below — which is the side its notch faces."),
              entities=st, frame=crop(init))
    print("init:",st)

    APPROACH=["ACTION4","ACTION4","ACTION4"]     # (40,21) -> (40,39)

    probes=[
      dict(name="reach the corridor foot below the new block",
           actions=APPROACH+["ACTION1"],                       # -> (34,39)
           hypothesis="can we get under the value-12 block at all, and does it react from 2 cells away?"),
      dict(name="step to the cell directly below it",
           actions=APPROACH+["ACTION1","ACTION1"],             # -> (28,39)
           hypothesis="value-8 guards kill when entered from the side they face; "
                      "does value-12 do the same? this is its facing cell"),
      dict(name="step onto the block itself",
           actions=APPROACH+["ACTION1","ACTION1","ACTION1"],   # -> (22,39)
           hypothesis="if it is not lethal, can we walk onto/through it like the guards we remove?"),
      dict(name="continue left toward the goal after the block",
           actions=APPROACH+["ACTION1","ACTION1","ACTION1","ACTION3"],
           hypothesis="if we survived the block, is the goal reachable along row 22?"),
    ]

    for p in probes:
        env,_=fresh(arc,gid)
        before=steps[0]
        raw2,grid2,died=walk(env,p["actions"])
        cost=steps[0]-before
        if died:
            J.probe(actions=p["actions"],hypothesis=p["hypothesis"],
                    observed="GAME_OVER — the player was caught/destroyed on this move",
                    died=True,env_steps=cost)
            print(f"  {p['name']:<46} -> DIED")
            continue
        s2=state_of(grid2)
        cleared = raw2.levels_completed>3
        obs=(f"survived. player={s2['player']}, block12={s2['block12']}, guard8={s2['guard8']}, "
             f"notches={s2['notch15_count']}"+(" — LEVEL CLEARED" if cleared else ""))
        J.probe(actions=p["actions"],hypothesis=p["hypothesis"],observed=obs,
                died=False,env_steps=cost,entities=s2,frame=crop(grid2))
        print(f"  {p['name']:<46} -> {obs}")

    print("\njournal:",J.path)
    print("summary:",summary(J.entries()))

if __name__=="__main__":
    main()
