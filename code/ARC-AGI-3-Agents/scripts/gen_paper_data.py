"""Build the interactive paper's data from the durable record — journals,
solutions, and the existing viz payloads — not from anyone's memory."""
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode
from arcengine import GameAction
from agents.wm.journal import load, summary

VIZ = Path("artifacts/wm_viz")
SOLS = json.loads(Path("artifacts/wm_journal/solutions.json").read_text())

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None

def level_frames():
    """One cropped opening frame per level, straight from the engine."""
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={})
    frames={}
    for lvl in range(5):
        grid=g(raw)
        if grid is None: break
        rs=[r for r in range(64) if any(grid[r][c] not in (5,6) for c in range(64))]
        cs=[c for c in range(64) if any(grid[r][c] not in (5,6) for r in range(64))]
        if not rs: break
        r0,r1,c0,c1=min(rs),max(rs),min(cs),max(cs)
        frames[lvl]={"grid":[row[c0:c1+1] for row in grid[r0:r1+1]]}
        if str(lvl) not in SOLS: break
        for n in SOLS[str(lvl)]:
            a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={})
            if raw is None or not raw.frame: break
    return frames

def main():
    levels=[]
    mechanics={
      0:"maze, player block, goal",
      1:"guard (8): stationary, lethal head-on, removable from behind",
      2:"three guards; the killing guard lunges and shows a 'fed' notch",
      3:"patroller (12): moves when the player moves, bounces off walls",
      4:"two player blocks under one action; goal renders over a patroller",
    }
    for lvl in range(5):
        j=load("tu93",lvl)
        s=summary(j) if j else {}
        sol=SOLS.get(str(lvl))
        levels.append({
          "level":lvl,
          "new_mechanic":mechanics.get(lvl,""),
          "solved":sol is not None,
          "solve_actions":len(sol) if sol else None,
          "journal_entries":len(j),
          "journal": [ {k:v for k,v in e.items() if k not in ("frame","predicted_frame","actual_frame","search_log")} for e in j ],
          "cost":s,
        })

    # in-model search stats (L2 study) + fidelity table
    inm=json.loads((VIZ/"inmodel_search.json").read_text()) if (VIZ/"inmodel_search.json").exists() else None
    l1s=json.loads((VIZ/"l1_search.json").read_text()) if (VIZ/"l1_search.json").exists() else None

    data={
      "title":"Learning an executable world model, one refutation at a time",
      "levels":levels,
      "frames":level_frames(),
      "inmodel":{"variants":inm["variants"],"totals":{
          "sims":inm["variants"][-1]["stats"]["sims"],
          "deaths":inm["variants"][-1]["stats"]["deaths"],
          "revisits":inm["variants"][-1]["stats"]["revisits"],
          "nodes":inm["variants"][-1]["stats"]["nodes"]}} if inm else None,
      "brute_force":{"attempts":l1s["totals"]["attempts"],"deaths":l1s["totals"]["deaths"],
                     "env_steps":l1s["totals"]["env_steps"],
                     "solution_len":l1s["solution_len"]} if l1s else None,
    }
    out=VIZ/"paper.json"; out.write_text(json.dumps(data))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    for L in levels:
        print(f"  L{L['level']}: solved={L['solved']} actions={L['solve_actions']} "
              f"journal={L['journal_entries']} cost={L['cost'].get('real_deaths','-')} deaths")

if __name__=="__main__":
    main()
