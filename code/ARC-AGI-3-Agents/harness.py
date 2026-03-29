"""
ARC-AGI-3 Harness Script for Claude Code.

Usage:
    uv run harness.py --game ls20 --actions '["RESET"]'
    uv run harness.py --game ls20 --actions '["RESET","ACTION1","ACTION3"]'
    uv run harness.py --game ls20 --actions '["RESET",{"action":"ACTION6","x":10,"y":20},"ACTION1"]'

Replays all actions from scratch (offline mode, ~2000 FPS) and prints:
- Compressed grid state after EACH action
- Game state, score, available actions
- Diff from previous frame
"""

import argparse
import json
import sys

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState


# ---------------------------------------------------------------------------
# Grid compression (same as claude_agent.py)
# ---------------------------------------------------------------------------

def _rle_row(row: list[int]) -> str:
    if not row:
        return ""
    parts = []
    current = row[0]
    count = 1
    for val in row[1:]:
        if val == current:
            count += 1
        else:
            parts.append(f"{current}x{count}" if count > 1 else str(current))
            current = val
            count = 1
    parts.append(f"{current}x{count}" if count > 1 else str(current))
    return " ".join(parts)


def compress_grid(grid: list[list[int]]) -> str:
    if not grid:
        return "(empty)"
    lines = []
    i = 0
    while i < len(grid):
        j = i + 1
        while j < len(grid) and grid[j] == grid[i]:
            j += 1
        row_rle = _rle_row(grid[i])
        if j - i > 2:
            lines.append(f"R{i}-R{j-1}: {row_rle}")
        elif j - i == 2:
            lines.append(f"R{i}-R{i+1}: {row_rle}")
        else:
            lines.append(f"R{i}: {row_rle}")
        i = j
    return "\n".join(lines)


def compute_diff(old: list[list[int]], new: list[list[int]]) -> str:
    changes = []
    for r in range(min(len(old), len(new))):
        for c in range(min(len(old[r]), len(new[r]))):
            if old[r][c] != new[r][c]:
                changes.append(f"({r},{c}):{old[r][c]}->{new[r][c]}")
    if not changes:
        return "NO CHANGE"
    summary = f"{len(changes)} cells changed"
    if len(changes) <= 60:
        return f"{summary}: {' '.join(changes)}"
    return f"{summary} (first 60): {' '.join(changes[:60])}"


# ---------------------------------------------------------------------------
# 2D Map View — bird's-eye with value-to-char mapping
# ---------------------------------------------------------------------------

# Single-char display per cell value (0-15). Customize per game if needed.
CHAR_MAP = {
    0: '○', 1: '●', 2: '②', 3: '·', 4: '█', 5: '▓', 6: '♦', 7: '⑦',
    8: '♥', 9: '◆', 10: '⑩', 11: '★', 12: '▲', 13: '⑬', 14: '⑭', 15: '⑮',
}

def map2d(grid: list[list[int]], row_range=None, col_range=None, step=1) -> str:
    """Render a 2D char map of the grid (or a slice of it).

    Args:
        grid: 2D int grid
        row_range: (start, end) inclusive, or None for full
        col_range: (start, end) inclusive, or None for full
        step: sample every Nth row/col (for overview of large grids)
    """
    if not grid:
        return "(empty)"
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    r0, r1 = row_range if row_range else (0, rows - 1)
    c0, c1 = col_range if col_range else (0, cols - 1)
    r0, r1 = max(0, r0), min(rows - 1, r1)
    c0, c1 = max(0, c0), min(cols - 1, c1)

    lines = []
    # Column header
    header = "     " + "".join(f"{c:2d}" if c % 5 == 0 else "  " for c in range(c0, c1 + 1, step))
    lines.append(header)

    for r in range(r0, r1 + 1, step):
        row_chars = []
        for c in range(c0, c1 + 1, step):
            row_chars.append(CHAR_MAP.get(grid[r][c], '?'))
        lines.append(f"R{r:02d}  {''.join(row_chars)}")
    return "\n".join(lines)


def column_slice(grid: list[list[int]], col_start: int, col_end: int) -> str:
    """Show what values exist at a column range across all rows (vertical view).

    Groups consecutive rows with identical column patterns.
    """
    if not grid:
        return "(empty)"
    lines = []
    i = 0
    while i < len(grid):
        row_vals = tuple(grid[i][col_start:col_end + 1])
        j = i + 1
        while j < len(grid) and tuple(grid[j][col_start:col_end + 1]) == row_vals:
            j += 1
        val_str = " ".join(str(v) for v in row_vals)
        chars = "".join(CHAR_MAP.get(v, '?') for v in row_vals)
        if j - i > 1:
            lines.append(f"R{i:02d}-R{j-1:02d}: [{val_str}] {chars}")
        else:
            lines.append(f"R{i:02d}:      [{val_str}] {chars}")
        i = j
    return "\n".join(lines)


