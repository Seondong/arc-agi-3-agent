"""Probe the L1 enemy rule precisely (black box).

Approaches the enemy from each side and records what happens, so the world model
can encode the real rule instead of the 2-datapoint guess. Also checks whether
the enemy ever moves when the player is at distance 2 (12px).
"""
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def tl(grid,val):
    cs=[(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==val]
    return (min(r for r,_ in cs),min(c for _,c in cs)) if cs else None

def run(arc,gid,path):
    """Replay L0 + path; return (state_name, grid_or_None, levels)."""
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    for n in L0+path:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
        if raw is None or not raw.frame:
            return (raw.state.name if raw else "NOFRAME"), None, (raw.levels_completed if raw else -1)
    return raw.state.name, g(raw), raw.levels_completed

def describe(arc,gid,label,path):
    st,grid,lv=run(arc,gid,path)
    if grid is None:
        print(f"  {label:<34} {'·'.join(x[-1] for x in path):<22} -> {st} (player gone)")
        return
    p,e=tl(grid,9),tl(grid,8)
    print(f"  {label:<34} {'·'.join(x[-1] for x in path):<22} -> {st} L{lv} player={p} enemy={e}"
          + ("  [ENEMY GONE]" if e is None else ""))

arc=Arcade(operation_mode=OperationMode.OFFLINE)
gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
st,grid,lv=run(arc,gid,[])
print(f"L1 init: player={tl(grid,9)} enemy={tl(grid,8)} enemy_notch={tl(grid,15)} goal={tl(grid,14)}")
print("  (enemy notch at col == enemy col -> facing LEFT)\n")

# Enemy sits at (27,36). Player starts (33,12).
print("APPROACHES:")
# from the LEFT (enemy's facing side) along row 27
describe(arc,gid,"left, stop at dist 2 (col 24)", ["ACTION1","ACTION4","ACTION4"])
describe(arc,gid,"left, step to adjacent (col 30)", ["ACTION1","ACTION4","ACTION4","ACTION4"])
# from BELOW along col 36
describe(arc,gid,"below, at (33,36) dist 1",       ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4"])
describe(arc,gid,"below, step UP onto enemy",      ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1"])
# from the RIGHT along row 27 (go under, past, and come back up on col 42)
describe(arc,gid,"right side, up at col 42",       ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION4","ACTION1"])
describe(arc,gid,"right, then step LEFT onto enemy",["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION4","ACTION1","ACTION3"])

print("\nDOES THE ENEMY EVER MOVE ON ITS OWN? (idle at distance 2, several turns)")
base=["ACTION1","ACTION4","ACTION4"]           # player at (27,24), dist 2 from enemy
for k in range(1,5):
    describe(arc,gid,f"idle x{k} at dist 2 (blocked up)", base+["ACTION1"]*k)
