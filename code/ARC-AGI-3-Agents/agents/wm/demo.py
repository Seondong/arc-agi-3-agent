"""Runnable demo: solve the synthetic maze and write a trace JSONL.

    python agents/wm/demo.py

Prints the episode result and the path to the emitted trace so you can inspect
the `data-logging-principles` records the loop produces per step.
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _AGENTS_ROOT not in sys.path:
    sys.path.insert(0, _AGENTS_ROOT)

from wm.brain import CallableBrain
from wm.env import GraphMazeEnv
from wm.loop import SolveLoop
from wm.reference_models import maze_world_model


def main() -> None:
    out = os.path.join(_HERE, "trace_demo.jsonl")
    env = GraphMazeEnv()
    brain = CallableBrain(maze_world_model(correct=True))
    result = SolveLoop(max_steps=50).run(env, brain, trace_path=out)

    print(f"status={result.status} solved={result.solved} "
          f"steps={result.steps} mispredictions={result.mispredictions}")
    print(f"final backtest: {result.final_backtest}")
    print(f"trace: {out}\n--- records ---")
    for rec in result.trace_records:
        print(json.dumps({
            "step": rec["step_index"],
            "phase": rec["phase"],
            "action": rec["action"]["name"],
            "predict": rec["reasoning"]["predict"],
            "match": rec["prediction_match"],
            "backtest_ok": rec["backtest_ok"],
            "wm_v": rec["world_model_version"],
        }))


if __name__ == "__main__":
    main()
