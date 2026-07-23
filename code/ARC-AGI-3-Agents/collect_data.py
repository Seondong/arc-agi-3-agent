"""
ARC-AGI-3 Data Collection Script.

Wraps the game environment to collect structured training data while playing.
One action per call; saves a JSONL record at each step.

Usage:
    # Start a new game
    uv run collect_data.py --game vc33 --action RESET --reasoning "Starting game" --fresh

    # Take actions with reasoning
    uv run collect_data.py --game vc33 --action '{"action":"ACTION6","x":62,"y":33}' --reasoning "Clicking diamond button to move boundary"

    # View current state (no action)
    uv run collect_data.py --game vc33 --view --map
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

from agents.grid_lib import (
    CHAR_MAP,
    diff_cell_count,
    find_objects_dict,
    map2d,
    find_objects,
)

SESSION_DIR = ".sessions"
DATA_DIR = "data"


# ---------------------------------------------------------------------------
# Session management (same pattern as play.py)
# ---------------------------------------------------------------------------

def session_path(game_prefix):
    os.makedirs(SESSION_DIR, exist_ok=True)
    return os.path.join(SESSION_DIR, f"{game_prefix}_collect.json")


def save_session(path, game_id, actions_history, step, levels):
    with open(path, "w") as f:
        json.dump({
            "game_id": game_id,
            "actions": actions_history,
            "step": step,
            "levels": levels,
        }, f)


def load_session(path):
    with open(path, "r") as f:
        return json.load(f)


def parse_action(spec):
    """Parse an action spec string into (GameAction, data_dict)."""
    if isinstance(spec, str):
        try:
            parsed = json.loads(spec)
            if isinstance(parsed, dict):
                name = parsed["action"]
                data = {k: v for k, v in parsed.items() if k != "action"}
                return GameAction.from_name(name), data
        except (json.JSONDecodeError, KeyError):
            pass
        return GameAction.from_name(spec), {}
    raise ValueError(f"Invalid action: {spec}")


def replay_actions(game_id, actions_history):
    """Replay all previous actions to restore game state."""
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    env = arc.make(game_id)
    grid = None
    prev_grid = None
    raw = None
    for spec in actions_history:
        action, data = parse_action(spec)
        if data:
            action.set_data(data)
        action.reasoning = "replay"
        prev_grid = grid
        raw = env.step(action, data=action.action_data.model_dump(), reasoning={})
        if raw and raw.frame:
            grid = [arr.tolist() for arr in raw.frame][-1]
    return env, grid, prev_grid, raw


# ---------------------------------------------------------------------------
# Data recording
# ---------------------------------------------------------------------------

def trajectory_path(game_prefix):
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{game_prefix}_trajectory.jsonl")


def build_objects_list(grid):
    """Build a list of object dicts from the grid."""
    obj_dict = find_objects_dict(grid)
    result = []
    for v, cells in sorted(obj_dict.items()):
        rs = [r for r, c in cells]
        cs = [c for r, c in cells]
        result.append({
            "value": v,
            "count": len(cells),
            "r_min": min(rs),
            "r_max": max(rs),
            "c_min": min(cs),
            "c_max": max(cs),
        })
    return result


def save_record(game_prefix, record):
    """Append one JSON record as a line to the trajectory JSONL file."""
    path = trajectory_path(game_prefix)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ARC-AGI-3 Data Collection")
    parser.add_argument("--game", required=True, help="Game ID prefix (e.g., vc33)")
    parser.add_argument("--action", type=str, default=None, help="Action to take (e.g., RESET, ACTION1, or JSON)")
    parser.add_argument("--reasoning", type=str, default="", help="Reasoning for the action")
    parser.add_argument("--view", action="store_true", help="Just view current state")
    parser.add_argument("--fresh", action="store_true", help="Start fresh session (clears trajectory file too)")
    parser.add_argument("--map", action="store_true", help="Show 2D map")
    parser.add_argument("--map-rows", type=str, default=None, help="Row range e.g. 0-30")
    parser.add_argument("--map-cols", type=str, default=None, help="Col range e.g. 0-30")
    parser.add_argument("--objects", action="store_true", help="Show objects")
    args = parser.parse_args()

    spath = session_path(args.game)

    # Find full game ID
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    game_id = None
    for e in arc.get_environments():
        if e.game_id.startswith(args.game):
            game_id = e.game_id
            break
    if not game_id:
        print(f"ERROR: Game '{args.game}' not found")
        sys.exit(1)

    # Load or create session
    actions_history = []
    prev_grid = None
    step = 0
    levels = 0

    if args.fresh:
        # Remove old trajectory file on fresh start
        tpath = trajectory_path(args.game)
        if os.path.exists(tpath):
            os.remove(tpath)
        # Remove old session
        if os.path.exists(spath):
            os.remove(spath)
    elif os.path.exists(spath):
        session = load_session(spath)
        actions_history = session["actions"]
        step = session["step"]
        levels = session["levels"]

    # Replay previous actions to restore state
    if actions_history:
        env, current_grid, prev_grid, last_raw = replay_actions(game_id, actions_history)
    else:
        env = arc.make(game_id)
        current_grid = None
        last_raw = None
        if not args.action and not args.view:
            args.action = "RESET"

    # View only
    if args.view and not args.action:
        if current_grid:
            print(f"Game: {game_id} | Step {step} | L{levels}")
            if args.objects:
                print(f"\n--- Objects ---\n{find_objects(current_grid)}")
            if args.map:
                rr = tuple(map(int, args.map_rows.split("-"))) if args.map_rows else None
                cr = tuple(map(int, args.map_cols.split("-"))) if args.map_cols else None
                print(f"\n{map2d(current_grid, row_range=rr, col_range=cr)}")
        else:
            print("No state yet. Run --action RESET first.")
        return

    if not args.action:
        print("Specify --action or --view")
        return

    # Parse and execute action
    action, action_data = parse_action(args.action)
    if action_data:
        action.set_data(action_data)
    action.reasoning = f"Step {step}"

    levels_before = levels

    raw = env.step(action, data=action.action_data.model_dump(), reasoning={})
    if raw is None:
        print("ERROR: No frame returned")
        return

    grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
    state = raw.state
    levels_after = raw.levels_completed
    avail_ids = raw.available_actions if raw.available_actions else []
    avail_names = [GameAction.from_id(a).name for a in avail_ids]

    # Compute diff
    diff_cells = diff_cell_count(current_grid, grid) if current_grid else 0

    # Build action_args
    action_args = action_data if action_data else {}

    # Build the record
    record = {
        "game_id": game_id,
        "step": step,
        "level": levels_before,
        "grid": grid,
        "available_actions": avail_ids,
        "prev_grid": current_grid,
        "diff_cells": diff_cells,
        "objects": build_objects_list(grid),
        "reasoning": args.reasoning,
        "action": action.name,
        "action_args": action_args,
        "levels_before": levels_before,
        "levels_after": levels_after,
        "state_after": state.name,
    }

    # Save record to JSONL
    tpath = save_record(args.game, record)

    # Store action in history
    actions_history.append(args.action)

    # Print summary
    print(f"Step {step} | {action.name} | {state.name} | L{levels_before}->L{levels_after} | Actions: {','.join(avail_names)}")
    if current_grid:
        print(f"Diff: {diff_cells} cells changed")
    if state == GameState.WIN:
        print("WIN!")
    elif state == GameState.GAME_OVER:
        print("GAME OVER")

    print(f"Record saved to {tpath}")

    if args.objects:
        print(f"\n--- Objects ---\n{find_objects(grid)}")

    if args.map:
        rr = tuple(map(int, args.map_rows.split("-"))) if args.map_rows else None
        cr = tuple(map(int, args.map_cols.split("-"))) if args.map_cols else None
        print(f"\n{map2d(grid, row_range=rr, col_range=cr)}")

    # Save session
    step += 1
    levels = levels_after
    save_session(spath, game_id, actions_history, step, levels)


if __name__ == "__main__":
    main()
