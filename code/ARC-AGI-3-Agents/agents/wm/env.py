"""Environment interface + a synthetic tu93-like maze fixture.

The real project plugs the offline `arc_agi` Arcade in behind `Environment`;
here we ship a deterministic, dependency-free graph maze so the entire solve
core (backtest -> plan -> execute -> misprediction halt) can be unit-tested
without game files or a model API. The maze mirrors the *mechanic shape* of
tu93 (grid of nodes, a deadly cell to route around, a goal) at 1 cell / node so
render/reconstruct stay trivial to read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from .core import Action, Frame, Status, _copy_frame, diff_cells


@dataclass
class StepResult:
    frame: Frame
    status: str
    changed_cells: int


@runtime_checkable
class Environment(Protocol):
    """Minimal environment contract the solve loop drives."""

    available_actions: list[str]

    def reset(self) -> Frame: ...
    def step(self, action: Action) -> StepResult: ...


# --------------------------------------------------------------------------- #
# Synthetic fixture: a 3x3 grid-of-nodes maze with one deadly cell.
# --------------------------------------------------------------------------- #
#
# Cell encoding in the rendered frame:
#   0 = empty floor, 1 = agent, 2 = deadly enemy, 3 = goal
#
# Node layout (index = row*cols + col):
#   0 1 2
#   3 4 5      (4 is the deadly enemy by default)
#   6 7 8
#
# Actions: ACTION1=up, ACTION2=down, ACTION3=left, ACTION4=right.

EMPTY, AGENT, ENEMY, GOAL = 0, 1, 2, 3
_DELTAS = {"ACTION1": (-1, 0), "ACTION2": (1, 0), "ACTION3": (0, -1), "ACTION4": (0, 1)}


class GraphMazeEnv:
    """Deterministic maze. Stepping onto the enemy cell is GAME_OVER."""

    available_actions = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]

    def __init__(
        self,
        rows: int = 3,
        cols: int = 3,
        start: int = 0,
        goal: int = 8,
        enemy: Optional[int] = 4,
    ):
        self.rows = rows
        self.cols = cols
        self.start = start
        self.goal = goal
        self.enemy = enemy
        self._agent = start

    # -- geometry -----------------------------------------------------------
    def _rc(self, node: int) -> tuple[int, int]:
        return divmod(node, self.cols)

    def _node(self, r: int, c: int) -> Optional[int]:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return r * self.cols + c
        return None

    def _move(self, node: int, action: Action) -> int:
        dr, dc = _DELTAS.get(action.name, (0, 0))
        r, c = self._rc(node)
        nxt = self._node(r + dr, c + dc)
        return node if nxt is None else nxt  # blocked move = stay

    def _render(self, agent: int) -> Frame:
        grid = [[EMPTY for _ in range(self.cols)] for _ in range(self.rows)]
        if self.enemy is not None:
            er, ec = self._rc(self.enemy)
            grid[er][ec] = ENEMY
        gr, gc = self._rc(self.goal)
        grid[gr][gc] = GOAL
        ar, ac = self._rc(agent)
        grid[ar][ac] = AGENT  # agent drawn last (wins ties)
        return grid

    # -- Environment protocol ----------------------------------------------
    def reset(self) -> Frame:
        self._agent = self.start
        return self._render(self._agent)

    def step(self, action: Action) -> StepResult:
        before = self._render(self._agent)
        nxt = self._move(self._agent, action)

        if self.enemy is not None and nxt == self.enemy:
            self._agent = nxt
            after = self._render(nxt)
            return StepResult(after, Status.GAME_OVER, diff_cells(before, after))

        self._agent = nxt
        after = self._render(nxt)
        status = Status.LEVEL_COMPLETED if nxt == self.goal else Status.RUNNING
        return StepResult(after, status, diff_cells(before, after))
