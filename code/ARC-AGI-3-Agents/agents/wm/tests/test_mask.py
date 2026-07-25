"""HUD-mask backtest test.

Real ARC-AGI-3 frames often carry a step/energy counter that changes every step
without game-logic meaning. A model that captures gameplay but not the counter
should still certify when it declares that region via `ignore(frame)`. This
proves: without ignore -> pointed bug on the HUD cell; with ignore -> green.

Run: python agents/wm/tests/test_mask.py
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _AGENTS_ROOT not in sys.path:
    sys.path.insert(0, _AGENTS_ROOT)

from wm.backtest import run_backtest
from wm.core import Action, Status, Timeline, Transition, WorldModel

# Frame layout: row 0 = gameplay [a, b], row 1 = HUD [counter, 0].
# Mechanic: ACTION4 increments b. The real HUD counter counts DOWN every step;
# our model renders the HUD as a constant 0 (i.e. does not model it).


def _reconstruct(frame):
    return (frame[0][0], frame[0][1])  # (a, b); HUD ignored in state


def _step(state, action: Action):
    a, b = state
    if action.name == "ACTION4":
        b += 1
    status = Status.LEVEL_COMPLETED if b >= 3 else Status.RUNNING
    return (a, b), status


def _render(state):
    a, b = state
    return [[a, b], [0, 0]]  # HUD rendered as constant 0 (unmodelled)


def _is_goal(state):
    return state[1] >= 3


def _model(with_ignore: bool) -> WorldModel:
    return WorldModel(
        version=1, reconstruct=_reconstruct, step=_step, render=_render,
        is_goal=_is_goal,
        ignore=(lambda frame: [(1, 0), (1, 1)]) if with_ignore else None,
    )


def _real_timeline() -> Timeline:
    # Gameplay b: 0 -> 1 -> 2; HUD counter: 9 -> 8 -> 7 (changes every step).
    frames = [
        [[5, 0], [9, 0]],
        [[5, 1], [8, 0]],
        [[5, 2], [7, 0]],
    ]
    tl = Timeline(frames[0])
    for i in range(1, len(frames)):
        tl.record(Transition(
            step_index=i, action=Action("ACTION4"),
            before_frame=frames[i - 1], after_frame=frames[i],
            status=Status.RUNNING, changed_cells=2,
        ))
    return tl


def test_hud_without_ignore_fails():
    r = run_backtest(_model(with_ignore=False), _real_timeline())
    assert not r.ok
    assert r.first_mismatch is not None
    assert r.first_mismatch.step_index == 1
    assert r.first_mismatch.frame_mismatch  # the HUD cell (1,0): 0 vs 8
    print("[mask] no-ignore -> pointed bug on HUD:", r.summary())


def test_hud_with_ignore_certifies():
    r = run_backtest(_model(with_ignore=True), _real_timeline())
    assert r.ok, r.summary()
    assert r.matched == 2
    print("[mask] ignore(HUD) -> green:", r.summary())


def _run_all():
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'all passed' if not failed else f'{failed} failed'}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
