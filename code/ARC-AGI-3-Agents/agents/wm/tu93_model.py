"""Hand-authored tu93 world model — authored by Claude Code (Max subscription),
standing in for what ClaudeBrain(API) would generate.

Every rule below was learned black-box, from stepping the engine and reading the
returned frames; `environment_files/` is never read. Each rule notes the level
whose observations forced it, so the model doubles as a record of what was
learned when (the narrative lives in artifacts/wm_journal/*.jsonl).

  L0  maze + player          3x3 player block (9) with a facing notch (4) moving
                             6px per action; walls (5) block; goal (14) clears
                             the level. Row 63 is a HUD bar -> ignore().
  L1  guards (8 + notch 15)  never move on their own; entering the cell a guard
                             FACES makes it lunge into that cell -> GAME_OVER;
                             stepping onto one from any other side removes it.
  L2  many guards            the same rule for N guards; the guard that catches
                             the player renders a "fed" notch (11 instead of 15).
  L3  patrollers (12)        advance 6px along their facing on every turn where
                             a player actually changes square, bouncing off walls
                             (the notch flips on arrival, showing where it goes
                             next); sharing a square with a player kills it.
  L4  several player blocks  one action drives every player block; each is
                             blocked independently by walls.
"""
from __future__ import annotations

from dataclasses import dataclass

from .core import Action, Frame, Status, WorldModel

WALL, DOOR, FLOOR, PLAYER, GOAL, NOTCH, BORDER = 5, 2, 0, 9, 14, 4, 6
GUARD, GUARD_NOTCH, GUARD_FED = 8, 15, 11   # guard body, facing notch, "fed" notch
PATROL = 12                                  # moving patroller (L3+), notch 15 too
STEP = 6                                     # pixels moved per action

_DELTA = {"ACTION1": (-STEP, 0), "ACTION2": (STEP, 0),
          "ACTION3": (0, -STEP), "ACTION4": (0, STEP)}
_FACE = {"ACTION1": "U", "ACTION2": "D", "ACTION3": "L", "ACTION4": "R"}
_NOTCH_OFF = {"U": (0, 1), "D": (2, 1), "L": (1, 0), "R": (1, 2)}
_ACT = {"U": "ACTION1", "D": "ACTION2", "L": "ACTION3", "R": "ACTION4"}
_FLIP = {"U": "D", "D": "U", "L": "R", "R": "L"}


@dataclass(frozen=True)
class Tu93State:
    """Everything that varies within a level. The maze itself is static context."""
    # One entry (row, col, facing) per player-controlled block. L0-L3 have one,
    # L4 has two; all of them obey the same action.
    players: tuple = ()
    moved: bool = False               # any action taken yet (HUD flag)
    guards: tuple = ()                # (row, col, facing) — stationary, lethal head-on
    patrols: tuple = ()               # (row, col, facing) — moving, lethal on contact
    killer: tuple | None = None       # guard that caught a player (renders notch 11)

    @property
    def alive(self) -> bool:
        return bool(self.players)


