"""Written by a headless Claude Code brain during an autosolve run.

Accepted only after replaying every recorded step exactly, and in
force when L0 cleared: replayed 14/14 recorded steps exactly

Not hand-written and not hand-edited. Saved here by
scripts/wm/autosolve.py so it outlives the process that wrote it.
"""
"""
World model for the grid game `vc33`  (64x64 frames, ACTION6 coordinate clicks).

WHAT THE EVIDENCE SHOWS
-----------------------
Row 0 is a HUD strip (all 7s) that fills with 4s from the right edge as steps are
taken.  It advanced by 1 cell on five of the seven recorded steps and by 2 cells
on the other two, so its rate is NOT a function of the action taken (runs 2 and 6
performed the very same clicks as run 8's steps 2 and 6 and advanced by only 1).
It is therefore an unpredictable step/time counter -> the whole of row 0 is
returned by `ignore()`.  Nothing else in any recorded frame is unexplained.

Below row 0 the grid splits into horizontal *bands* of rows that share the same
"fill boundary" = the column of the first EMPTY(0) cell in the row:

    rows  1..27  boundary 32   (adjustable, holds a 9-button at r24-27 c60-63)
    rows 28..31  boundary 64   (static beam: 5s from col 20, a `b` pair at 38-39)
    rows 32..63  boundary 52   (adjustable, holds a 9-button at r32-35 c60-63)

A band is drawn as FILL(3) left of its boundary and EMPTY(0) right of it, plus
two kinds of decoration recovered from the opening frame:
  * cells left of the boundary that are not 3  -> a sprite anchored to the RIGHT
    EDGE of the fill (here: the left-pointing arrow `..44bb/4444bb` at rows
    44-49, offsets -6..-1 from the boundary);
  * cells right of the boundary that are not 0 -> sprites at ABSOLUTE positions
    (here: the two 9-buttons).

Clicking a 9-button (runs 4 and 5) moves 4 columns from the band the button sits
in to the other adjustable band:  click top button -> top 32->28, bottom 52->56;
click bottom button -> top 32->36, bottom 52->48.  The right-edge sprite travels
with its boundary.  This reproduces both 265-cell diffs exactly (108 top cells +
156 bottom cells + 1 HUD cell), including the 28/52 extra cells caused by the
arrow sliding.  Clicks on 3, 4, 7 or b cells (runs 1,2,3,6,7 and steps 1,2,3,6,7
of run 8) change nothing but the HUD -> every non-button click is a no-op.

GOAL
----
No recorded run ever ended, so the win condition is not observed.  The only
structure the frame offers is: the moving right-edge marker is a 2-wide `b`
pair, an arrow points LEFT away from it, and a static 2-wide `b` pair sits on the
beam at columns 38-39 — reachable from the bottom band's 52 in exactly three
4-column steps (52 -> 40 puts the moving `b` on columns 38-39).  `is_goal` fires
only on that exact column match, and only when such a static twin of the moving
marker's colour actually exists in the frame; otherwise it returns False.  No
GAME_OVER is ever predicted (the HUD's rate, hence any move limit, is unknown).
"""

from collections import namedtuple

GRID_FILL = 3      # solid mass
GRID_EMPTY = 0     # background
BUTTON = 9         # only value whose click ever had an effect
STEP = 4           # columns transferred per button press

State = namedtuple("State", "level bounds steps")

_LEVEL_CACHE = {}


