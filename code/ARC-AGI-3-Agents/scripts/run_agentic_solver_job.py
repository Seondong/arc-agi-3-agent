"""[Mar 31] Created by SD with GPT-5.4."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MPLCONFIGDIR = REPO_ROOT / "artifacts" / "mplconfig"
DEFAULT_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(DEFAULT_MPLCONFIGDIR))

from agents.agentic.solve_loop import solve_episode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one agentic solve-loop episode and emit a structured result JSON."
    )
    parser.add_argument("--game", required=True, help="Game ID prefix, e.g. sk48")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="Maximum steps for the solve loop.",
    )
    parser.add_argument(
        "--memory-root",
        required=True,
        help="Directory where solve_loop should write episode artifacts.",
    )
    parser.add_argument(
        "--result-json",
        required=True,
        help="Path where this wrapper writes a compact JSON result.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose solve-loop logging.",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="Optional LLM model name to use as solve-loop brain.",
    )
    parser.add_argument(
        "--llm-memory-window",
        type=int,
        default=4,
        help="Rolling compact reasoning memory size for the LLM brain.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = solve_episode(
        game_id_prefix=args.game,
        max_steps=args.max_steps,
        memory_root=args.memory_root,
        verbose=not args.quiet,
        llm_model=args.llm_model,
        llm_memory_window=args.llm_memory_window,
    )
    episode_root = Path(args.memory_root) / result.episode_id
    payload = {
        "runner": "solve_loop",
        "game_id": result.game_id,
        "episode_id": result.episode_id,
        "episode_root": str(episode_root),
        "trace_path": str(episode_root / "episode_trace.jsonl"),
        "episode_json_path": str(episode_root / "episode.json"),
        "levels_completed": result.levels_completed,
        "total_steps": result.total_steps,
        "final_state": result.final_state,
        "phase_transitions": result.phase_transitions,
        "world_model_summary": result.world_model_summary,
        "trajectory_length": len(result.trajectory),
        "llm_used": result.llm_used,
        "llm_model": result.llm_model,
        "llm_memory_window": result.llm_memory_window,
    }
    result_path = Path(args.result_json)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
