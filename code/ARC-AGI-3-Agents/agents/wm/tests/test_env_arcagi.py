"""Adapter tests for ArcAgiEnv using a fake engine (no arc_agi needed).

Verifies the frame/status/level-up conversion and RESET filtering in
`_extract`, which is the part most likely to drift from the real API.

Run: python agents/wm/tests/test_env_arcagi.py
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _AGENTS_ROOT not in sys.path:
    sys.path.insert(0, _AGENTS_ROOT)

from wm.core import Status
from wm.env_arcagi import ArcAgiEnv


# -- fakes mimicking arcengine ------------------------------------------------
class _FakeState:
    NOT_FINISHED = "NOT_FINISHED"
    WIN = "WIN"
    GAME_OVER = "GAME_OVER"


class _FakeArr:
    def __init__(self, grid):
        self._grid = grid

    def tolist(self):
        return self._grid


class _FakeGameAction:
    _NAMES = {1: "ACTION1", 2: "ACTION2", 3: "ACTION3", 4: "ACTION4", 0: "RESET"}

    def __init__(self, name):
        self.name = name

    @classmethod
    def from_id(cls, a):
        return cls(cls._NAMES.get(a, f"ACTION{a}"))


class _Raw:
    def __init__(self, grid, state, levels, actions):
        self.frame = [_FakeArr(grid)]
        self.state = state
        self.levels_completed = levels
        self.available_actions = actions


def _env_with_fakes():
    env = ArcAgiEnv("tu93")
    env._GameState = _FakeState
    env._GameAction = _FakeGameAction
    env._prev_levels = 0
    return env


G = [[0, 1], [2, 3]]


def test_status_mapping_and_level_up():
    env = _env_with_fakes()

    r = env._extract(_Raw(G, _FakeState.NOT_FINISHED, 0, [1, 2, 3, 4, 0]))
    assert r.status == Status.RUNNING
    assert r.frame == G
    assert env.available_actions == ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]  # RESET filtered

    r = env._extract(_Raw(G, _FakeState.NOT_FINISHED, 1, [1, 2, 3, 4]))
    assert r.status == Status.LEVEL_COMPLETED  # levels went 0 -> 1

    r = env._extract(_Raw(G, _FakeState.NOT_FINISHED, 1, [1, 2, 3, 4]))
    assert r.status == Status.RUNNING  # still level 1, no new completion

    r = env._extract(_Raw(G, _FakeState.WIN, 1, [1, 2, 3, 4]))
    assert r.status == Status.LEVEL_COMPLETED  # whole game solved

    r = env._extract(_Raw(G, _FakeState.GAME_OVER, 1, [1, 2, 3, 4]))
    assert r.status == Status.GAME_OVER
    print("[env] status mapping + level-up + RESET filter OK")


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
