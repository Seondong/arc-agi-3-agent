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
  L6  pursuer (13)           sits still until a player crosses the straight line
                             it faces; its notch then turns 11 ("locked on") and
                             it walks that line to the square where it saw the
                             player, and from there follows the player's own trail
                             one square per player move — never a shortcut. Touch
                             kills.
  L4  a second player-looking block  a 3x3 block of 9 with a facing notch that
                             is NOT controlled: it never responds to any action,
                             even when its way is clear and the real player moves
                             the same way. Which look-alike is real cannot be read
                             off a single frame — it is discovered by acting.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core import Action, Frame, Status, WorldModel

WALL, DOOR, FLOOR, PLAYER, GOAL, NOTCH, BORDER = 5, 2, 0, 9, 14, 4, 6
GUARD, GUARD_NOTCH, GUARD_FED = 8, 15, 11   # guard body, facing notch, "fed" notch
PATROL = 12                                  # moving patroller (L3+), notch 15 too
PURSUER, PURSUER_LOCKED = 13, 11             # trail-following hunter (L6+)
STEP = 6                                     # pixels moved per action

_DELTA = {"ACTION1": (-STEP, 0), "ACTION2": (STEP, 0),
          "ACTION3": (0, -STEP), "ACTION4": (0, STEP)}
_FACE = {"ACTION1": "U", "ACTION2": "D", "ACTION3": "L", "ACTION4": "R"}
_NOTCH_OFF = {"U": (0, 1), "D": (2, 1), "L": (1, 0), "R": (1, 2)}
_ACT = {"U": "ACTION1", "D": "ACTION2", "L": "ACTION3", "R": "ACTION4"}
_FLIP = {"U": "D", "D": "U", "L": "R", "R": "L"}

# Top-left corners of 9-blocks that look exactly like the player but never move.
# Discovered by probing, not by reading the frame: on L4 the block at (44,51) sat
# out ACTION1 while the real player took the same step upward with a clear path
# (scripts/probe_l4_second_block.py). Treated as part of the static maze.
INERT_LOOKALIKES = frozenset({(44, 51)})


@dataclass(frozen=True)
class Tu93State:
    """Everything that varies within a level. The maze itself is static context."""
    # One entry (row, col, facing) per player-controlled block. Every level so far
    # has exactly one; L4's second 9-block is inert and lives in the background.
    players: tuple = ()
    moved: bool = False               # any action taken yet (HUD flag)
    guards: tuple = ()                # (row, col, facing) — stationary, lethal head-on
    patrols: tuple = ()               # (row, col, facing) — moving, lethal on contact
    # (row, col, facing, locked, route): a pursuer walks `route` one square per
    # player move. Before it locks on, route is empty and it never moves. `route`
    # holds exactly the squares it is behind the player by, so it stays short.
    pursuers: tuple = ()
    killer: tuple | None = None       # guard that caught a player (renders notch 11)

    @property
    def alive(self) -> bool:
        return bool(self.players)


# Historical variants, so a refuted model can be RE-RUN instead of remembered.
# Each name switches off exactly one rule this file later learned, which is how
# the visualizations regenerate their refutations from the live engine:
#   drive_all_players  every 3x3 block of 9 is a player          (pre-v10)
#   no_pursuer         value 13 is scenery, not an entity        (pre-v11)
#   type_render        co-located enemies drawn in a fixed type
#                      order (guard last) instead of by axis      (pre-v12)
#   no_crossing        a player crossing a patroller leaves it
#                      alive                                      (pre-v12)
LEGACY_SWITCHES = ("drive_all_players", "no_pursuer", "type_render", "no_crossing")


