"""Common grid analysis library for ARC-AGI-3 agents.

Consolidates grid utilities from harness.py, play.py, and claude_agent.py.
"""

from typing import Any, Optional

from arcengine import FrameData


# ---------------------------------------------------------------------------
# Character map for 2D visualization
# ---------------------------------------------------------------------------

CHAR_MAP = {
    0: '○', 1: '●', 2: '②', 3: '·', 4: '█', 5: '▓', 6: '♦', 7: '⑦',
    8: '♥', 9: '◆', 10: '⑩', 11: '★', 12: '▲', 13: '⑬', 14: '⑭', 15: '⑮',
}


# ---------------------------------------------------------------------------
# Grid compression (RLE)
# ---------------------------------------------------------------------------

def _rle_row(row: list[int]) -> str:
    if not row:
        return ""
    parts: list[str] = []
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
    lines: list[str] = []
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


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------

def compute_diff(old: list[list[int]], new: list[list[int]], max_show: int = 40) -> str:
    changes: list[str] = []
    for r in range(min(len(old), len(new))):
        for c in range(min(len(old[r]), len(new[r]))):
            if old[r][c] != new[r][c]:
                changes.append(f"({r},{c}):{old[r][c]}->{new[r][c]}")
    if not changes:
        return "NO CHANGE (0 cells)"
    n = len(changes)
    if n <= max_show:
        return f"{n} cells: {' '.join(changes)}"
    return f"{n} cells (first {max_show}): {' '.join(changes[:max_show])}"


def diff_cell_count(old: list[list[int]], new: list[list[int]]) -> int:
    count = 0
    for r in range(min(len(old), len(new))):
        for c in range(min(len(old[r]), len(new[r]))):
            if old[r][c] != new[r][c]:
                count += 1
    return count


# ---------------------------------------------------------------------------
# 2D map rendering
# ---------------------------------------------------------------------------

