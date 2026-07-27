"""Hand-authored sk48 world model — authored by Claude Code, standing in for what
ClaudeBrain(API) would generate.

Learned black box. Nothing was inherited from tu93 or m0r0: this game is not a
maze at all, and none of their vocabulary applies.

  the thing you drive  a 6x6 head box (border value 6, interior 0) that slides up
                       and down one column, 6 px per action, dragging a vertical
                       wire behind it. It never moves sideways.
  the wire             two rows of alternating 1/2 running right from the head at
                       head_row+2. ACTION4 extends it 6 px, ACTION3 retracts it.
                       Its tip is the only other thing that varies.
  so the state is      (head row, wire tip) — two integers. That is the whole
                       game state, which is why the reachable space is tiny and
                       the interesting difficulty is entirely in the goal.
  targets              three 4x4 colour blocks in one column on the right, each on
                       its own row band.
  connecting           a colour is connected when an extension CROSSES INTO its
                       block: the tip must go from short of the block to inside
                       it. Sliding an already-long wire over a block does nothing,
                       and neither does extending further when the tip is already
                       past — the first version of this model got that second
                       clause wrong, planned a 12-action solution on it, and the
                       plan did nothing in the real engine.
  holding              retracting the wire to its minimum drops the current
                       connection. Retracting one step short holds it, which is
                       what makes three simultaneous connections possible with one
                       wire.
  the order            the bottom strip shows the three colours in an order that
                       is NOT their vertical order, and that order is enforced:
                       connecting them 8 -> 14 -> 9 clears L0 in 22 actions, while
                       8 -> 9 -> 14 punches nothing after the first.
  goal                 all three colours connected at once.
  moving while wired    UNDERIVED. Enumerating the real engine (73 states, 292
                       transitions, 3229 engine steps) shows the head sometimes
                       cannot move vertically while the wire is fully extended,
                       and the pattern does not reduce to anything simple: with
                       nothing connected and with (8,14) connected, head 18 cannot
                       go up, but with exactly (8,) connected it can. Rather than
                       guess, step() takes the CONSERVATIVE reading — no vertical
                       movement while the wire passes through any block — which
                       can only make the planner miss solutions, never invent one.
                       A model that under-claims is recoverable; one that
                       over-claims spends real actions on nonsense.

ACTION6 is inert everywhere tried (24 of 27 explorer candidates); ACTION7 is an
undo that steps the whole state back one action and is not modelled — the planner
has no use for it, and modelling it would need a history in the state.

THIS MODEL IS FOR L0 ONLY. L1 transposes the geometry — four colours in one ROW
instead of three in one COLUMN — and nothing that connects on L0 connects there:
not extending at any head row, not sweeping an extended wire through the block
row, not the coordinate action on any block. The model still produces a plan for
L1 because its rules are written in terms of blocks and a checklist, and that
plan does not clear. Reconstructing L1 and planning it is therefore a known
false positive, recorded here rather than hidden.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core import Action, Frame, Status, WorldModel

HEAD_BORDER, HEAD_FILL = 6, 0
WIRE = (1, 2)                # the horizontal wire alternates these
VWIRE = (2, 3)               # the vertical wire behind the head
FIELD = 4                    # the open field the wire is drawn over
STEP = 6
HEAD_SIZE = 6
WIRE_ROW_OFFSET = 2          # the wire runs at head_row + 2 and + 3


@dataclass(frozen=True)
class Sk48State:
    head_row: int = 0
    tip: int = 0                  # rightmost column the wire reaches
    connected: tuple = ()         # colours connected so far, in the order made


def sk48_world_model(version: int = 1) -> WorldModel:
    ctx: dict = {}

    def _find_head(frame):
        rows, cols = len(frame), len(frame[0])
        cells = {(r, c) for r in range(rows) for c in range(cols)
                 if frame[r][c] == HEAD_BORDER}
        if not cells:
            return None, None
        r0 = min(r for r, _ in cells)
        c0 = min(c for r, c in cells if r == r0)
        return r0, c0

    def _blocks(frame, value):
        rows, cols = len(frame), len(frame[0])
        cells = {(r, c) for r in range(rows) for c in range(cols)
                 if frame[r][c] == value}
        found, claimed = [], set()
        for r, c in sorted(cells):
            if (r, c) in claimed:
                continue
            blk = {(r + i, c + j) for i in range(4) for j in range(4)}
            if blk <= cells:
                claimed |= blk
                found.append((r, c))
        return found

    def reconstruct(frame: Frame) -> Sk48State:
        head_r, head_c = _find_head(frame)
        wire_row = head_r + WIRE_ROW_OFFSET
        tip = max((c for c in range(len(frame[0])) if frame[wire_row][c] in WIRE),
                  default=head_c + HEAD_SIZE - 1)

        # Targets: the colour blocks stacked on the right. The checklist strip at
        # the bottom gives the required ORDER, which is not their vertical order.
        colours = sorted({v for row in frame for v in row}
                         - {HEAD_BORDER, HEAD_FILL, FIELD, 5} - set(WIRE) - set(VWIRE))
        targets, checklist = {}, []
        for v in colours:
            bs = _blocks(frame, v)
            right = [b for b in bs if b[1] > len(frame[0]) // 2 - 8 and b[0] < 50]
            bottom = [b for b in bs if b[0] >= 50]
            if right and bottom:
                targets[v] = right[0]
                checklist.append((bottom[0][1], v))
        order = tuple(v for _, v in sorted(checklist))

        ctx.update(bg=[list(r) for r in frame], head_c=head_c, rows=len(frame),
                   cols=len(frame[0]), targets=targets, order=order,
                   min_tip=head_c + HEAD_SIZE - 1,
                   head_rows=_head_rows(frame, head_c))
        return Sk48State(head_row=head_r, tip=tip, connected=())

    def _head_rows(frame, head_c):
        """Rows the head box can occupy: every 6-step offset that stays on field."""
        out = []
        r = 0
        while r + HEAD_SIZE <= len(frame):
            out.append(r)
            r += STEP
        return tuple(out)

    def _through(tip, row):
        """The colour whose block the wire currently passes through, if any."""
        for v, (br, bc) in ctx["targets"].items():
            if br <= row <= br + 3 and tip >= bc:
                return v
        return None

    def _crossed(tip_before, tip_after, row):
        """The colour whose block this extension crossed INTO, if any.

        Not "the wire now overlaps the block" — that is what the refuted first
        version checked, and it let the planner believe a wire already extended
        past a block could connect it by extending once more.
        """
        for v, (br, bc) in ctx["targets"].items():
            if br <= row <= br + 3 and tip_before < bc <= tip_after:
                return v
        return None

    def step(state: Sk48State, action: Action):
        name = action.name
        head_row, tip, conn = state.head_row, state.tip, state.connected
        if name in ("ACTION1", "ACTION2"):
            nxt = head_row + (-STEP if name == "ACTION1" else STEP)
            if nxt < 0 or nxt + HEAD_SIZE > ctx["rows"]:
                return state, Status.RUNNING
            # Conservative: a wire currently through a block is treated as snagged.
            # See "moving while wired" in the module docstring — the real rule is
            # not derived, and this reading only ever costs the planner options.
            if _through(tip, head_row + WIRE_ROW_OFFSET) is not None:
                return state, Status.RUNNING
            head_row = nxt
        elif name == "ACTION4":
            if tip + STEP >= ctx["cols"]:
                return state, Status.RUNNING
            before_tip = tip
            tip += STEP
            # A connection is made by an extension CROSSING INTO a block, and only
            # if this colour is the next one the checklist calls for.
            hit = _crossed(before_tip, tip, head_row + WIRE_ROW_OFFSET)
            if hit is not None and hit not in conn:
                want = ctx["order"][len(conn)] if len(conn) < len(ctx["order"]) else None
                if hit == want:
                    conn = conn + (hit,)
        elif name == "ACTION3":
            if tip - STEP < ctx["min_tip"]:
                return state, Status.RUNNING
            tip -= STEP
            # Retracting to the minimum drops the connection being held.
            if tip <= ctx["min_tip"] and conn:
                conn = conn[:-1]
        else:
            return state, Status.RUNNING          # ACTION6 inert, ACTION7 not modelled

        nxt = Sk48State(head_row, tip, conn)
        return nxt, (Status.LEVEL_COMPLETED if is_goal(nxt) else Status.RUNNING)

    def render(state: Sk48State) -> Frame:
        raise NotImplementedError(
            "sk48's frame is not reconstructed pixel-for-pixel yet: the head box, "
            "both wires and the checklist punch-outs would all have to be drawn. "
            "The dynamics above are enough to plan with, and a model that cannot "
            "render says so rather than returning a wrong frame."
        )

    def is_goal(state: Sk48State) -> bool:
        return len(state.connected) == len(ctx.get("order", ())) and bool(ctx.get("order"))

    return WorldModel(
        version=version,
        reconstruct=reconstruct, step=step, render=render, is_goal=is_goal,
        notes="sk48: a head that slides in one column and extends a wire right; "
              "connect the colour blocks in the order the bottom strip shows",
        source_code="see agents/wm/models/sk48.py",
        confidence=0.6,
        fingerprint=lambda s: (s.head_row, s.tip, s.connected),
    )


# --------------------------------------------------------------------------- #
# Site metadata
# --------------------------------------------------------------------------- #

TITLE = "sk48"
BLURB = ("Not a maze: a head slides up and down one column and extends a wire to "
         "the right. Connect three colour blocks — but only by extending into "
         "them, never by sliding past, never letting the wire fully retract, and "
         "in the order a strip at the bottom of the screen quietly specifies.")
VERSION_BY_LEVEL = {0: "v1"}
MECHANIC_BY_LEVEL = {
    0: "wire-laying: connect three colour blocks by extending into each, holding "
       "the previous connections, in the order the bottom strip shows",
    1: "four colours in one row instead of three in one column; nothing that "
       "connects on L0 connects here — unsolved, and the model knows it is not "
       "modelling this level",
}
LEGACY_VARIANTS = []
DEEP_DIVES = []