def tu93_world_model(version: int = 1, inert=INERT_LOOKALIKES,
                     legacy=()) -> WorldModel:
    ctx: dict = {}
    legacy = frozenset(legacy)
    unknown = legacy - set(LEGACY_SWITCHES)
    if unknown:
        raise ValueError(f"unknown legacy switch(es): {sorted(unknown)}")
    if "drive_all_players" in legacy:
        inert = ()
    inert = frozenset(tuple(p) for p in inert)

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

        # A look-alike that probing showed to be inert is left in `bg`: it never
        # moves, so it is scenery, and render() then reproduces it for free.
        players = [b for b in _blocks(frame, PLAYER, notch_vals=(NOTCH,))
                   if (b[0], b[1]) not in inert]
        guards = _blocks(frame, GUARD)
        patrols = _blocks(frame, PATROL)
        # A pursuer already showing notch 11 would be mid-chase and its route
        # could not be recovered from one frame; reconstruct only ever runs on a
        # level's first frame, where every pursuer is still asleep.
        pursuers = ([] if "no_pursuer" in legacy
                    else [(r, c, f, False, ()) for (r, c, f) in _blocks(frame, PURSUER)])
        for group in (players, guards, patrols, pursuers):  # erase movers from the maze
            for entry in group:
                r, c = entry[0], entry[1]
                for i in range(3):
                    for j in range(3):
                        bg[r + i][c + j] = FLOOR

        goal_cells = [(r, c) for r in range(rows) for c in range(cols)
                      if frame[r][c] == GOAL]
        goal = (min(r for r, _ in goal_cells), min(c for _, c in goal_cells)) \
            if goal_cells else None

        ctx.update(bg=bg, goal=goal, rows=rows, cols=cols)
        return Tu93State(players=tuple(players), moved=False,
                         guards=tuple(guards), patrols=tuple(patrols),
                         pursuers=tuple(pursuers))

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

    def _sightline(r, c, f):
        """The squares a block at (r,c) can see along `f`, nearest first."""
        dr, dc = _DELTA[_ACT[f]]
        seen, (cr, cc) = [], (r, c)
        while not _blocked_step(cr, cc, f):
            cr, cc = cr + dr, cc + dc
            seen.append((cr, cc))
            if len(seen) > 16:            # a 64px grid cannot be longer than this
                break
        return seen

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

        # 3b. a player that steps into the square a patroller is leaving destroys
        #     it — the moving counterpart of stepping onto a guard from behind.
        #     Ending on the SAME square as a patroller is still death (below);
        #     this is the crossing case, where the two swap past each other.
        #     (Observed L8 k=17: the player dropped into (16,45) as the patroller
        #     there moved off to (16,39), and that patroller never reappeared.)
        if "no_crossing" not in legacy:
            newp = {(r, c) for (r, c, _) in new_players}
            kept = []
            for old, new in zip(state.patrols, new_patrols):
                if (old[0], old[1]) in newp and (old[0], old[1]) != (new[0], new[1]):
                    continue
                kept.append(new)
            new_patrols = kept

        # 4. pursuers: asleep until a player crosses the line they face, then they
        #    walk that line to the sighting square and follow the player's trail
        new_pursuers = []
        for (ur, uc, uf, locked, route) in state.pursuers:
            if not locked:
                ray = _sightline(ur, uc, uf)
                spotted = next((sq for sq in ray
                                if any((r, c) == sq for (r, c, _) in new_players)),
                               None)
                if spotted is None:
                    new_pursuers.append((ur, uc, uf, False, ()))
                    continue
                # It locks on this turn but does not move until the next one.
                route = tuple(ray[:ray.index(spotted) + 1])
                new_pursuers.append((ur, uc, uf, True, route))
                continue
            if not any_moved or not route:
                new_pursuers.append((ur, uc, uf, True, route))
                continue
            (nur, nuc), rest = route[0], route[1:]
            # The player's new square joins the end of the trail it is walking.
            rest = rest + tuple((r, c) for (r, c, _) in new_players[:1])
            ahead = rest[0] if rest else (nur, nuc)
            nuf = uf
            for f, (fdr, fdc) in ((f, _DELTA[_ACT[f]]) for f in _FLIP):
                if (nur + fdr, nuc + fdc) == ahead:
                    nuf = f
            new_pursuers.append((nur, nuc, nuf, True, rest))

        # 5. contact with a patroller or a pursuer destroys the player it touches
        hit = {(qr, qc) for (qr, qc, _) in new_patrols}
        hit |= {(ur, uc) for (ur, uc, _, _, _) in new_pursuers}
        if any((r, c) in hit for (r, c, _) in new_players):
            return (Tu93State((), True, tuple(survivors), tuple(new_patrols),
                              tuple(new_pursuers)), Status.GAME_OVER)

        nxt = Tu93State(tuple(new_players), True, tuple(survivors), tuple(new_patrols),
                        tuple(new_pursuers))
        if ctx["goal"] is not None and any((r, c) == ctx["goal"]
                                           for (r, c, _) in new_players):
            return nxt, Status.LEVEL_COMPLETED
        return nxt, Status.RUNNING

    # -- rendering -----------------------------------------------------------
    def _axis(f):
        return "H" if f in ("L", "R") else "V"

    def _enemy_draw_list(state):
        """Enemies in draw order, bottom first.

        Two entities can share a square, and then exactly one of them is drawn
        whole — body and notch, never a mix. Which one is not a fixed type
        order: on L5 the guard at (42,30), which faces L, is drawn over a
        patroller crossing it horizontally, while the guard at (42,24), which
        faces U, is drawn *under* the same patroller. Across all nine overlaps
        observed on L5 and L8 the discriminator is the axis: a guard wins when
        its facing lies along the axis the other thing is travelling, and loses
        otherwise; a patroller always wins against a pursuer.

        UNDER-DETERMINED. This fits every overlap observed so far, and the one
        competing hypothesis (a fixed z-order by initial row-major position) is
        refuted by the (42,30) case. But no observed frame separates it from
        other axis-free explanations, because the discriminating case — a
        patroller crossing a guard perpendicular to that guard's facing — does
        not arise in any level's solution path. Treat as the least-trusted rule
        in this model; it affects rendering only, never dynamics or planning.
        """
        if "type_render" in legacy:      # the pre-v12 order: guards drawn last
            return ([(0, 0, i, "guard", e) for i, e in enumerate(state.guards)]
                    + [(1, 1, i, "patrol", e) for i, e in enumerate(state.patrols)]
                    + [(2, 2, i, "pursuer", e) for i, e in enumerate(state.pursuers)])
        movers = [(e[0], e[1], e[2]) for e in state.patrols]
        movers += [(e[0], e[1], e[2]) for e in state.pursuers]
        out = []
        for i, (gr, gc, gf) in enumerate(state.guards):
            same_axis = any((mr, mc) == (gr, gc) and _axis(mf) == _axis(gf)
                            for (mr, mc, mf) in movers)
            out.append((2 if same_axis else 0, 0, i, "guard", (gr, gc, gf)))
        for i, e in enumerate(state.patrols):
            out.append((1, 1, i, "patrol", e))
        for i, e in enumerate(state.pursuers):
            out.append((0.5, 2, i, "pursuer", e))
        out.sort(key=lambda t: (t[0], t[1], t[2]))
        return out

    def render(state: Tu93State) -> Frame:
        grid = [list(row) for row in ctx["bg"]]
        for (_z, _t, _i, kind, e) in _enemy_draw_list(state):
            r0, c0, f = e[0], e[1], e[2]
            body = {"guard": GUARD, "patrol": PATROL, "pursuer": PURSUER}[kind]
            for r in range(r0, r0 + 3):
                for c in range(c0, c0 + 3):
                    grid[r][c] = body
            nr, nc = _NOTCH_OFF[f]
            if kind == "guard" and (r0, c0) == state.killer:
                grid[r0 + nr][c0 + nc] = GUARD_FED
            elif kind == "pursuer" and e[3]:
                grid[r0 + nr][c0 + nc] = PURSUER_LOCKED
            else:
                grid[r0 + nr][c0 + nc] = GUARD_NOTCH
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
        fingerprint=lambda s: (s.players, s.guards, s.patrols, s.pursuers),
        ignore=ignore,
    )


