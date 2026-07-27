"""Recovered from the journal by scripts/wm/extract_model.py.

Written by a headless Claude Code brain during an autosolve run and
verified there by replay; this file is a copy of that source, taken from
note seq=118. It is not hand-written and has not been hand-edited.
"""
"""
World model for the grid game `ft09`.

Layout discovered from the evidence
-----------------------------------
The 64x64 board holds four identical *panels*.  A panel is a 3x3 arrangement of
6x6 tiles on an 8-pixel pitch (tile 6 wide, 2-pixel gap):

        tile(i, j)  ->  rows r0+8i .. r0+8i+5 , cols c0+8j .. c0+8j+5

The eight outer tiles are solid, each either 9 ("light") or 8 ("dark").
The centre tile (1,1) is not a tile at all but a 3x3 *thumbnail* built from 2x2
pixels, using 2 for "light", 0 for "dark" and 8 for its own centre pixel.

In the opening frame:

  panel @ (2,4)    tiles [[9,8,9],[8,.,9],[9,8,8]]   thumb [[2,0,2],[0,8,2],[2,0,0]]
  panel @ (2,38)   tiles [[9,8,9],[8,.,8],[9,8,9]]   thumb [[2,0,2],[0,8,0],[2,0,2]]
  panel @ (36,4)   tiles [[8,9,9],[8,.,8],[9,9,8]]   thumb [[0,2,2],[0,8,0],[2,2,0]]
  panel @ (36,36)  tiles [[9,9,9],[9,.,9],[9,9,9]]   thumb [[0,2,2],[0,8,0],[2,2,0]]

Three panels already agree with their own thumbnail under 2<->9 / 0<->8.  The
fourth (36,36) does not: it is blank (all 9) and its thumbnail instead shows the
pattern to be produced.  That panel is also the only one drawn inside a frame of
colour 4 (its inter-tile gaps are 4, not the background 5), which is how this
model identifies the interactive panel without hard-coding coordinates.

Action evidence
---------------
ACTION6(x=col, y=row):
  * inside an outer tile of the framed panel  -> that entire 6x6 tile flips
    9 -> 8 (runs 15..22, one tile each, exactly 36 pixels), and the two
    right-most cells of the bottom row go 12 -> 11.
  * anywhere else (the three unframed panels, the frame itself, the bottom bar)
    -> nothing changes at all (runs 1..14, 23).

Only the 9 -> 8 direction was ever observed, because every recorded run started
from the all-9 panel and took a single step.  This model treats the tile as a
plain toggle 9 <-> 8; the shortest solution is identical under either reading,
and a toggle is the only reading that stays usable on a level whose framed panel
does not start out blank.

Win condition
-------------
Forced by the thumbnails: three panels *are* their thumbnail, the working panel
is not.  Goal = the framed panel's eight outer tiles match its thumbnail.

Debt (see `ignore`)
-------------------
The bottom row (all 12 in the opening frame) is a step counter: two cells at the
right turn 12 -> 11 per effective move.  One step of it is all the evidence
shows, so how the bar continues is not forced.  `render` draws the obvious
extrapolation (two more cells consumed per effective move) but the whole row is
excluded from checking.
"""

from collections import namedtuple

from agents.wm.core import Action, Frame, Status, WorldModel


# ---------------------------------------------------------------- constants --

BACKGROUND = 5
FRAME_COLOUR = 4
TILE_DARK = 8
TILE_LIGHT = 9

THUMB_OFF = 0        # thumbnail pixel meaning "dark tile" (8)
THUMB_ON = 2         # thumbnail pixel meaning "light tile" (9)
THUMB_CENTRE = 8     # thumbnail's own centre pixel

TILE = 6             # tile side, in cells
PITCH = 8            # tile-to-tile spacing
SUB = 2              # thumbnail pixel side

_THUMB_TO_TILE = {THUMB_OFF: TILE_DARK, THUMB_ON: TILE_LIGHT}


State = namedtuple(
    "State",
    "base path rows cols origin tiles target counter moves",
)
# base    : frozen copy of the whole incoming frame (nested tuples)
# path    : index path from `base` down to the 2-D grid
# origin  : (r0, c0) of the interactive panel, or None if none was found
# tiles   : 3x3 tuple of tile colours; entry (1,1) is None (the thumbnail)
# target  : 3x3 tuple of wanted tile colours; entry (1,1) is None
# counter : (row_index, full_value) of the bottom step bar, or None
# moves   : number of effective (state-changing) actions taken


# ------------------------------------------------------------ frame helpers --

def _freeze(x):
    if isinstance(x, (list, tuple)):
        return tuple(_freeze(i) for i in x)
    return x


def _thaw(x):
    if isinstance(x, tuple):
        return [_thaw(i) for i in x]
    return x


