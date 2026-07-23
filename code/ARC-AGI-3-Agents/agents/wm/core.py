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
    after_frame: Frame
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


# --------------------------------------------------------------------------- #
# small frame helpers (stdlib-only)
# --------------------------------------------------------------------------- #


def _copy_frame(frame: Frame) -> Frame:
    return [list(row) for row in frame]


def frames_equal(a: Frame, b: Frame) -> bool:
    return a == b


def diff_cells(a: Frame, b: Frame) -> int:
    """Count differing cells between two equally-shaped frames.

    Mismatched shapes are treated as maximally different (a strong signal that
    the renderer is wrong), returning the larger cell count.
    """
    if len(a) != len(b) or any(len(ra) != len(rb) for ra, rb in zip(a, b)):
        return max(sum(len(r) for r in a), sum(len(r) for r in b))
    return sum(
        1
        for ra, rb in zip(a, b)
        for va, vb in zip(ra, rb)
        if va != vb
    )