# --------------------------------------------------------------------------- #
# frame helpers
# --------------------------------------------------------------------------- #
def _cell(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        return int(v, 16)
    return int(v)


def _normalize(frame):
    """Return (rows_as_tuple_of_tuples_of_int, wrap_depth)."""
    g = frame
    wrapped = 0
    # peel off any outer list-of-grids wrappers
    while (isinstance(g, (list, tuple)) and g
           and isinstance(g[0], (list, tuple)) and g[0]
           and isinstance(g[0][0], (list, tuple))):
        g = g[-1]
        wrapped += 1
    if isinstance(g, (list, tuple)) and g and isinstance(g[0], str):
        rows = tuple(tuple(_cell(ch) for ch in row) for row in g)
    else:
        rows = tuple(tuple(_cell(v) for v in row) for row in g)
    return rows, wrapped


# --------------------------------------------------------------------------- #
# static level description, derived from the opening frame
# --------------------------------------------------------------------------- #
class _Level(object):
    def __init__(self, grid, wrapped):
        self.grid = grid
        self.wrapped = wrapped
        self.h = len(grid)
        self.w = len(grid[0]) if self.h else 0
        self.key = hash(grid)
        self.hud_row = grid[0] if self.h else ()

        # ---- bands: maximal runs of consecutive rows (row 0 excluded) that
        #      share the same fill boundary -------------------------------- #
        per_row = []
        for r in range(1, self.h):
            row = grid[r]
            b = self.w
            for c in range(self.w):
                if row[c] == GRID_EMPTY:
                    b = c
                    break
            per_row.append(b)

        bands = []
        if per_row:
            start, cur = 1, per_row[0]
            for i in range(1, len(per_row)):
                r = i + 1
                if per_row[i] != cur:
                    bands.append((start, r - 1, cur))
                    start, cur = r, per_row[i]
            bands.append((start, self.h - 1, cur))
        self.bands = tuple(bands)
        self.bounds0 = tuple(b[2] for b in bands)

        # ---- decorations ------------------------------------------------- #
        rel, abs_ = [], []
        for (r0, r1, b0) in bands:
            rel_d, abs_d = {}, {}
            for r in range(r0, r1 + 1):
                row = grid[r]
                for c in range(self.w):
                    v = row[c]
                    if c < b0:
                        if v != GRID_FILL:
                            rel_d[(r, c - b0)] = v      # anchored to right edge
                    else:
                        if v != GRID_EMPTY:
                            abs_d[(r, c)] = v           # anchored absolutely
            rel.append(rel_d)
            abs_.append(abs_d)
        self.rel = tuple(rel)
        self.abs = tuple(abs_)

        # ---- buttons ------------------------------------------------------ #
        self.button_band = {}          # (row, col) -> band index
        band_of_row = {}
        for i, (r0, r1, _b) in enumerate(bands):
            for r in range(r0, r1 + 1):
                band_of_row[r] = i
        adjustable = []
        for r in range(1, self.h):
            for c in range(self.w):
                if grid[r][c] == BUTTON:
                    i = band_of_row[r]
                    self.button_band[(r, c)] = i
                    if i not in adjustable:
                        adjustable.append(i)
        self.adjustable = tuple(sorted(adjustable))

        # ---- goal hypothesis: moving marker meets its static twin ---------- #
        self.marker_value = None
        self.marker_band = None
        self.marker_offsets = ()
        self.target_cols = frozenset()
        moving_vals = {}
        for i in self.adjustable:
            for (r, off), v in self.rel[i].items():
                moving_vals.setdefault(v, set()).add(i)
        static_cols = {}
        for i, (r0, r1, b0) in enumerate(bands):
            if i in self.adjustable:
                continue
            for (r, off), v in self.rel[i].items():
                static_cols.setdefault(v, set()).add(off + b0)
            for (r, c), v in self.abs[i].items():
                static_cols.setdefault(v, set()).add(c)
        shared = [v for v in moving_vals
                  if v in static_cols and len(moving_vals[v]) == 1]
        if len(shared) == 1:
            v = shared[0]
            band = next(iter(moving_vals[v]))
            offs = sorted({off for (r, off), vv in self.rel[band].items()
                           if vv == v})
            if offs:
                self.marker_value = v
                self.marker_band = band
                self.marker_offsets = tuple(offs)
                self.target_cols = frozenset(static_cols[v])

    # identity by content so States built from equal frames compare equal
    def __hash__(self):
        return self.key

    def __eq__(self, other):
        return isinstance(other, _Level) and other.grid == self.grid


# --------------------------------------------------------------------------- #
# the model
# --------------------------------------------------------------------------- #
class Model(object):

    # -- construction ------------------------------------------------------ #
    def reconstruct(self, frame):
        grid, wrapped = _normalize(frame)
        key = (hash(grid), wrapped)
        lvl = _LEVEL_CACHE.get(key)
        if lvl is None or lvl.grid != grid:
            lvl = _Level(grid, wrapped)
            _LEVEL_CACHE[key] = lvl
        return State(lvl, lvl.bounds0, 0)

    # -- dynamics ---------------------------------------------------------- #
    def step(self, state, action):
        lvl = state.level
        x = getattr(action, "x", None)
        y = getattr(action, "y", None)
        bounds = state.bounds

        if x is not None and y is not None:
            col, row = int(x), int(y)
            i = lvl.button_band.get((row, col))
            if i is not None and len(lvl.adjustable) == 2:
                j = [k for k in lvl.adjustable if k != i][0]
                new = list(bounds)
                new[i] = bounds[i] - STEP     # the pressed band gives up 4 cols
                new[j] = bounds[j] + STEP     # the other band gains them
                # out-of-range transfers were never observed; treat as no-op
                if 0 <= new[i] <= lvl.w and 0 <= new[j] <= lvl.w:
                    bounds = tuple(new)
        # directional actions never appear in the evidence -> no-op

        nxt = State(lvl, bounds, state.steps + 1)
        return nxt, ("LEVEL_COMPLETED" if self.is_goal(nxt) else "RUNNING")

    # -- rendering --------------------------------------------------------- #
    def render(self, state):
        lvl = state.level
        out = [list(lvl.hud_row)]                 # HUD reproduced as-is (ignored)
        for _ in range(1, lvl.h):
            out.append([GRID_EMPTY] * lvl.w)

        for i, (r0, r1, _b0) in enumerate(lvl.bands):
            b = state.bounds[i]
            b = max(0, min(lvl.w, b))
            for r in range(r0, r1 + 1):
                row = out[r]
                for c in range(lvl.w):
                    row[c] = GRID_FILL if c < b else GRID_EMPTY
            for (r, off), v in lvl.rel[i].items():
                c = b + off
                if 0 <= c < lvl.w:
                    out[r][c] = v
            for (r, c), v in lvl.abs[i].items():
                if 0 <= c < lvl.w:
                    out[r][c] = v                 # buttons draw on top

        for _ in range(lvl.wrapped):
            out = [out]
        return out

    # -- goal / bookkeeping ------------------------------------------------- #
    def is_goal(self, state):
        lvl = state.level
        if lvl.marker_value is None or not lvl.target_cols:
            return False                          # no evidence -> never claim
        b = state.bounds[lvl.marker_band]
        moving = frozenset(b + off for off in lvl.marker_offsets)
        return moving == lvl.target_cols

    def fingerprint(self, state):
        # step count is deliberately excluded: it only drives the HUD row,
        # which is ignored, so two states with equal bounds are equivalent.
        return (state.level.key, state.bounds)

    def ignore(self, frame):
        grid, _ = _normalize(frame)
        w = len(grid[0]) if grid else 0
        # Row 0 is the step/time HUD; it advanced by 1 or 2 cells per action
        # with no visible dependence on the action, so it is not predictable.
        return [(0, c) for c in range(w)]


def build(version: int = 1):
    return Model()


# ---------------------------------------------------------------------------
# Registry adapter, written by scripts/wm/autosolve.py alongside the model.
# The brain writes `build(version)`; the registry calls
# `<game>_world_model(**kwargs)` and passes keywords a brain-written model has
# never heard of (`legacy=[...]`, used by the simplification pass).
# ---------------------------------------------------------------------------
def vc33_world_model(version: int = 1, **_ignored):
    return build(version)