def _raw(frame):
    """Best-effort extraction of the nested int structure out of a Frame."""
    if isinstance(frame, (list, tuple)):
        return frame
    for attr in ("grid", "cells", "data", "values", "frame", "pixels"):
        value = getattr(frame, attr, None)
        if isinstance(value, (list, tuple)):
            return value
    raise TypeError("cannot read grid data out of frame %r" % (type(frame),))


def _depth(x):
    d = 0
    while isinstance(x, (list, tuple)) and x:
        d += 1
        x = x[0]
    return d


def _locate_grid(raw):
    """Return (path, grid) where grid is the 2-D list of ints."""
    if _depth(raw) >= 3:
        idx = len(raw) - 1
        return (idx,), raw[idx]
    return (), raw


def _dig(container, path):
    for p in path:
        container = container[p]
    return container


# ----------------------------------------------------------- shape scanning --

def _uniform(grid, r, c, h, w):
    """Colour of the h x w block at (r, c), or None if it is not uniform."""
    if r < 0 or c < 0 or r + h > len(grid) or c + w > len(grid[r]):
        return None
    v = grid[r][c]
    for i in range(r, r + h):
        row = grid[i]
        for j in range(c, c + w):
            if row[j] != v:
                return None
    return v


def _read_thumb(grid, r, c):
    """A 6x6 thumbnail at (r, c): nine uniform 2x2 pixels, centre = 8, rest 0/2."""
    out = []
    for a in range(3):
        row = []
        for b in range(3):
            v = _uniform(grid, r + SUB * a, c + SUB * b, SUB, SUB)
            if v is None:
                return None
            row.append(v)
        out.append(row)
    if out[1][1] != THUMB_CENTRE:
        return None
    for a in range(3):
        for b in range(3):
            if (a, b) == (1, 1):
                continue
            if out[a][b] not in _THUMB_TO_TILE:
                return None
    return tuple(tuple(x) for x in out)


def _read_tiles(grid, r0, c0):
    """The eight solid outer tiles of the panel whose top-left tile is (r0, c0)."""
    rows, cols = len(grid), len(grid[0])
    if r0 < 0 or c0 < 0:
        return None
    if r0 + 2 * PITCH + TILE > rows or c0 + 2 * PITCH + TILE > cols:
        return None
    out = []
    for i in range(3):
        row = []
        for j in range(3):
            if (i, j) == (1, 1):
                row.append(None)
                continue
            v = _uniform(grid, r0 + PITCH * i, c0 + PITCH * j, TILE, TILE)
            if v not in (TILE_DARK, TILE_LIGHT):
                return None
            row.append(v)
        out.append(row)
    return tuple(tuple(x) for x in out)


def _find_panels(grid):
    """All (r0, c0, tiles, thumb) panels on the board."""
    rows, cols = len(grid), len(grid[0])
    seen = set()
    panels = []
    for r in range(PITCH, rows - TILE + 1):
        for c in range(PITCH, cols - TILE + 1):
            thumb = _read_thumb(grid, r, c)
            if thumb is None:
                continue
            r0, c0 = r - PITCH, c - PITCH
            if (r0, c0) in seen:
                continue
            tiles = _read_tiles(grid, r0, c0)
            if tiles is None:
                continue
            seen.add((r0, c0))
            panels.append((r0, c0, tiles, thumb))
    return panels


def _target_from_thumb(thumb):
    return tuple(
        tuple(None if (i, j) == (1, 1) else _THUMB_TO_TILE[thumb[i][j]]
              for j in range(3))
        for i in range(3)
    )


def _pick_active(grid, panels):
    """
    The interactive panel is the one drawn inside the colour-4 frame: its
    inter-tile gap is 4 instead of the background 5.  Falling back on the
    equivalent signature -- the only panel that disagrees with its own
    thumbnail -- keeps this working if a level draws the frame differently.
    """
    framed = []
    for p in panels:
        r0, c0 = p[0], p[1]
        gap = _uniform(grid, r0, c0 + TILE, TILE, PITCH - TILE)
        if gap == FRAME_COLOUR:
            framed.append(p)

    def mismatched(cands):
        return [p for p in cands if p[2] != _target_from_thumb(p[3])]

    if len(framed) == 1:
        return framed[0]
    if framed:
        odd = mismatched(framed)
        return odd[0] if odd else framed[0]
    odd = mismatched(panels)
    return odd[0] if len(odd) == 1 else None


def _find_counter(grid):
    """Bottom step bar: a uniform last row."""
    rows, cols = len(grid), len(grid[0])
    last = rows - 1
    v = _uniform(grid, last, 0, 1, cols)
    if v is None:
        return None
    return (last, v)


# ------------------------------------------------------------------- model --

