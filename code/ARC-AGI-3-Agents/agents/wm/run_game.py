"""Play a real ARC-AGI-3 game with the verified world-model loop.

    python agents/wm/run_game.py --game tu93 --max-steps 200

Runs on a host with the offline `arc_agi` engine and Anthropic credentials
(the Mac). Wires ArcAgiEnv -> ClaudeBrain (Opus authors the world model) ->
SolveLoop, and writes a data-logging-principles trace per episode.

Requirements:
  - `pip install arc-agi` (offline Arcade + game files)
  - ANTHROPIC_API_KEY set (or an `ant auth login` profile)
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _AGENTS_ROOT not in sys.path:
    sys.path.insert(0, _AGENTS_ROOT)

from wm.brain import CallableBrain, ClaudeBrain
from wm.env_arcagi import ArcAgiEnv
from wm.loop import SolveLoop


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game", default="tu93", help="game id prefix, e.g. tu93")
    ap.add_argument("--max-steps", type=int, default=200)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--effort", default="high",
                    choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--trace", default=None, help="trace JSONL output path")
    ap.add_argument("--reference-model", default=None,
                    help="optional dotted path to a WorldModel factory "
                         "(e.g. wm.reference_models:maze_world_model) to run a "
                         "hand-written model via CallableBrain instead of Opus")
    args = ap.parse_args()

    env = ArcAgiEnv(args.game)
    trace = args.trace or os.path.join(_HERE, f"trace_{args.game}.jsonl")

    if args.reference_model:
        mod_name, fn_name = args.reference_model.split(":")
        import importlib
        factory = getattr(importlib.import_module(mod_name), fn_name)
        brain = CallableBrain(factory())
    else:
        brain = ClaudeBrain(model_id=args.model, effort=args.effort)

    result = SolveLoop(max_steps=args.max_steps).run(env, brain, trace_path=trace)

    print(f"game={args.game} status={result.status} solved={result.solved} "
          f"levels={result.levels_completed} steps={result.steps} "
          f"mispredictions={result.mispredictions}")
    print(f"final backtest: {result.final_backtest}")
    print(f"trace: {trace}")


if __name__ == "__main__":
    main()