def find_objects(grid: list[list[int]], bg_values={3, 4, 5}) -> str:
    """Find non-background objects and their bounding boxes."""
    objects = {}  # value -> list of (r,c)
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            v = grid[r][c]
            if v not in bg_values:
                objects.setdefault(v, []).append((r, c))

    lines = []
    for v, cells in sorted(objects.items()):
        rs = [r for r, c in cells]
        cs = [c for r, c in cells]
        char = CHAR_MAP.get(v, '?')
        lines.append(f"  Value {v} ({char}): {len(cells)} cells, "
                      f"R{min(rs)}-R{max(rs)} C{min(cs)}-C{max(cs)}")
    return "\n".join(lines) if lines else "  (none)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_action(action_spec) -> tuple[GameAction, dict]:
    """Parse action from string or dict."""
    if isinstance(action_spec, str):
        return GameAction.from_name(action_spec), {}
    elif isinstance(action_spec, dict):
        name = action_spec["action"]
        data = {k: v for k, v in action_spec.items() if k != "action"}
        return GameAction.from_name(name), data
    raise ValueError(f"Invalid action spec: {action_spec}")


def main():
    parser = argparse.ArgumentParser(description="ARC-AGI-3 Harness for Claude Code")
    parser.add_argument("--game", required=True, help="Game ID (e.g., ls20)")
    parser.add_argument("--actions", required=True, help="JSON array of actions")
    parser.add_argument("--compact", action="store_true", help="Only show last frame")
    parser.add_argument("--map", action="store_true", help="Show 2D char map of final grid")
    parser.add_argument("--map-rows", type=str, default=None, help="Row range for map: '5-50'")
    parser.add_argument("--map-cols", type=str, default=None, help="Col range for map: '10-55'")
    parser.add_argument("--col-slice", type=str, default=None, help="Vertical column slice: '29-38'")
    parser.add_argument("--objects", action="store_true", help="Find non-background objects")
    args = parser.parse_args()

    actions_list = json.loads(args.actions)

    # Initialize game
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    envs = arc.get_environments()
    game_id = None
    for e in envs:
        if e.game_id.startswith(args.game):
            game_id = e.game_id
            break
    if not game_id:
        available = [e.game_id for e in envs]
        print(f"ERROR: Game '{args.game}' not found. Available: {available}")
        sys.exit(1)

    env = arc.make(game_id)
    prev_grid = None

    for i, action_spec in enumerate(actions_list):
        action, data = parse_action(action_spec)
        if data:
            action.set_data(data)
        action.reasoning = f"Step {i}"

        raw = env.step(action, data=action.action_data.model_dump(), reasoning={})
        if raw is None:
            print(f"\n=== Step {i}: {action.name} → ERROR: No frame returned ===")
            continue

        grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
        state = raw.state
        levels = raw.levels_completed
        available = [GameAction.from_id(a).name for a in raw.available_actions] if raw.available_actions else []

        if args.compact and i < len(actions_list) - 1:
            # Only print summary for intermediate steps
            diff_str = compute_diff(prev_grid, grid) if prev_grid else "INITIAL"
            change_marker = "→ CHANGED" if diff_str != "NO CHANGE" else "→ no change"
            print(f"Step {i}: {action.name} | {state.name} | L{levels} | {change_marker}")
        else:
            print(f"\n{'='*60}")
            print(f"Step {i}: {action.name}")
            print(f"State: {state.name} | Levels completed: {levels}")
            if available:
                print(f"Available actions: {', '.join(available)}")

            if prev_grid is not None:
                diff_str = compute_diff(prev_grid, grid)
                print(f"Diff: {diff_str}")

            if not args.compact or i == len(actions_list) - 1:
                print(f"\nGrid ({len(grid)}x{len(grid[0]) if grid else 0}):")
                print(compress_grid(grid))

        prev_grid = [row[:] for row in grid] if grid else None

    # Final summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(actions_list)} actions | State: {state.name} | Levels: {levels}")
    if state == GameState.WIN:
        print("WIN!")
    elif state == GameState.GAME_OVER:
        print("GAME OVER")

    # Extra analysis modes on the final grid
    if grid:
        if args.objects:
            print(f"\n--- Objects (non-bg) ---")
            print(find_objects(grid))

        if args.map:
            row_range = None
            col_range = None
            if args.map_rows:
                r0, r1 = map(int, args.map_rows.split("-"))
                row_range = (r0, r1)
            if args.map_cols:
                c0, c1 = map(int, args.map_cols.split("-"))
                col_range = (c0, c1)
            print(f"\n--- 2D Map ---")
            print(map2d(grid, row_range=row_range, col_range=col_range))

        if args.col_slice:
            c0, c1 = map(int, args.col_slice.split("-"))
            print(f"\n--- Column Slice C{c0}-C{c1} ---")
            print(column_slice(grid, c0, c1))


if __name__ == "__main__":
    main()
