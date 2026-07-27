"""Core data types for the verified world-model solve core.

Everything here is stdlib-only and Kaggle-safe (no numpy required at import
time). Frames are plain 2D int grids so the whole loop is trivially
serializable and testable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Hashable, Optional

# A frame is a 2D grid of small ints (0-15 colours in the real games).
Frame = list[list[int]]

# Opaque model-internal state. Brains choose the representation; the loop only
# passes it around. For BFS it must be fingerprintable (default: repr).
State = Any


class Status:
    """Terminal/non-terminal status of a single attempt (Baseline1 vocabulary)."""

    RUNNING = "RUNNING"
    LEVEL_COMPLETED = "LEVEL_COMPLETED"
    GAME_OVER = "GAME_OVER"

    TERMINAL = frozenset({LEVEL_COMPLETED, GAME_OVER})


@dataclass(frozen=True)
class Action:
    """An environment action. `x`/`y` carry ACTION6 coordinates when present."""

    name: str
    x: Optional[int] = None
    y: Optional[int] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"name": self.name}
        if self.x is not None:
            d["x"] = self.x
        if self.y is not None:
            d["y"] = self.y
        return d

    def __str__(self) -> str:
        if self.x is not None or self.y is not None:
            return f"{self.name}({self.x},{self.y})"
        return self.name


@dataclass
class Transition:
    """One real, recorded environment step. Immutable ground truth."""

    step_index: int
    action: Action
    before_frame: Frame
    # None when the engine returned no frame (it does that on death): there is
    # then nothing to verify a render against, only the status.
    after_frame: Optional[Frame]
    status: str
    changed_cells: int = 0

    def to_dict(self) -> dict:
        return {
            "step_index": self.step_index,
            "action": self.action.to_dict(),
            "status": self.status,
            "changed_cells": self.changed_cells,
        }


class Timeline:
    """Append-only history of real transitions for a single attempt.

    The initial frame plus the ordered actions are sufficient to reconstruct
    any intermediate real state (games are deterministic per attempt), which is
    exactly what `run_backtest` relies on.
    """

    def __init__(self, initial_frame: Frame):
        self._initial_frame: Frame = _copy_frame(initial_frame)
        self._transitions: list[Transition] = []

    @property
    def initial_frame(self) -> Frame:
        return self._initial_frame

    @property
    def transitions(self) -> list[Transition]:
        return list(self._transitions)

    @property
    def current_frame(self) -> Frame:
        if self._transitions:
            return self._transitions[-1].after_frame
        return self._initial_frame

    def record(self, transition: Transition) -> None:
        self._transitions.append(transition)

    def __len__(self) -> int:
        return len(self._transitions)


@dataclass
class WorldModel:
    """A brain-authored executable theory of the game.

    The four callables are the same interface Baseline1 forces its coding agent
    to fill (engine / reconstruction / renderer / planner-target), and the same
    joint state+mechanism program Schema keeps in one editable file:

      reconstruct(frame)        -> initial model state for the level
      step(state, action)       -> (new_state, status)      # the dynamics
      render(state)             -> frame                     # for verification
      is_goal(state)            -> bool                      # inferred win test

    `source_code` holds the literal code the brain wrote, so the trace can carry
    it as distillation supervision. `fingerprint` keys BFS visited-sets.
    """

    version: int
    reconstruct: Callable[[Frame], State]
    step: Callable[[State, Action], tuple[State, str]]
    render: Callable[[State], Frame]
    is_goal: Callable[[State], bool]
    notes: str = ""
    source_code: str = ""
    confidence: float = 0.5
    fingerprint: Callable[[State], Hashable] = field(default=lambda s: repr(s))
    # Optional: given a frame, return the cells (r, c) to EXCLUDE from
    # verification — e.g. a HUD / step-counter region that changes every step
    # but carries no game-logic. Prefer modelling those cells in render();
    # treat a non-empty ignore set as modelling debt (Baseline1's
    # apply_render_overrides warning). Default None = compare every cell.
    ignore: Optional[Callable[[Frame], object]] = None


# --------------------------------------------------------------------------- #
# small frame helpers (stdlib-only)
# --------------------------------------------------------------------------- #


def _copy_frame(frame: Frame) -> Frame:
    return [list(row) for row in frame]


def frames_equal(a: Frame, b: Frame, ignored=None) -> bool:
    """True if frames match, optionally skipping an `ignored` set of (r, c) cells."""
    if not ignored:
        return a == b
    if len(a) != len(b):
        return False
    for r, (ra, rb) in enumerate(zip(a, b)):
        if len(ra) != len(rb):
            return False
        for c, (va, vb) in enumerate(zip(ra, rb)):
            if (r, c) in ignored:
                continue
            if va != vb:
                return False
    return True


def diff_cells(a: Frame, b: Frame, ignored=None) -> int:
    """Count differing cells (excluding `ignored`), or the larger size on shape mismatch."""
    if len(a) != len(b) or any(len(ra) != len(rb) for ra, rb in zip(a, b)):
        return max(sum(len(r) for r in a), sum(len(r) for r in b))
    return sum(
        1
        for r, (ra, rb) in enumerate(zip(a, b))
        for c, (va, vb) in enumerate(zip(ra, rb))
        if va != vb and not (ignored and (r, c) in ignored)
    )


def ignored_cells(model, frame: Frame):
    """Resolve a model's HUD/ignore mask for a frame; None when it declares none."""
    if getattr(model, "ignore", None) is None:
        return None
    try:
        cells = model.ignore(frame)
    except Exception:  # noqa: BLE001 - a broken ignore mask just means "compare all"
        return None
    return {tuple(c) for c in cells} or None


def state_fields(state):
    """(name, value) pairs for a model's state, whatever shape it has.

    The contract has only ever required a state to be immutable and hashable
    through `fingerprint`. Every hand-written model happened to use a dataclass,
    so the tools that introspect state called `dataclasses.fields()` directly —
    and the first model written by the brain, which uses a plain class, broke
    them. It broke gen_site.py (the whole site build died) and export_dataset.py
    (ft09 and vc33, the two games solved unattended, produced zero training
    pairs and said nothing about it). Fixed twice separately before being put
    here, which is why it is here.
    """
    import dataclasses
    if dataclasses.is_dataclass(state):
        return [(f.name, getattr(state, f.name)) for f in dataclasses.fields(state)]
    if hasattr(state, "_fields"):                       # NamedTuple
        return list(zip(state._fields, state))
    if hasattr(state, "__dict__"):
        return [(k, v) for k, v in vars(state).items() if not k.startswith("_")]
    if hasattr(state, "__slots__"):
        return [(k, getattr(state, k, None)) for k in state.__slots__]
    if isinstance(state, tuple):
        return [(f"f{i}", v) for i, v in enumerate(state)]
    return []