# --------------------------------------------------------------------------- #
# Game metadata for the site generators. Game-specific facts live with the
# game's model, so nothing downstream needs a per-game branch.
# --------------------------------------------------------------------------- #

TITLE = "tu93"
BLURB = ("A maze game whose curriculum introduces one new object at a time: a "
         "guard that never moves but kills what steps in front of it, a patroller "
         "that moves only when you do, a block that looks exactly like the player "
         "and is not, and a pursuer that walks your own trail.")

# The version each level was FIRST certified with, and the version that
# reproduces it exactly today — two levels needed a later fix than the one that
# first "certified" them.
VERSION_BY_LEVEL = {0: "v3", 1: "v4", 2: "v7", 3: "v8", 4: "v10", 5: "v12",
                    6: "v11", 7: "v11", 8: "v12"}

MECHANIC_BY_LEVEL = {
    0: "maze, player block, goal tile",
    1: "guard (8): never moves, lethal if you step into the cell it faces, "
       "removable from any other side",
    2: "three guards at once; the one that catches you lunges into your square "
       "and wears a 'fed' notch (11)",
    3: "patroller (12): advances only on turns where the player really moved, "
       "bounces off walls, kills on contact",
    4: "a second 3x3 block of 9 that looks exactly like the player and is never "
       "controlled; patrollers overlap freely and hide under the goal tile",
    5: "nothing new — guards and patrollers composed",
    6: "pursuer (13): sleeps until you cross the line it faces, then follows your "
       "own trail one square per move, forever two squares behind",
    7: "nothing new — pursuer in a corridor maze",
    8: "nothing new — guards, patrollers and a pursuer at once",
}

# Retired versions, reconstructable from the legacy switches, for the fidelity
# matrix. Earlier ones (v0-v8) existed only as edits to this file before the
# switches were added and live in the journals as record, not as runnable code.
LEGACY_VARIANTS = [
    ("v9", ["drive_all_players", "no_pursuer", "type_render", "no_crossing"],
     "every 3x3 block of 9 is a player; value 13 is scenery"),
    ("v10", ["no_pursuer", "type_render", "no_crossing"],
     "+ the inert look-alike: only the block that responds is a player"),
    ("v11", ["type_render", "no_crossing"], "+ the pursuer and its trail"),
    ("v12", [], "+ overlap draw order by axis, and a crossed patroller is destroyed"),
]

# Extra pages this game has beyond the standard three.
DEEP_DIVES = [
    ("l4_evolve.html", 4, "counting cells is not counting things"),
    ("l6_pursuer.html", 6, "the thing that follows you"),
]
