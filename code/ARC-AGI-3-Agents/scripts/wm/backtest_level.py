"""Certify the model against a real action sequence on one level, with a
predicted/actual diff on failure.

Usage: backtest_level.py --game tu93 --level 6 "ACTION4,ACTION4" [--journal]

Prints the first divergence as a pointed bug — which step, which action, which
cells — because that is what the next model version gets written against.
"""
import _cli
from agents.wm.backtest import run_backtest
from agents.wm.core import Action, Status, Timeline, Transition
from agents.wm.harness import Session, bounds
from agents.wm.journal import Journal
from agents.wm.models import model_for

CH = {0: '·', 2: '▒', 4: '◆', 5: '█', 6: '.', 8: '♥', 9: '@', 11: '♠', 12: '◘',
      13: '?', 14: '⊕', 15: '♢'}


def show(pred, act, r0, r1, c0, c1):
    print(f"      {'PREDICTED':<{c1 - c0 + 1}}   {'ACTUAL':<{c1 - c0 + 1}}   DIFF")
    for r in range(r0, r1 + 1):
        p = "".join(CH.get(pred[r][c], '?') for c in range(c0, c1 + 1))
        a = "".join(CH.get(act[r][c], '?') for c in range(c0, c1 + 1))
        d = "".join('!' if pred[r][c] != act[r][c] else ' ' for c in range(c0, c1 + 1))
        if d.strip():
            print(f"R{r:02d}   {p}   {a}   {d}")


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    _cli.actions_arg(p)
    p.add_argument("--journal", action="store_true")
    p.add_argument("--version", default="v0", help="label to record in the journal")
    a = p.parse_args()

    s = Session.open(a.game, a.level)
    init, lv = s.grid, s.raw.levels_completed
    r0, r1, c0, c1 = bounds(init)
    tl, prev = Timeline(init), init
    for i, n in enumerate(_cli.actions(a.actions), start=1):
        s.act(n)
        if s.dead:
            # No frame comes back on death: record None so the backtest checks the
            # status and does not compare a render against a stale frame.
            tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                                 after_frame=None, status=Status.GAME_OVER))
            print(f"  (died at step {i})")
            break
        cur = s.grid
        st = Status.LEVEL_COMPLETED if s.raw.levels_completed > lv else Status.RUNNING
        tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                             after_frame=cur, status=st))
        prev = cur
        if st == Status.LEVEL_COMPLETED:
            break

    model = model_for(a.game, version=0)
    rep = run_backtest(model, tl)
    print(f"{a.game} L{a.level} over {len(tl)} real steps: {rep.summary()}")
    J = Journal(a.game, a.level) if a.journal else None
    if not rep.ok and rep.first_mismatch is not None:
        m = rep.first_mismatch
        if m.actual_frame is not None:
            show(m.predicted_frame, m.actual_frame, r0, r1, c0, c1)
        if J:
            J.refute(version=a.version, bug=m.summary(), step_index=m.step_index,
                     action=m.action, cells_off=m.changed_cells)
    elif J:
        J.author(version=a.version, rules=["carried model reproduces this sequence"],
                 code=f"see agents/wm/models/{a.game.split('-')[0]}.py", changed="none",
                 because=f"backtest {rep.matched}/{rep.total} exact",
                 backtest={"matched": rep.matched, "total": rep.total, "ok": True})
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
