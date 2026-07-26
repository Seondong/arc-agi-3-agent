"""Pin down the value-12 entity's rule on L3, journaling each probe live."""
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
PREFIX=L0+L1+L2
steps=[0]

def g(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else None
def tl(gr,v):
    cs=[(r,c) for r in range(64) for c in range(64) if gr[r][c]==v]
    return (min(r for r,_ in cs),min(c for _,c in cs)) if cs else None
def notch_of(gr,tlpos):
    if not tlpos: return None
    r,c=tlpos
    for i in range(3):
        for j in range(3):
            if gr[r+i][c+j]==15: return (i,j)
    return None

def fresh(arc,gid):
    env=arc.make(gid)
    raw=env.step(GameAction.RESET,data=GameAction.RESET.action_data.model_dump(),reasoning={}); steps[0]+=1
    for n in PREFIX:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); steps[0]+=1
    return env,raw

def trace(arc,gid,names):
    """Return per-step [(action, player, blk12, notch, alive)]."""
    env,raw=fresh(arc,gid); out=[]
    for n in names:
        a=GameAction.from_name(n); raw=env.step(a,data=a.action_data.model_dump(),reasoning={}); steps[0]+=1
        if raw is None or not raw.frame or raw.state.name=="GAME_OVER":
            out.append((n,None,None,None,False)); break
        gr=g(raw)
        out.append((n,tl(gr,9),tl(gr,12),notch_of(gr,tl(gr,12)),True))
    return out

def main():
    J=Journal("tu93",3)     # append to the journal started by investigate_l3
    arc=Arcade(operation_mode=OperationMode.OFFLINE)
    gid=next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))

    # --- probe A: does it move only when the PLAYER moves? -------------------
    t=trace(arc,gid,["ACTION1","ACTION1","ACTION4","ACTION1"])
    obs="; ".join(f"{a}: player={p} blk12={b}" for a,p,b,_,alive in t if alive)
    J.probe(actions=["ACTION1","ACTION1","ACTION4","ACTION1"],
            hypothesis="does the value-12 block advance on every turn, or only when the player "
                       "actually changes square? (A1 is blocked by a wall here)",
            observed=obs, died=not t[-1][4], env_steps=len(t))
    print("A. blocked-then-move:\n   ",obs)

    # --- probe B: how far does it go / does it turn around? ------------------
    t=trace(arc,gid,["ACTION4","ACTION3","ACTION4","ACTION3","ACTION4"])
    obs="; ".join(f"{a}: player={p} blk12={b} notch={n}" for a,p,b,n,alive in t if alive)
    J.probe(actions=["ACTION4","ACTION3","ACTION4","ACTION3","ACTION4"],
            hypothesis="the block moved DOWN three times — does it keep going, reverse at a wall, "
                       "or chase the player? shuffle left/right and watch it",
            observed=obs, died=not t[-1][4], env_steps=len(t))
    print("B. shuffle:\n   ",obs)

    # --- probe C: is contact lethal, or can it be stepped on like a guard? ---
    t=trace(arc,gid,["ACTION4","ACTION4","ACTION4"])
    died = not t[-1][4]
    J.probe(actions=["ACTION4","ACTION4","ACTION4"],
            hypothesis="the block descends the same column the player is walking along; "
                       "what happens when they meet — death, or removal like a value-8 guard?",
            observed=("GAME_OVER on contact — the player is destroyed, not the block"
                      if died else f"survived: {t[-1]}"),
            died=died, env_steps=len(t))
    print("C. collision ->","DIED" if died else t[-1])

    print("\nsummary:",summary(J.entries()))

if __name__=="__main__":
    main()
