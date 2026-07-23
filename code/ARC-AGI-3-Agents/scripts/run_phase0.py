#!/usr/bin/env python3
"""Phase 0 pipeline: RESET -> Perception -> Bootstrap Reasoner -> Memory Store.

Chains the perception stack (SceneCanonicalize, ObjectTracker, RelationGraph,
AffordanceMapper, GoalSurfaceDetector) with GPT's bootstrap_reasoner to
produce motif beliefs + probe suggestions, then persists everything via
EpisodeMemoryStore.

Usage:
    uv run python scripts/run_phase0.py --game sk48
    uv run python scripts/run_phase0.py --game ls20 --output-dir dynamics
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap environment
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

# ---------------------------------------------------------------------------
# Internal imports
# ---------------------------------------------------------------------------
from agents.grid_lib import CHAR_MAP, compress_grid, compute_diff, map2d
from agents.agentic.perception import (
    GoalSurface,
    ObjectTransition,
    PerceivedObject,
    SpatialRelation,
    TransitionKind,
    run_perception,
)
from agents.agentic.schemas import ObservationSnapshot, ObjectSummary
from agents.agentic.bootstrap_reasoner import (
    build_bootstrap_ledger,
    suggest_next_probe,
)
from agents.agentic.memory import EpisodeMemoryStore, TrajectoryCurator


# ===================================================================
# Helpers
# ===================================================================

def resolve_game_id(prefix: str) -> str:
    """Find the full game ID matching a short prefix."""
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    for env in arc.get_environments():
        if env.game_id.startswith(prefix):
            return env.game_id
    raise SystemExit(f"ERROR: Game '{prefix}' not found")


def reset_game(game_id: str):
    """RESET the game and return (env, grid, frame)."""
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    env = arc.make(game_id)
    action = GameAction.from_name("RESET")
    action.reasoning = "Phase 0 reset"
    frame = env.step(action, data=action.action_data.model_dump(), reasoning={})
    if frame is None or not frame.frame:
        raise RuntimeError("RESET returned no frame")
    grid = [arr.tolist() for arr in frame.frame][-1]
    return env, grid, frame


def build_value_histogram(grid: list[list[int]]) -> dict[str, int]:
    """Build {str(value): count} histogram for ObservationSnapshot."""
    counts: dict[str, int] = {}
    for row in grid:
        for v in row:
            key = str(v)
            counts[key] = counts.get(key, 0) + 1
    return counts


def build_observation(
    game_id: str,
    grid: list[list[int]],
    frame,
    object_summaries: list[ObjectSummary],
    step_index: int = 0,
) -> ObservationSnapshot:
    """Construct an ObservationSnapshot from frame data + perception output."""
    avail = []
    if frame.available_actions:
        avail = [GameAction.from_id(a).name for a in frame.available_actions]

    rows = len(grid)
    cols = len(grid[0]) if rows else 0

    return ObservationSnapshot(
        game_id=game_id,
        step_index=step_index,
        state=frame.state.name,
        levels_completed=frame.levels_completed,
        grid_rows=rows,
        grid_cols=cols,
        available_actions=avail,
        diff_summary="INITIAL",
        action_history=[],
        value_histogram=build_value_histogram(grid),
        objects=object_summaries,
        compressed_grid=compress_grid(grid),
        map2d=map2d(grid),
        notes=["Phase 0 bootstrap observation."],
    )


# ===================================================================
# Serialisation helpers for perception-specific types
# ===================================================================

def perception_to_dict(perc: dict) -> dict:
    """Convert perception output to a JSON-serialisable dict."""

    def _obj_to_dict(o: PerceivedObject) -> dict:
        return {
            "obj_id": o.obj_id,
            "value": o.value,
            "char": o.char,
            "cell_count": o.cell_count,
            "center": list(o.center),
            "bbox": [o.row_min, o.row_max, o.col_min, o.col_max],
        }

    def _transition_to_dict(t: ObjectTransition) -> dict:
        return {
            "kind": t.kind.name,
            "obj_id": t.obj_id,
            "value": t.value,
            "prev_center": list(t.prev_center) if t.prev_center else None,
            "curr_center": list(t.curr_center) if t.curr_center else None,
            "detail": t.detail,
        }

    def _relation_to_dict(r: tuple) -> dict:
        return {
            "subject": r[0],
            "relation": r[1].name,
            "object": r[2],
        }

    def _goal_to_dict(g: GoalSurface) -> dict:
        return {
            "kind": g.kind,
            "bbox": [g.row_min, g.row_max, g.col_min, g.col_max],
            "detail": g.detail,
        }

    return {
        "background_values": sorted(perc["background"]),
        "objects": [_obj_to_dict(o) for o in perc["objects"]],
        "transitions": [_transition_to_dict(t) for t in perc["transitions"]],
        "relations": [_relation_to_dict(r) for r in perc["relations"]],
        "affordances": perc["affordances"],
        "goal_surfaces": [_goal_to_dict(g) for g in perc["goal_surfaces"]],
        "object_count": len(perc["objects"]),
    }


# ===================================================================
# Main pipeline
# ===================================================================

def run_phase0(game_prefix: str, output_dir: str = "dynamics") -> Path:
    """Execute Phase 0 on one game and save structured output."""

    # 1. Resolve game & RESET
    game_id = resolve_game_id(game_prefix)
    print(f"[Phase 0] Game: {game_id}")

    env, grid, frame = reset_game(game_id)
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    print(f"[Phase 0] Grid: {rows}x{cols} | State: {frame.state.name} "
          f"| L{frame.levels_completed}")

    # 2. Run perception stack
    print("[Phase 0] Running perception stack ...")
    perc = run_perception(grid=grid, prev_grid=None, prev_objects=None)
    n_objects = len(perc["objects"])
    n_relations = len(perc["relations"])
    n_surfaces = len(perc["goal_surfaces"])
    print(f"  Objects: {n_objects} | Relations: {n_relations} "
          f"| Goal surfaces: {n_surfaces}")
    for obj in perc["objects"][:8]:
        print(f"    {obj.obj_id}: val={obj.value}({obj.char}) "
              f"cells={obj.cell_count} "
              f"bbox=({obj.row_min},{obj.col_min})-({obj.row_max},{obj.col_max})")
    if n_objects > 8:
        print(f"    ... and {n_objects - 8} more")

    # 3. Build ObservationSnapshot
    observation = build_observation(
        game_id=game_id,
        grid=grid,
        frame=frame,
        object_summaries=perc["object_summaries"],
        step_index=0,
    )

    # 4. Feed into bootstrap_reasoner
    print("[Phase 0] Running bootstrap reasoner ...")
    ledger = build_bootstrap_ledger(
        episode_id=f"{game_prefix}-phase0",
        observation=observation,
    )
    print(f"  Top motifs ({len(ledger.top_motifs)}):")
    for m in ledger.top_motifs:
        print(f"    {m.name}: conf={m.confidence:.3f}  evidence={m.evidence}")

    print(f"  Hypotheses ({len(ledger.hypotheses)}):")
    for h in ledger.hypotheses:
        print(f"    [{h.hypothesis_id}] {h.summary} (conf={h.confidence:.3f})")

    print(f"  Goal beliefs ({len(ledger.goal_beliefs)}):")
    for g in ledger.goal_beliefs:
        print(f"    {g.summary} (conf={g.confidence:.2f})")

    # 5. Get probe suggestion
    probe = suggest_next_probe(observation, ledger)
    print(f"  Next probe: {probe.action} "
          f"(gain={probe.expected_information_gain:.2f})")
    print(f"    Rationale: {probe.rationale}")

    # 6. Save to dynamics/{game}/ via EpisodeMemoryStore
    game_dir = Path(output_dir) / game_prefix
    game_dir.mkdir(parents=True, exist_ok=True)

    store = EpisodeMemoryStore.create(
        root_dir=str(game_dir),
        game_id=game_id,
        tags=["phase0", "bootstrap"],
        notes=["Created by run_phase0.py"],
    )
    obs_path = store.write_observation(observation)
    belief_path = store.write_belief(ledger)

    # Build trajectory record
    curator = TrajectoryCurator()
    traj = curator.curate(observation=observation, belief=ledger)
    store.append_trace(traj)

    # Also save perception + probe as separate JSON for easy inspection
    phase0_summary = {
        "game_id": game_id,
        "game_prefix": game_prefix,
        "grid_shape": [rows, cols],
        "perception": perception_to_dict(perc),
        "motifs": [m.model_dump() for m in ledger.top_motifs],
        "hypotheses": [h.model_dump() for h in ledger.hypotheses],
        "goal_beliefs": [g.model_dump() for g in ledger.goal_beliefs],
        "action_semantics": ledger.action_semantics,
        "probe_suggestion": {
            "action": probe.action,
            "rationale": probe.rationale,
            "expected_information_gain": probe.expected_information_gain,
            "expected_outcome": probe.expected_outcome,
        },
    }

    summary_path = game_dir / "phase0_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(phase0_summary, f, ensure_ascii=False, indent=2)

    print(f"\n[Phase 0] Output saved:")
    print(f"  Episode dir:   {store.root}")
    print(f"  Observation:   {obs_path}")
    print(f"  Belief ledger: {belief_path}")
    print(f"  Summary:       {summary_path}")
    print(f"[Phase 0] Done.")

    return summary_path


# ===================================================================
# CLI
# ===================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Phase 0: Perception + Bootstrap Reasoner pipeline"
    )
    parser.add_argument(
        "--game", required=True,
        help="Game ID prefix (e.g. sk48, ls20)"
    )
    parser.add_argument(
        "--output-dir", default="dynamics",
        help="Root output directory (default: dynamics)"
    )
    args = parser.parse_args()
    run_phase0(args.game, args.output_dir)
