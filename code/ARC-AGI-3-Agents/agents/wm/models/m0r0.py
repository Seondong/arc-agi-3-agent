"""Hand-authored m0r0 world model — authored by Claude Code, standing in for what
ClaudeBrain(API) would generate.

Learned black box, by stepping the engine and reading frames; `environment_files/`
is never read. Nothing was carried over from tu93 without being re-measured, and
almost nothing survived that test:

  floor        value **5** is the corridor here and 11/12 are the two solid
               territories — the opposite of tu93, where 5 was wall. The blocks
               start inside the 5-region, move through it, and stop exactly where
               it ends.
  agents       two solid square blocks of value 10, no facing notch anywhere. The
               SIZE IS PER LEVEL and must be read off the frame: L0 has 5x5 blocks
               moving 5 px, L1 has 4x4 blocks moving 4. A model that hardcodes the
               first level's size sees nothing at all on the second.
  step         equal to the agent's own size, whatever that is.
  mirror       one action drives both. ACTION1/2 move them the same way
               vertically; ACTION3/4 move them in OPPOSITE horizontal directions.
               The column sum is conserved while both are free: 19+39, 14+44,
               9+49, 24+34 all give 58.
  independence they are not rigidly locked. Each is blocked by its own walls: the
               second ACTION1 took the left block 44 -> 39 while the right one
               stayed at 44, because rows 39-43 cols 39-43 are territory.
  ACTION5      changes nothing on L0.

  counters     rows 0 and 63 are two mirrored step counters, 64 cells each, 5 ->
               0, consumed from the right along row 0 and from the left along row
               63. The RATE is not pinned down: 13 actions spent 6 ticks, a fully
               blocked directional action costs nothing (steps 3 and 8 of the
               probe), and ACTION5 costs one even though it moves nothing. Not
               modelled — excluded via ignore(), the same modelling debt tu93's
               HUD row carries. It will matter eventually: a counter that reaches
               zero is the obvious way to lose.

  hazard 8     walking INTO value 8 sends every agent back to its starting square.
               The first reading of this was wrong and is worth keeping as a
               warning: the reset was first seen on a move where one agent went
               and the other was blocked, so it was written down as "breaking the
               mirror is punished". That law made L1 unsolvable — 34 reachable
               states, none with the pair meeting — which is what forced a second
               look. Enumerating with the law switched OFF produced 23 candidate
               asymmetric moves; ten were run against the engine and SEVEN did not
               reset at all. The three that did were exactly the three where the
               blocked agent's destination contained value 8; the seven that did
               not were blocked by ordinary territory (6, 15). Ten out of ten.
               Breaking the mirror is free; touching the hazard is not.
  L2 switches  value 9 appears as 2x2 marks and they are a CONTROL TRANSFER.
               ACTION6 on a mark turns it into 11 and both agents from 10 into 1;
               the agents then do not move at all and ACTION1-4 drive the selected
               mark instead, 4 px per action. ACTION6 on a frozen agent cancels
               (agents back to 10, marks back to 9 where they now stand); on
               another mark it hands control over; on the selected mark it does
               nothing. A moved mark persists. ACTION6 did nothing whatsoever on
               L0 and L1, which is why it was nearly written off.
               L2 IS NOT SOLVED and is not modelled. Ruled out by measurement: the
               agents cannot meet (column 30, the mirror axis, is walled by 15 and
               hazard 8 for the whole band), marks cannot reach the agents (they
               stop at row 15), marks cannot merge (they block each other), and
               repositioning a mark leaves the agents' reachable set at exactly
               101 states. What the marks are FOR is the open question.
  goal         the two agents must OCCUPY THE SAME SQUARE. There is no goal tile
               anywhere — the win condition is a relation between the two agents,
               not a place. Found by enumerating the reachable states inside the
               certified model (2627 of them, free) and noticing 43 in which the
               pair coincides, then spending 15 real actions on the shortest one:
               LEVEL_COMPLETED. The halves are not separated as first assumed;
               a wide corridor at rows 9-13 lets each agent cross to the other
               side, which is the only way a mirror pair can ever meet.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core import Action, Frame, Status, WorldModel

FLOOR = 5                    # the corridor — NOT a wall, unlike tu93
AGENT = 10                   # a solid 5x5 block
TERRITORY = (11, 12)         # L0's two halves; both block movement
HAZARD = 8                   # appears from L1; see "mirror law" above
# Direction per action; the magnitude is the agent's size, read from the frame.
_DIR = {"ACTION1": (-1, 0), "ACTION2": (1, 0), "ACTION3": (0, -1), "ACTION4": (0, 1)}


@dataclass(frozen=True)
class M0r0State:
    """Both agents. `sign` is +1 for the one that moves with the action and -1 for
    its mirror image; it is fixed at reconstruct time by which side of the axis
    the agent starts on."""
    agents: tuple = ()        # ((row, col, sign), ...)

    @property
    def alive(self) -> bool:
        return bool(self.agents)


# Retired rules, kept behind switches so a refuted model can be RE-RUN instead of
# remembered — and so the law below can be enumerated with it turned off, which is
# the only way to find candidate counterexamples to it.
LEGACY_SWITCHES = ("no_mirror_law", "no_goal")


def m0r0_world_model(version: int = 1, legacy=()) -> WorldModel:
    ctx: dict = {}
    legacy = frozenset(legacy)
    unknown = legacy - set(LEGACY_SWITCHES)
    if unknown:
        raise ValueError(f"unknown legacy switch(es): {sorted(unknown)}")

    def _agent_blocks(frame):
        """Every maximal solid square of AGENT, and the size they share.

        The size is measured, not assumed: it changes from level to level.
        """
        rows, cols = len(frame), len(frame[0])
        cells = {(r, c) for r in range(rows) for c in range(cols)
                 if frame[r][c] == AGENT}
        if not cells:
            return [], 0
        found, claimed = [], set()
        for r, c in sorted(cells):
            if (r, c) in claimed:
                continue
            size = 0
            while all((r + i, c + j) in cells
                      for i in range(size + 1) for j in range(size + 1)):
                size += 1
            if size == 0:
                continue
            claimed |= {(r + i, c + j) for i in range(size) for j in range(size)}
            found.append((r, c, size))
        sizes = {b[2] for b in found}
        size = min(sizes) if sizes else 0
        return [(r, c) for (r, c, _) in found], size

    def reconstruct(frame: Frame) -> M0r0State:
        rows, cols = len(frame), len(frame[0])
        bg = [list(row) for row in frame]
        agents, size = _agent_blocks(frame)
        for (r, c) in agents:                       # the agents are not scenery
            for i in range(size):
                for j in range(size):
                    bg[r + i][c + j] = FLOOR
        # The mirror axis is halfway between the two agents' columns; with one
        # agent it degenerates to "no mirroring", which is the safe reading.
        axis = (sum(c for _, c in agents) / len(agents)) if agents else 0
        enforce = "no_mirror_law" not in legacy       # see "hazard 8" above
        ctx.update(bg=bg, rows=rows, cols=cols, axis=axis, size=size,
                   enforce_mirror=enforce, start=tuple(agents))
        return M0r0State(agents=tuple((r, c, 1 if c <= axis else -1)
                                      for (r, c) in agents))

    def _hazard(r, c) -> bool:
        """Does the block an agent is trying to enter contain the hazard?"""
        bg, rows, cols, size = ctx["bg"], ctx["rows"], ctx["cols"], ctx["size"]
        if not (0 <= r <= rows - size and 0 <= c <= cols - size):
            return False
        return any(bg[r + i][c + j] == HAZARD
                   for i in range(size) for j in range(size))

    def _free(r, c) -> bool:
        """An agent fits at (r, c) only where every cell it covers is corridor."""
        bg, rows, cols, size = ctx["bg"], ctx["rows"], ctx["cols"], ctx["size"]
        if not (0 <= r <= rows - size and 0 <= c <= cols - size):
            return False
        return all(bg[r + i][c + j] == FLOOR for i in range(size) for j in range(size))

    def step(state: M0r0State, action: Action):
        d = _DIR.get(action.name)
        if d is None or not state.agents:
            return state, Status.RUNNING        # ACTION5 does nothing (observed L0)
        step_px = ctx["size"]
        dr, dc = d[0] * step_px, d[1] * step_px
        moved, hazard = [], False
        for (r, c, sign) in state.agents:
            nr, nc = r + dr, c + dc * sign      # vertical shared, horizontal mirrored
            if _hazard(nr, nc):
                hazard = True
            moved.append((nr, nc, sign) if _free(nr, nc) else (r, c, sign))
        if hazard and ctx.get("enforce_mirror"):
            # An agent walked into the hazard: everyone goes back to the start.
            starts = ctx.get("start", ())
            moved = [(sr, sc, sign) for (sr, sc), (_, _, sign)
                     in zip(starts, state.agents)]
        nxt = M0r0State(tuple(moved))
        return nxt, (Status.LEVEL_COMPLETED if is_goal(nxt) else Status.RUNNING)

    def render(state: M0r0State) -> Frame:
        grid = [list(row) for row in ctx["bg"]]
        size = ctx["size"]
        for (r, c, _) in state.agents:
            for i in range(size):
                for j in range(size):
                    grid[r + i][c + j] = AGENT
        return grid

    def ignore(frame: Frame):
        # The two step counters. Their rate is observed but not understood (see
        # the module docstring), so they are excluded from verification rather
        # than predicted wrongly. Modelling debt, recorded as such.
        cols = len(frame[0])
        return [(0, c) for c in range(cols)] + [(len(frame) - 1, c) for c in range(cols)]

    def is_goal(state: M0r0State) -> bool:
        """The two mirror agents standing on the same square."""
        if "no_goal" in legacy:
            return False
        seen = set()
        for (r, c, _) in state.agents:
            if (r, c) in seen:
                return True
            seen.add((r, c))
        return False

    return WorldModel(
        version=version,
        reconstruct=reconstruct, step=step, render=render, is_goal=is_goal,
        notes="m0r0: a mirror pair of 5x5 agents; one action drives both, mirrored "
              "horizontally; the level clears when they stand on the same square",
        source_code="see agents/wm/models/m0r0.py",
        confidence=0.85,
        fingerprint=lambda s: s.agents,
        ignore=ignore,
    )


# --------------------------------------------------------------------------- #
# Site metadata
# --------------------------------------------------------------------------- #

TITLE = "m0r0"
BLURB = ("Two 5x5 agents driven by one action: together vertically, opposite each "
         "other horizontally. There is no goal tile — the level clears when the "
         "mirror pair manages to stand on the same square, which was found by "
         "enumerating the model's reachable states rather than by searching the "
         "environment.")
MECHANIC_BY_LEVEL = {
    0: "mirror pair: one action drives both, horizontal motion is opposite, each "
       "blocked by its own walls; the level clears when the two occupy the same square",
    1: "agents are 4x4 stepping 4, not 5x5 stepping 5; walking into hazard value 8 "
       "sends every agent back to its start",
    2: "value-9 marks are ACTION6 switches: throwing one turns both agents from "
       "value 10 into value 1 — not yet modelled",
}
VERSION_BY_LEVEL = {0: "v2", 1: "v5"}
LEGACY_VARIANTS = [
    ("v4", ["no_mirror_law"], "before the hazard rule: no reset at all"),
    ("v5", [], "+ walking into hazard 8 resets everyone"),
]
DEEP_DIVES = []
