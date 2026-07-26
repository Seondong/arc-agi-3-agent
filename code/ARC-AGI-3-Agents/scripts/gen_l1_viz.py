"""Generate L1 solution-playback viz data (black-box brute-force solve).
Captures per-step reality grid + entity positions + the enemy-defeat & goal moments."""
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction

L0 = ["ACTION4","ACTION2","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2","ACTION2",
      "ACTION3","ACTION3","ACTION2","ACTION4","ACTION4","ACTION2","ACTION4","ACTION1","ACTION4","ACTION2"]
L1 = ["ACTION1","ACTION4","ACTION4","ACTION2","ACTION4","ACTION4","ACTION1","ACTION4","ACTION4","ACTION1"]
R0,R1,C0,C1 = 18,38,9,53

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def crop(grid): return [row[C0:C1+1] for row in grid[R0:R1+1]]
def bb(grid,val):
    cs=[(r,c) for r,row in enumerate(grid) for c,v in enumerate(row) if v==val]
    if not cs: return None
    rs=[r for r,_ in cs]; cc=[c for _,c in cs]
    return [min(rs)-R0,min(cc)-C0]

arc=Arcade(operation_mode=OperationMode.OFFLINE)
gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
env=arc.make(gid)
raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
for n in L0:
    a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
init=g(raw)
steps=[{"i":-1,"action":"L1 start","real":crop(init),"enemy":bb(init,8),"goal":bb(init,14),
        "note":"L1: player (bottom-left), goal 14 (top-right), enemy 8 (center) — a directional guard","tag":"start"}]
prev_enemy=bb(init,8)
prev_levels=1
for i,n in enumerate(L1):
    a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
    grid=g(raw)
    enemy=bb(grid,8) if grid else None
    cleared = raw.levels_completed>prev_levels
    defeated = (prev_enemy is not None and enemy is None and not cleared)
    tag="move"
    note="move "+n
    if defeated:
        tag="defeat"; note="stepped onto the enemy FROM BELOW → enemy removed (safe). Head-on from its facing side would have been fatal."
    if cleared:
        tag="clear"; note="reached goal 14 → LEVEL_COMPLETED → L2"
        prev_levels=raw.levels_completed
    steps.append({"i":i,"action":n,"real":crop(grid) if grid else None,
                  "enemy":enemy,"goal":bb(grid,14) if grid else None,"note":note,"tag":tag})
    prev_enemy=enemy

data={"game":"tu93","level":1,"grid":{"rows":R1-R0+1,"cols":C1-C0+1},
      "method":"brute-force BFS over the real engine (black-box; death-pruned)",
      "solution":L1,"actions":len(L1),
      "mechanic":"Enemy (value 8) is static until the player is adjacent. Adjacent from the side it FACES (notch 15 = left) -> it lunges -> GAME_OVER. Stepped on from below/behind -> enemy removed.",
      "steps":steps}
out=Path("artifacts/wm_viz/l1.json"); out.write_text(json.dumps(data),encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size} bytes, {len(steps)} frames)")
print("defeat step:", next((s['i'] for s in steps if s['tag']=='defeat'),None),
      "| clear step:", next((s['i'] for s in steps if s['tag']=='clear'),None))