def tu93_world_model(version: int = 1) -> WorldModel:
    ctx: dict = {}

    # -- reconstruction ------------------------------------------------------
    def _blocks(frame, body, notch_vals=(GUARD_NOTCH, GUARD_FED)):
        """Find every 3x3 block of `body` (its facing notch may replace one cell)."""
        rows, cols = len(frame), len(frame[0])
        cells = {(r, c) for r in range(rows) for c in range(cols)
                 if frame[r][c] == body or frame[r][c] in notch_vals}
        found, claimed = [], set()
        for r, c in sorted(cells):
            if (r, c) in claimed:
                continue
            block = {(r + i, c + j) for i in range(3) for j in range(3)}
            if not block <= cells:
                continue
            if not any(frame[rr][cc] == body for rr, cc in block):
                continue                      # a pure-notch overlap, not this body
            claimed |= block
            facing = "R"
            for rr, cc in block:
                if frame[rr][cc] in notch_vals:
                    off = (rr - r, cc - c)
                    for f, o in _NOTCH_OFF.items():
                        if o == off:
                            facing = f
                            break
            found.append((r, c, facing))
        return found

    def reconstruct(frame: Frame) -> Tu93State:
        rows, cols = len(frame), len(frame[0])
        bg = [list(row) for row in frame]

        players = _blocks(frame, PLAYER, notch_vals=(NOTCH,))
        guards = _blocks(frame, GUARD)
        patrols = _blocks(frame, PATROL)
        for group in (players, guards, patrols):          # erase movers from the maze
            for (r, c, _) in group:
                for i in range(3):
                    for j in range(3):
                        bg[r + i][c + j] = FLOOR

        goal_cells = [(r, c) for r in range(rows) for c in range(cols)
                      if frame[r][c] == GOAL]
        goal = (min(r for r, _ in goal_cells), min(c for _, c in goal_cells)) \
            if goal_cells else None

        ctx.update(bg=bg, goal=goal, rows=rows, cols=cols)
        return Tu93State(players=tuple(players), moved=False,
                         guards=tuple(guards), patrols=tuple(patrols))

    # -- geometry ------------------------------------------------------------
    def _wall_in(rrange, crange) -> bool:
        bg, rows, cols = ctx["bg"], ctx["rows"], ctx["cols"]
        for r in rrange:
            for c in crange:
                if not (0 <= r < rows and 0 <= c < cols):
                    return True
                if bg[r][c] in (WALL, BORDER):
                    return True
        return False

    def _blocked_step(r, c, f) -> bool:
        """True if a 3x3 block at (r,c) cannot take a 6px step along `f`."""
        dr, dc = _DELTA[_ACT[f]]
        gap_r = range(r + dr // 2, r + dr // 2 + 3) if dr else range(r, r + 3)
        gap_c = range(c + dc // 2, c + dc // 2 + 3) if dc else range(c, c + 3)
        return (_wall_in(gap_r, gap_c)
                or _wall_in(range(r + dr, r + dr + 3), range(c + dc, c + dc + 3)))

    # -- dynamics ------------------------------------------------------------
    def step(state: Tu93State, action: Action):
        d = _DELTA.get(action.name)
        if d is None or not state.players:
            return state, Status.RUNNING
        dr, dc = d
        face = _FACE[action.name]

        # 1. every player block tries the same move; each is blocked on its own
        new_players, any_moved = [], False
        for (pr, pc, pf) in state.players:
            if _blocked_step(pr, pc, face):
                new_players.append((pr, pc, pf))          # stays put, keeps facing
            else:
                new_players.append((pr + dr, pc + dc, face))
                any_moved = True

        # 2. guards: lethal head-on, removable from behind (L1/L2)
        survivors, killer = [], None
        for (gr, gc, gf) in state.guards:
            fdr, fdc = _DELTA[_ACT[gf]]
            lethal = (gr + fdr, gc + fdc)
            if any((r, c) == lethal for (r, c, _) in new_players):
                lunged = tuple((lethal[0], lethal[1], gf) if (r0, c0) == (gr, gc)
                               else (r0, c0, f0) for (r0, c0, f0) in state.guards)
                return (Tu93State((), True, lunged, state.patrols, killer=lethal),
                        Status.GAME_OVER)
            if any((r, c) == (gr, gc) for (r, c, _) in new_players):
                continue                                   # stepped on from behind
            survivors.append((gr, gc, gf))

        # 3. patrollers advance only when a player really moved (L3)
        new_patrols = []
        for (qr, qc, qf) in state.patrols:
            if not any_moved:
                new_patrols.append((qr, qc, qf))
                continue
            if _blocked_step(qr, qc, qf):
                qf = _FLIP[qf]
                if _blocked_step(qr, qc, qf):
                    new_patrols.append((qr, qc, qf))       # boxed in
                    continue
            mdr, mdc = _DELTA[_ACT[qf]]
            nqr, nqc = qr + mdr, qc + mdc
            if _blocked_step(nqr, nqc, qf):                # notch flips on arrival
                qf = _FLIP[qf]
            new_patrols.append((nqr, nqc, qf))

        # 4. contact with a patroller destroys the player it touches
        hit = {(qr, qc) for (qr, qc, _) in new_patrols}
        if any((r, c) in hit for (r, c, _) in new_players):
            return (Tu93State((), True, tuple(survivors), tuple(new_patrols)),
                    Status.GAME_OVER)

        nxt = Tu93State(tuple(new_players), True, tuple(survivors), tuple(new_patrols))
        if ctx["goal"] is not None and any((r, c) == ctx["goal"]
                                           for (r, c, _) in new_players):
            return nxt, Status.LEVEL_COMPLETED
        return nxt, Status.RUNNING

    # -- rendering -----------------------------------------------------------
    def render(state: Tu93State) -> Frame:
        grid = [list(row) for row in ctx["bg"]]
        for (gr, gc, gf) in state.guards:
            for r in range(gr, gr + 3):
                for c in range(gc, gc + 3):
                    grid[r][c] = GUARD
            nr, nc = _NOTCH_OFF[gf]
            grid[gr + nr][gc + nc] = (GUARD_FED if (gr, gc) == state.killer
                                      else GUARD_NOTCH)
        for (qr, qc, qf) in state.patrols:
            for r in range(qr, qr + 3):
                for c in range(qc, qc + 3):
                    grid[r][c] = PATROL
            nr, nc = _NOTCH_OFF[qf]
            grid[qr + nr][qc + nc] = GUARD_NOTCH
        # The goal tile is drawn OVER a patroller standing on it (observed L4):
        # a patroller crossing the goal square is hidden, not the other way round.
        g = ctx.get("goal")
        if g is not None:
            for r in range(g[0], g[0] + 3):
                for c in range(g[1], g[1] + 3):
                    grid[r][c] = GOAL
        for (pr, pc, pf) in state.players:
            for r in range(pr, pr + 3):
                for c in range(pc, pc + 3):
                    grid[r][c] = PLAYER
            nr, nc = _NOTCH_OFF[pf]
            grid[pr + nr][pc + nc] = NOTCH
        return grid

    def is_goal(state: Tu93State) -> bool:
        g = ctx.get("goal")
        return g is not None and any((r, c) == g for (r, c, _) in state.players)

    def ignore(frame: Frame):
        # Row 63 is a HUD energy/step bar consumed right-to-left at a non-integer
        # rate. It carries no game logic, so it is excluded from verification
        # rather than modelled pixel-exactly (modelling debt, per the brain
        # contract's HUD escape hatch).
        return [(63, c) for c in range(len(frame[0]))]

    return WorldModel(
        version=version,
        reconstruct=reconstruct, step=step, render=render, is_goal=is_goal,
        notes="tu93: maze + guards (static, lethal head-on) + patrollers (moving) "
              "+ possibly several player blocks under one control",
        source_code="see agents/wm/tu93_model.py",
        confidence=0.9,
        fingerprint=lambda s: (s.players, s.guards, s.patrols),
        ignore=ignore,
    )
