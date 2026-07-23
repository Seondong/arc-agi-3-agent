"""End-to-end tests for the verified world-model solve core.

Run: python -m pytest agents/wm/tests/test_wm.py
 or: python agents/wm/tests/test_wm.py   (no pytest needed)

These exercise the three invariants:
  1. a certified model is planned inside for free and solves with 0 real waste;
  2. run_backtest returns a pointed bug on a wrong model;
  3. reality outranks the model — a plan on a wrong model is halted.
"""

from __future__ import annotations

import os
import sys

# Allow running as a plain script from the repo without installation.
_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _AGENTS_ROOT not in sys.path:
    sys.path.insert(0, _AGENTS_ROOT)

from wm.backtest import run_backtest
from wm.brain import CallableBrain
from wm.core import Action, Status, Timeline, Transition
from wm.env import GraphMazeEnv
from wm.loop import SolveLoop
from wm.planner import run_bfs
from wm.reference_models import maze_world_model


def _play(env, names):
    """Drive an env with a list of action names, returning its Timeline."""
    frame = env.reset()
    tl = Timeline(frame)
    for i, name in enumerate(names, start=1):
        res = env.step(Action(name))
        tl.record(Transition(
            step_index=i, action=Action(name),
            before_frame=tl.current_frame, after_frame=res.frame,
            status=res.status, changed_cells=res.changed_cells,
        ))
        if res.status in Status.TERMINAL:
            break
    return tl


def test_correct_model_solves_maze_for_free():
    env = GraphMazeEnv()  # 3x3, start 0, goal 8, deadly enemy at centre 4
    brain = CallableBrain(maze_world_model(correct=True))
    result = SolveLoop(max_steps=50).run(env, brain)

    assert result.solved, result.status
    assert result.status == Status.LEVEL_COMPLETED
    assert result.mispredictions == 0          # a correct model never surprises
    assert result.steps == 4                   # shortest safe path, no waste
    assert result.trace_records                 # traces were emitted
    print("[1] correct model solved in", result.steps,
          "actions, 0 mispredictions, backtest:", result.final_backtest)


def test_backtest_returns_pointed_bug_on_wrong_model():
    env = GraphMazeEnv()
    # Walk deliberately into the deadly centre: right (0->1), down (1->4)=DEATH.
    timeline = _play(env, ["ACTION4", "ACTION2"])
    assert timeline.transitions[-1].status == Status.GAME_OVER

    good = run_backtest(maze_world_model(correct=True), timeline)
    wrong = run_backtest(maze_world_model(correct=False), timeline)

    assert good.ok, good.summary()
    assert not wrong.ok
    assert wrong.first_mismatch is not None
    assert wrong.first_mismatch.step_index == 2          # the fatal step
    assert wrong.first_mismatch.status_mismatch          # predicted RUNNING
    print("[2] wrong model caught:", wrong.summary())


def test_reality_outranks_model_halts_plan():
    # Corridor 1x3: start 0, deadly enemy 1, goal 2. The only route runs through
    # the enemy, which the WRONG model thinks is passable.
    env = GraphMazeEnv(rows=1, cols=3, start=0, goal=2, enemy=1)
    brain = CallableBrain(maze_world_model(correct=False))
    result = SolveLoop(max_steps=20).run(env, brain)

    assert not result.solved
    assert result.mispredictions >= 1        # the plan hit reality and was voided
    # The recorded history now refutes the wrong model.
    print("[3] wrong-model plan halted; mispredictions:", result.mispredictions,
          "final status:", result.status)


def test_bfs_prunes_death_and_finds_safe_path():
    env = GraphMazeEnv()
    model = maze_world_model(correct=True)
    start = model.reconstruct(env.reset())
    plan = run_bfs(model, start, [Action(a) for a in env.available_actions])
    assert plan.found
    # verify the plan never routes through the deadly centre in-model
    s = start
    for a in plan.actions:
        s, status = model.step(s, a)
        assert status != Status.GAME_OVER
    print("[4] BFS plan:", [str(a) for a in plan.actions], "|", plan.summary())


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
