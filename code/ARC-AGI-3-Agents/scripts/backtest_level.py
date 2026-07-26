"""Backtest the tu93 model against a real action sequence on any level.

Replays saved solutions to the level, runs the actions given on the command line
for real, and demands an exact frame match at every step. On the first divergence
it prints the predicted and actual grids side by side with the wrong cells marked
— a pointed bug, not a score.

Usage: backtest_level.py ACTION3,ACTION4,... [--level N] [--journal]
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.backtest import run_backtest  # noqa: E402
from agents.wm.core import Action, Status, Timeline, Transition  # noqa: E402
from agents.wm.journal import Journal  # noqa: E402
from agents.wm.tu93_model import tu93_world_model  # noqa: E402

SOLUTIONS_PATH = Path("artifacts/wm_journal/solutions.json")
MODEL_VERSION_N = 11
MODEL_VERSION = f"v{MODEL_VERSION_N}"
CH = {0: '·', 2: '▒', 4: '◆', 5: '█', 6: '.', 8: '♥', 9: '@', 11: '♠', 12: '◘',
      14: '⊕', 15: '♢'}


def g(raw):
    return [a.tolist() for a in raw.frame][-1] if raw.frame else None


def prefix_for(level):
    sols = {int(k): v for k, v in json.loads(SOLUTIONS_PATH.read_text()).items()}
    out = []
    for i in range(level):
        if i not in sols:
            raise SystemExit(f"missing solution for L{i}")
        out += sols[i]
    return out


def show(pred, act, r0=12, r1=48, c0=7, c1=55):
    """Print predicted vs actual side by side; '!' marks a mispredicted cell."""
    print(f"      {'PREDICTED':<{c1 - c0 + 1}}   {'ACTUAL':<{c1 - c0 + 1}}   DIFF")
    for r in range(r0, r1 + 1):
        p = "".join(CH.get(pred[r][c], '?') for c in range(c0, c1 + 1))
        a = "".join(CH.get(act[r][c], '?') for c in range(c0, c1 + 1))
        d = "".join('!' if pred[r][c] != act[r][c] else ' ' for c in range(c0, c1 + 1))
        if d.strip():
            print(f"R{r:02d}   {p}   {a}   {d}")


def main():
    actions = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] else []
    level = int(sys.argv[sys.argv.index("--level") + 1]) if "--level" in sys.argv else 4
    J = Journal("tu93", level) if "--journal" in sys.argv else None

    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})
    for n in prefix_for(level):
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})

    lv = raw.levels_completed
    init = g(raw)
    tl = Timeline(init)
    prev = init
    steps = 0
    for i, n in enumerate(actions, start=1):
        a = GameAction.from_name(n)
        raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
        steps += 1
        if raw is None or not raw.frame or raw.state.name == "GAME_OVER":
            # No frame comes back on death: record None so the backtest checks
            # the status and does not compare against a stale frame.
            tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                                 after_frame=None, status=Status.GAME_OVER))
            print(f"  (died at step {i})")
            break
        cur = g(raw)
        st = Status.LEVEL_COMPLETED if raw.levels_completed > lv else Status.RUNNING
        tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                             after_frame=cur, status=st))
        prev = cur
        if st == Status.LEVEL_COMPLETED:
            break

    model = tu93_world_model(version=MODEL_VERSION_N)
    rep = run_backtest(model, tl)
    print(f"L{level} backtest over {steps} real steps: {rep.summary()}")
    if not rep.ok and rep.first_mismatch is not None:
        m = rep.first_mismatch
        show(m.predicted_frame, m.actual_frame)
        if J:
            J.refute(version=MODEL_VERSION, bug=m.summary(), step_index=m.step_index,
                     action=m.action, cells_off=m.changed_cells)
    elif J:
        J.author(version=MODEL_VERSION,
                 rules=[r for r in (sys.argv[sys.argv.index("--rules") + 1].split("|")
                                    if "--rules" in sys.argv else
                                    ["carried model reproduces this level exactly"])],
                 code="see agents/wm/tu93_model.py",
                 changed=(sys.argv[sys.argv.index("--changed") + 1]
                          if "--changed" in sys.argv else "none"),
                 because=f"backtest {rep.matched}/{rep.total} exact on L{level}",
                 backtest={"matched": rep.matched, "total": rep.total, "ok": True})
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