class Ft09World(WorldModel):

    def __init__(self, version: int = 1):
        try:
            super().__init__()
        except Exception:
            pass
        self.version = version

    # -- construction --------------------------------------------------------

    def reconstruct(self, frame):
        raw = _raw(frame)
        path, grid = _locate_grid(raw)
        rows, cols = len(grid), len(grid[0])

        panels = _find_panels(grid)
        active = _pick_active(grid, panels)

        if active is None:
            origin = None
            tiles = None
            target = None
        else:
            r0, c0, tiles, thumb = active
            origin = (r0, c0)
            target = _target_from_thumb(thumb)

        return State(
            base=_freeze(raw),
            path=tuple(path),
            rows=rows,
            cols=cols,
            origin=origin,
            tiles=tiles,
            target=target,
            counter=_find_counter(grid),
            moves=0,
        )

    # -- dynamics ------------------------------------------------------------

    @staticmethod
    def _tile_at(origin, r, c):
        """Which outer tile of the panel covers (r, c), or None."""
        r0, c0 = origin
        di, dj = r - r0, c - c0
        if di < 0 or dj < 0:
            return None
        i, ri = divmod(di, PITCH)
        j, rj = divmod(dj, PITCH)
        if i > 2 or j > 2 or ri >= TILE or rj >= TILE:
            return None
        if (i, j) == (1, 1):          # the thumbnail, never observed to react
            return None
        return (i, j)

    def step(self, state, action):
        name = getattr(action, "name", action)
        name = name if isinstance(name, str) else str(name)
        name = name.rsplit(".", 1)[-1].upper()

        x = getattr(action, "x", None)
        y = getattr(action, "y", None)

        if "ACTION6" not in name or x is None or y is None:
            return state, self._status(state)
        if state.origin is None:
            return state, self._status(state)

        hit = self._tile_at(state.origin, int(y), int(x))
        if hit is None:
            return state, self._status(state)

        i, j = hit
        cur = state.tiles[i][j]
        new = TILE_DARK if cur == TILE_LIGHT else TILE_LIGHT
        tiles = tuple(
            tuple(new if (a, b) == (i, j) else state.tiles[a][b] for b in range(3))
            for a in range(3)
        )
        nxt = state._replace(tiles=tiles, moves=state.moves + 1)
        return nxt, self._status(nxt)

    def _status(self, state):
        return _status("LEVEL_COMPLETED" if self.is_goal(state) else "RUNNING")

    # -- queries -------------------------------------------------------------

    def is_goal(self, state):
        if state.origin is None or state.target is None:
            return False
        return state.tiles == state.target

    def fingerprint(self, state):
        # `moves` is deliberately left out: it only affects the ignored step bar.
        return (state.origin, state.tiles)

    # -- rendering -----------------------------------------------------------

    def render(self, state):
        raw = _thaw(state.base)
        grid = _dig(raw, state.path)

        if state.origin is not None:
            r0, c0 = state.origin
            for i in range(3):
                for j in range(3):
                    if (i, j) == (1, 1):
                        continue
                    v = state.tiles[i][j]
                    for r in range(r0 + PITCH * i, r0 + PITCH * i + TILE):
                        row = grid[r]
                        for c in range(c0 + PITCH * j, c0 + PITCH * j + TILE):
                            row[c] = v

        if state.counter is not None and state.moves:
            crow, full = state.counter
            used = min(2 * state.moves, state.cols)
            row = grid[crow]
            for k in range(used):
                row[state.cols - 1 - k] = full - 1

        return raw

    # -- checking debt -------------------------------------------------------

    def ignore(self, frame):
        """
        The bottom step bar only.  Two of its cells go 12 -> 11 per effective
        move, but a single recorded step does not pin down how the bar keeps
        going, so it is excluded rather than guessed at.
        """
        try:
            raw = _raw(frame)
            _, grid = _locate_grid(raw)
            counter = _find_counter(grid)
            if counter is None:
                return []
            crow, _ = counter
            return [(crow, c) for c in range(len(grid[0]))]
        except Exception:
            return []


def _status(name):
    value = getattr(Status, name, None)
    return name if value is None else value


def build(version: int = 1) -> WorldModel:
    return Ft09World(version)


# ---------------------------------------------------------------------------
# Registry adapter, added by scripts/wm/extract_model.py.
# The brain writes `build(version)`; the registry calls
# `<game>_world_model(**kwargs)` and passes keywords a brain-written model has
# never heard of (`legacy=[...]`, used by the simplification pass). Swallowing
# them keeps the game-agnostic tools working against a recovered model instead
# of failing on an argument it was never asked to support.
# ---------------------------------------------------------------------------
def ft09_world_model(version: int = 1, **_ignored):
    return build(version)
