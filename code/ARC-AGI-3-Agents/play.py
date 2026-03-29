"""
ARC-AGI-3 Interactive Player for Claude Code.

Maintains game state in memory. One action per call, no replay needed.

Usage:
    # Start a game
    uv run play.py --game vc33 --action RESET

    # Take actions (reads state from session file)
    uv run play.py --game vc33 --action ACTION1
    uv run play.py --game vc33 --action '{"action":"ACTION6","x":62,"y":33}'

    # View current state without taking action
    uv run play.py --game vc33 --view

    # View with 2D map
    uv run play.py --game vc33 --view --map

    # Reset session (start fresh)
    uv run play.py --game vc33 --action RESET --fresh
"""

import argparse
import json
import os
import pickle
import sys

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState


SESSION_DIR = ".sessions"

# ---------------------------------------------------------------------------
# Char map + analysis (shared with harness.py)
# ---------------------------------------------------------------------------

CHAR_MAP = {
    0: '○', 1: '●', 2: '②', 3: '·', 4: '█', 5: '▓', 6: '♦', 7: '⑦',
    8: '♥', 9: '◆', 10: '⑩', 11: '★', 12: '▲', 13: '⑬', 14: '⑭', 15: '⑮',
}


def map2d(grid, row_range=None, col_range=None):
    if not grid:
        return "(empty)"
    rows, cols = len(grid), len(grid[0])
    r0, r1 = row_range if row_range else (0, rows - 1)
    c0, c1 = col_range if col_range else (0, cols - 1)
    r0, r1 = max(0, r0), min(rows - 1, r1)
    c0, c1 = max(0, c0), min(cols - 1, c1)
    lines = []
    header = "     " + "".join(f"{c:2d}" if c % 5 == 0 else "  " for c in range(c0, c1 + 1))
    lines.append(header)
    for r in range(r0, r1 + 1):
        chars = "".join(CHAR_MAP.get(grid[r][c], '?') for c in range(c0, c1 + 1))
        lines.append(f"R{r:02d}  {chars}")
    return "\n".join(lines)


def find_objects(grid, bg_values={3, 4, 5}):
    objects = {}
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            v = grid[r][c]
            if v not in bg_values:
                objects.setdefault(v, []).append((r, c))
    lines = []
    for v, cells in sorted(objects.items()):
        rs = [r for r, c in cells]
        cs = [c for r, c in cells]
        lines.append(f"  {v}({CHAR_MAP.get(v,'?')}): {len(cells)} cells R{min(rs)}-{max(rs)} C{min(cs)}-{max(cs)}")
    return "\n".join(lines) if lines else "  (none)"


def compute_diff(old, new):
    changes = []
    for r in range(min(len(old), len(new))):
        for c in range(min(len(old[r]), len(new[r]))):
            if old[r][c] != new[r][c]:
                changes.append(f"({r},{c}):{old[r][c]}->{new[r][c]}")
    if not changes:
        return "NO CHANGE (0 cells)"
    n = len(changes)
    if n <= 40:
        return f"{n} cells: {' '.join(changes)}"
    return f"{n} cells (first 40): {' '.join(changes[:40])}"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def session_path(game_prefix):
    os.makedirs(SESSION_DIR, exist_ok=True)
    return os.path.join(SESSION_DIR, f"{game_prefix}.pkl")


def save_session(path, game_id, actions_history, prev_grid, step, levels):
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


def replay_actions(game_id, actions_history):
    """Replay all previous actions to restore game state. Fast in offline mode."""
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    env = arc.make(game_id)
    grid = None
    for spec in actions_history:
        action, data = parse_action(spec)
        if data:
            action.set_data(data)
        action.reasoning = "replay"
        raw = env.step(action, data=action.action_data.model_dump(), reasoning={})
        if raw and raw.frame:
            grid = [arr.tolist() for arr in raw.frame][-1]
    return env, grid


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_action(spec):
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


def main():
    parser = argparse.ArgumentParser(description="ARC-AGI-3 Interactive Player")
    parser.add_argument("--game", required=True, help="Game ID prefix (e.g., vc33)")
    parser.add_argument("--action", type=str, default=None, help="Action to take")
    parser.add_argument("--view", action="store_true", help="Just view current state")
    parser.add_argument("--fresh", action="store_true", help="Start fresh session")
    parser.add_argument("--map", action="store_true", help="Show 2D map")
    parser.add_argument("--map-rows", type=str, default=None)
    parser.add_argument("--map-cols", type=str, default=None)
    parser.add_argument("--objects", action="store_true", help="Show objects")
    args = parser.parse_args()

    spath = session_path(args.game)

    # Find game ID
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

    if not args.fresh and os.path.exists(spath):
        session = load_session(spath)
        actions_history = session["actions"]
        step = session["step"]
        levels = session["levels"]

    # Replay previous actions to restore state (fast in offline, ~2000 FPS)
    if actions_history:
        env, prev_grid = replay_actions(game_id, actions_history)
    else:
        env = arc.make(game_id)
        if not args.action:
            args.action = "RESET"

    # View only
    if args.view and not args.action:
        if prev_grid:
            print(f"Game: {game_id} | Step {step} | L{levels}")
            if args.objects:
                print(f"\n--- Objects ---\n{find_objects(prev_grid)}")
            if args.map:
                rr = tuple(map(int, args.map_rows.split("-"))) if args.map_rows else None
                cr = tuple(map(int, args.map_cols.split("-"))) if args.map_cols else None
                print(f"\n{map2d(prev_grid, row_range=rr, col_range=cr)}")
        else:
            print("No state yet. Run --action RESET first.")
        return

    if not args.action:
        print("Specify --action or --view")
        return

    # Execute action
    action, data = parse_action(args.action)
    if data:
        action.set_data(data)
    action.reasoning = f"Step {step}"

    raw = env.step(action, data=action.action_data.model_dump(), reasoning={})
    if raw is None:
        print(f"ERROR: No frame returned")
        return

    grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
    state = raw.state
    levels = raw.levels_completed
    avail = [GameAction.from_id(a).name for a in raw.available_actions] if raw.available_actions else []

    # Store action in history
    actions_history.append(args.action)

    # Print result
    print(f"Step {step} | {action.name} | {state.name} | L{levels} | Actions: {','.join(avail)}")
    if prev_grid:
        print(f"Diff: {compute_diff(prev_grid, grid)}")
    if state == GameState.WIN:
        print("WIN!")
    elif state == GameState.GAME_OVER:
        print("GAME OVER")

    if args.objects:
        print(f"\n--- Objects ---\n{find_objects(grid)}")

    if args.map:
        rr = tuple(map(int, args.map_rows.split("-"))) if args.map_rows else None
        cr = tuple(map(int, args.map_cols.split("-"))) if args.map_cols else None
        print(f"\n{map2d(grid, row_range=rr, col_range=cr)}")

    # Save session
    step += 1
    save_session(spath, game_id, actions_history, prev_grid, step, levels)


if __name__ == "__main__":
    main()
