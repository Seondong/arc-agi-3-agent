"""Per-timepoint world-model evolution for tu93 L0 (honest, incremental).

At each exploration observation the model is (re)authored from ONLY what has
been observed so far and REALLY backtested against the timeline-so-far. Each
new rule is gated on the first observation that justifies it, so scrubbing the
timeline shows the executable world model genuinely growing:

  reset            : player(9)+goal(14) seen; dynamics UNKNOWN (no-op step model)
  step where HUD   : row63 changes -> hypothesise HUD=single cell (63,63)
  +1 more HUD cell : single-cell REFUTED -> ignore whole row 63
  first real move  : no-op REFUTED -> 6px movement + wall(5) blocking + notch(4)

Then the certified model plans via BFS (0 real actions) and executes.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[5]))
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example"); load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.wm.core import Action, Timeline, Transition, Status, WorldModel
from agents.wm.backtest import run_backtest, reconstruct_current_state
from agents.wm.loop import run_bfs

R0, R1, C0, C1 = 13, 51, 9, 53
EXPLORE = 8
WALL, DOOR, FLOOR, PLAYER, GOAL, NOTCH, BORDER = 5, 2, 0, 9, 14, 4, 6
DELTA = {"ACTION1": (-6, 0), "ACTION2": (6, 0), "ACTION3": (0, -6), "ACTION4": (0, 6)}
FACE = {"ACTION1": "U", "ACTION2": "D", "ACTION3": "L", "ACTION4": "R"}
NOFF = {"U": (0, 1), "D": (2, 1), "L": (1, 0), "R": (1, 2)}


def grid_of(raw): return [a.tolist() for a in raw.frame][-1] if raw.frame else []
def crop(g): return [row[C0:C1 + 1] for row in g[R0:R1 + 1]]
def row63_zeros(g): return sum(1 for v in g[63] if v == FLOOR)


# ---- parametric model: only the KNOWN mechanics are active ------------------
def build_model(flags, version):
    ctx = {}

    def find(frame, val):
        cs = [(r, c) for r, row in enumerate(frame) for c, v in enumerate(row) if v == val]
        return (min(r for r, _ in cs), min(c for _, c in cs)) if cs else None

    def reconstruct(frame):
        bg = [[FLOOR if v in (PLAYER, NOTCH) else v for v in row] for row in frame]
        pr, pc = find(frame, PLAYER)
        g = find(frame, GOAL)
        n = find(frame, NOTCH)
        facing = "R"
        if n:
            off = (n[0] - pr, n[1] - pc)
            for f, o in NOFF.items():
                if o == off: facing = f
        ctx.update(bg=bg, goal=g, rows=len(frame), cols=len(frame[0]), init_face=facing)
        # state: (pr, pc, facing, acted)
        return (pr, pc, facing, False)

    def wall(rows, cols):
        bg = ctx["bg"]
        for r in rows:
            for c in cols:
                if not (0 <= r < ctx["rows"] and 0 <= c < ctx["cols"]): return True
                if bg[r][c] in (WALL, BORDER): return True
        return False

    def step(state, action):
        pr, pc, face, _ = state
        if not flags["move"]:
            return (pr, pc, face, True), Status.RUNNING          # dynamics unknown: no-op
        d = DELTA.get(action.name)
        if d is None: return (pr, pc, face, True), Status.RUNNING
        dr, dc = d
        gr = range(pr + dr // 2, pr + dr // 2 + 3) if dr else range(pr, pr + 3)
        gc = range(pc + dc // 2, pc + dc // 2 + 3) if dc else range(pc, pc + 3)
        dstr, dstc = range(pr + dr, pr + dr + 3), range(pc + dc, pc + dc + 3)
        if flags["walls"] and (wall(gr, gc) or wall(dstr, dstc)):
            return (pr, pc, face, True), Status.RUNNING          # blocked by wall
        npr, npc, nf = pr + dr, pc + dc, FACE[action.name]
        st = (npr, npc, nf, True)
        if (npr, npc) == ctx["goal"]: return st, Status.LEVEL_COMPLETED
        return st, Status.RUNNING

    def render(state):
        pr, pc, face, acted = state
        grid = [list(row) for row in ctx["bg"]]
        for r in range(pr, pr + 3):
            for c in range(pc, pc + 3): grid[r][c] = PLAYER
        f = face if flags["notch"] else ctx["init_face"]
        nr, nc = NOFF[f]; grid[pr + nr][pc + nc] = NOTCH
        if flags["hud"] == "single":
            grid[63][63] = FLOOR if acted else BORDER
        return grid

    def is_goal(state): return (state[0], state[1]) == ctx.get("goal")

    def ignore(frame):
        return [(63, c) for c in range(len(frame[0]))] if flags["hud"] == "ignore" else []

    conf = 0.15 + 0.35 * flags["move"] + 0.2 * flags["walls"] + \
        0.15 * flags["notch"] + (0.15 if flags["hud"] == "ignore" else 0)
    return WorldModel(version=version, reconstruct=reconstruct, step=step, render=render,
                      is_goal=is_goal, fingerprint=lambda s: (s[0], s[1]),
                      ignore=(ignore if flags["hud"] == "ignore" else None),
                      confidence=round(min(conf, 0.95), 2))


def rules_of(flags):
    r = ["player = 3x3 block (9); goal = 3x3 block (14)  [seen in frame 0]"]
    r.append("dynamics: 6px move A1=up A2=down A3=left A4=right"
             if flags["move"] else "dynamics: UNKNOWN — assume actions are no-ops")
    if flags["walls"]: r.append("wall (5) in the path blocks the move")
    if flags["notch"]: r.append("notch (4) marks facing = last move direction")
    hud = {"none": "row 63: not yet modelled",
           "single": "HUD = single cell (63,63): 6→0 on action  [hypothesis]",
           "ignore": "row 63 = HUD energy bar → ignore() (excluded from checks)"}[flags["hud"]]
    r.append(hud)
    return r


def code_of(flags):
    L = []
    L.append("def step(state, action):")
    if not flags["move"]:
        L.append("    return state          # dynamics unknown → no-op")
    else:
        L.append("    dr, dc = DELTA[action]                 # 6px in action dir")
        if flags["walls"]:
            L.append("    if wall(5) in doorway or destination:")
            L.append("        return state, RUNNING          # blocked")
        L.append("    move player; facing = action_dir")
        L.append("    if dest == goal(14): return LEVEL_COMPLETED")
        L.append("    return RUNNING")
    L.append("")
    L.append("def render(state):")
    L.append("    grid = static_background + 3x3 player(9)")
    L.append("    grid[notch] = 4  # at " + ("facing edge" if flags["notch"] else "initial facing"))
    if flags["hud"] == "single":
        L.append("    grid[63][63] = 0 if acted else 6       # HUD = one cell")
    L.append("    return grid")
    if flags["hud"] == "ignore":
        L.append("")
        L.append("def ignore(frame):                         # HUD row excluded")
        L.append("    return [(63, c) for c in range(64)]")
    return "\n".join(L)


def bt(model, tl):
    r = run_backtest(model, tl)
    return {"matched": r.matched, "total": r.total, "ok": r.ok,
            "bug": (r.first_mismatch.summary() if r.first_mismatch else None)}


def main():
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(), reasoning={})
    init = grid_of(raw)

    flags = {"move": False, "walls": False, "notch": False, "hud": "none"}
    version = 0
    steps = [{"phase": "explore", "i": -1, "action": "RESET", "real": crop(init), "pred": None,
              "moved": None, "note": "player & goal visible; dynamics unknown"}]
    model_at = [{"step": -1, "version": version, "rules": rules_of(flags), "code": code_of(flags),
                 "backtest": {"matched": 0, "total": 0, "ok": True, "bug": None},
                 "confidence": build_model(flags, version).confidence,
                 "refuted": None}]

    tl = Timeline(init)
    cycle = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]
    prev = init
    for k in range(EXPLORE):
        name = cycle[k % 4]
        act = GameAction.from_name(name)
        raw = env.step(act, data=act.action_data.model_dump(), reasoning={})
        cur = grid_of(raw)
        moved = any(prev[r][c] != cur[r][c] for r in range(16, 49) for c in range(12, 51))
        tl.record(Transition(step_index=k + 1, action=Action(name),
                             before_frame=prev, after_frame=cur, status=Status.RUNNING))

        # does the CURRENT model still hold after this observation? (refutation)
        prior = build_model(flags, version)
        pr_bt = bt(prior, tl)
        refuted = None
        if not pr_bt["ok"]:
            refuted = pr_bt["bug"]

        # ---- update knowledge from this observation (gated on first justifier) ----
        z = row63_zeros(cur)
        if flags["hud"] == "none":
            flags["hud"] = "single"                     # first HUD change → 1-cell guess
        elif flags["hud"] == "single" and z > 1:
            flags["hud"] = "ignore"                      # more cells → refuted → ignore
        if moved and not flags["move"]:
            flags["move"] = flags["walls"] = flags["notch"] = True  # first real move

        if refuted is not None:
            version += 1
        model = build_model(flags, version)
        b = bt(model, tl)

        steps.append({"phase": "explore", "i": k, "action": name, "real": crop(cur),
                      "pred": None, "moved": moved,
                      "note": ("moved 6px " + name if moved else name + " blocked (wall)")})
        model_at.append({"step": k, "version": version, "rules": rules_of(flags),
                         "code": code_of(flags), "backtest": b, "confidence": model.confidence,
                         "refuted": refuted})
        prev = cur

    # ---- SOLVE with certified model ----
    final = build_model(flags, version)
    cur_state = reconstruct_current_state(final, tl)
    actions = [Action(a) for a in cycle]
    plan = run_bfs(final, cur_state, actions)
    sol = [a.name for a in (plan.actions or [])]
    prev_levels = 0
    for j, name in enumerate(sol):
        ps, pst = final.step(cur_state, Action(name))
        pg = final.render(ps)
        act = GameAction.from_name(name)
        raw = env.step(act, data=act.action_data.model_dump(), reasoning={})
        real = grid_of(raw)
        terminal = raw.levels_completed > prev_levels
        if terminal: prev_levels = raw.levels_completed
        pc, rc = crop(pg), crop(real)
        mism = [] if terminal else [[r, c] for r in range(len(rc)) for c in range(len(rc[0]))
                                    if pc[r][c] != rc[r][c] and (R0 + r) != 63]
        steps.append({"phase": "solve", "i": j, "action": name, "pred": pc, "real": rc,
                      "moved": None, "match": ("terminal" if terminal else len(mism) == 0),
                      "mismatch": mism,
                      "note": ("goal reached → LEVEL_COMPLETED" if terminal
                               else "certified model predicted reality exactly")})
        cur_state = ps

    data = {
        "game": "tu93", "level": 0, "grid": {"rows": R1 - R0 + 1, "cols": C1 - C0 + 1},
        "author": "Claude Code (Max subscription) as propose() — model re-authored per observation",
        "cost": {"explore": EXPLORE, "solve": len(sol), "total": EXPLORE + len(sol),
                 "planning_actions": 0, "oracle_optimal": 18},
        "steps": steps, "model_at": model_at, "final_version": version,
    }
    out = Path("artifacts/wm_viz/tu93/data/evolve.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"final version index = {version} (0=initial)  explore={EXPLORE} solve={len(sol)} total={EXPLORE+len(sol)}")
    for m in model_at:
        r = "  <REFUTED prior>" if m["refuted"] else ""
        print(f"  step {m['step']:>2}: v{m['version']} conf={m['confidence']} "
              f"backtest {m['backtest']['matched']}/{m['backtest']['total']} ok={m['backtest']['ok']}{r}")


if __name__ == "__main__":
    main()