def map2d(grid: list[list[int]], row_range: Optional[tuple[int, int]] = None,
          col_range: Optional[tuple[int, int]] = None) -> str:
    if not grid:
        return "(empty)"
    rows, cols = len(grid), len(grid[0])
    r0, r1 = row_range if row_range else (0, rows - 1)
    c0, c1 = col_range if col_range else (0, cols - 1)
    r0, r1 = max(0, r0), min(rows - 1, r1)
    c0, c1 = max(0, c0), min(cols - 1, c1)

    lines: list[str] = []
    header = "     " + "".join(
        f"{c:2d}" if c % 5 == 0 else "  " for c in range(c0, c1 + 1)
    )
    lines.append(header)
    for r in range(r0, r1 + 1):
        chars = "".join(CHAR_MAP.get(grid[r][c], '?') for c in range(c0, c1 + 1))
        lines.append(f"R{r:02d}  {chars}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Object detection
# ---------------------------------------------------------------------------

def find_objects(grid: list[list[int]], bg_values: set[int] = {3, 4, 5}) -> str:
    objects: dict[int, list[tuple[int, int]]] = {}
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            v = grid[r][c]
            if v not in bg_values:
                objects.setdefault(v, []).append((r, c))
    lines: list[str] = []
    for v, cells in sorted(objects.items()):
        rs = [r for r, c in cells]
        cs = [c for r, c in cells]
        char = CHAR_MAP.get(v, '?')
        lines.append(
            f"  {v}({char}): {len(cells)} cells R{min(rs)}-{max(rs)} C{min(cs)}-{max(cs)}"
        )
    return "\n".join(lines) if lines else "  (none)"


def find_objects_dict(grid: list[list[int]], bg_values: set[int] = {3, 4, 5}) -> dict[int, list[tuple[int, int]]]:
    objects: dict[int, list[tuple[int, int]]] = {}
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            v = grid[r][c]
            if v not in bg_values:
                objects.setdefault(v, []).append((r, c))
    return objects


# ---------------------------------------------------------------------------
# Column slice (vertical view)
# ---------------------------------------------------------------------------

def column_slice(grid: list[list[int]], col_start: int, col_end: int) -> str:
    if not grid:
        return "(empty)"
    lines: list[str] = []
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


# ---------------------------------------------------------------------------
# Energy detection
# ---------------------------------------------------------------------------

def detect_energy(grid: list[list[int]]) -> Optional[tuple[int, int]]:
    """Scan bottom rows for an energy/progress bar.

    Returns (remaining, total) or None if not detected.
    Looks for rows where a single value fills from the left (energy remaining)
    and another value fills the rest (energy consumed).
    """
    if not grid or len(grid) < 2:
        return None
    for row_idx in range(len(grid) - 1, max(len(grid) - 5, -1), -1):
        row = grid[row_idx]
        if not row:
            continue
        first_val = row[0]
        count = 0
        for v in row:
            if v == first_val:
                count += 1
            else:
                break
        if count < len(row) and count > 2:
            return (len(row) - count, len(row))
    return None


# ---------------------------------------------------------------------------
# State summarization for LLM input
# ---------------------------------------------------------------------------

def summarize_state(
    grid: list[list[int]],
    prev_grid: Optional[list[list[int]]],
    frame: FrameData,
    action_counter: int,
) -> str:
    from arcengine import GameAction
    parts: list[str] = []

    parts.append(f"State: {frame.state.name} | Level: {frame.levels_completed} | Step: {action_counter}")

    avail = []
    if frame.available_actions:
        avail = [GameAction.from_id(a).name for a in frame.available_actions]
        parts.append(f"Available: {', '.join(avail)}")

    energy = detect_energy(grid)
    if energy:
        parts.append(f"Energy: {energy[0]}/{energy[1]}")

    if prev_grid is not None:
        n_changed = diff_cell_count(prev_grid, grid)
        if n_changed == 0:
            parts.append("Diff: NO CHANGE")
        elif n_changed < 10:
            parts.append(f"Diff: {compute_diff(prev_grid, grid, max_show=10)}")
        elif n_changed > 500:
            parts.append(f"Diff: {n_changed} cells (level transition?)")
        else:
            parts.append(f"Diff: {n_changed} cells changed")

    parts.append(f"\nObjects:\n{find_objects(grid)}")

    # Compact map: sample every 4th row/col for small models, full for API
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    if rows > 32:
        # Sampled overview
        lines = []
        for r in range(0, rows, 4):
            chars = "".join(CHAR_MAP.get(grid[r][c], '?') for c in range(0, cols, 2))
            lines.append(f"R{r:02d} {chars}")
        parts.append(f"\n2D Map (sampled):\n" + "\n".join(lines))
    else:
        parts.append(f"\n2D Map:\n{map2d(grid)}")

    return "\n".join(parts)


def summarize_state_full(
    grid: list[list[int]],
    prev_grid: Optional[list[list[int]]],
    frame: FrameData,
    action_counter: int,
) -> str:
    """Full state summary with complete 2D map. For API-based providers."""
    from arcengine import GameAction
    parts: list[str] = []
    parts.append(f"State: {frame.state.name} | Level: {frame.levels_completed} | Step: {action_counter}")
    if frame.available_actions:
        avail = [GameAction.from_id(a).name for a in frame.available_actions]
        parts.append(f"Available: {', '.join(avail)}")
    energy = detect_energy(grid)
    if energy:
        parts.append(f"Energy: {energy[0]}/{energy[1]}")
    if prev_grid is not None:
        n_changed = diff_cell_count(prev_grid, grid)
        if n_changed == 0:
            parts.append("Diff: NO CHANGE")
        elif n_changed < 10:
            parts.append(f"Diff: {compute_diff(prev_grid, grid, max_show=10)}")
        elif n_changed > 500:
            parts.append(f"Diff: {n_changed} cells (level transition?)")
        else:
            parts.append(f"Diff: {n_changed} cells changed")
    parts.append(f"\nObjects:\n{find_objects(grid)}")
    parts.append(f"\n2D Map:\n{map2d(grid)}")
    return "\n".join(parts)
