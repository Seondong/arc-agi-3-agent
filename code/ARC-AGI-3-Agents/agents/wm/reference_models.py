"""Hand-authored world models for the synthetic maze.

These stand in for what `ClaudeBrain` would generate. `maze_world_model(True)`
is a correct theory (knows the enemy cell is deadly); `maze_world_model(False)`
is a plausible-but-wrong theory (ignores the enemy) used to exercise the
backtest counterexample and the reality-outranks-model plan halt.
"""

from __future__ import annotations

from dataclasses import dataclass

from .core import Action, Frame, Status, WorldModel

EMPTY, AGENT, ENEMY, GOAL = 0, 1, 2, 3
_DELTAS = {"ACTION1": (-1, 0), "ACTION2": (1, 0), "ACTION3": (0, -1), "ACTION4": (0, 1)}


@dataclass(frozen=True)
class MazeState:
    agent: int
    rows: int
    cols: int
    goal: int
    enemy: int  # -1 when absent


def _reconstruct(frame: Frame) -> MazeState:
    rows, cols = len(frame), len(frame[0])
    agent = goal = enemy = -1
    for r in range(rows):
        for c in range(cols):
            v = frame[r][c]
            node = r * cols + c
            if v == AGENT:
                agent = node
            elif v == GOAL:
                goal = node
            elif v == ENEMY:
                enemy = node
    return MazeState(agent=agent, rows=rows, cols=cols, goal=goal, enemy=enemy)


def _render(state: MazeState) -> Frame:
    grid = [[EMPTY] * state.cols for _ in range(state.rows)]
    if state.enemy >= 0:
        er, ec = divmod(state.enemy, state.cols)
        grid[er][ec] = ENEMY
    gr, gc = divmod(state.goal, state.cols)
    grid[gr][gc] = GOAL
    ar, ac = divmod(state.agent, state.cols)
    grid[ar][ac] = AGENT
    return grid


def _make_step(enemy_is_deadly: bool):
    def step(state: MazeState, action: Action) -> tuple[MazeState, str]:
        dr, dc = _DELTAS.get(action.name, (0, 0))
        r, c = divmod(state.agent, state.cols)
        nr, nc = r + dr, c + dc
        if not (0 <= nr < state.rows and 0 <= nc < state.cols):
            nxt = state.agent  # blocked
        else:
            nxt = nr * state.cols + nc
        new_state = MazeState(nxt, state.rows, state.cols, state.goal, state.enemy)
        if enemy_is_deadly and state.enemy >= 0 and nxt == state.enemy:
            return new_state, Status.GAME_OVER
        if nxt == state.goal:
            return new_state, Status.LEVEL_COMPLETED
        return new_state, Status.RUNNING

    return step


def _is_goal(state: MazeState) -> bool:
    return state.agent == state.goal


def maze_world_model(correct: bool = True, version: int = 1) -> WorldModel:
    return WorldModel(
        version=version,
        reconstruct=_reconstruct,
        step=_make_step(enemy_is_deadly=correct),
        render=_render,
        is_goal=_is_goal,
        notes=("enemy cell is deadly; route around it"
               if correct else "enemy ignored (WRONG theory)"),
        source_code=("step: move on grid; enter enemy -> GAME_OVER; "
                     "enter goal -> LEVEL_COMPLETED"
                     if correct else
                     "step: move on grid; enter goal -> LEVEL_COMPLETED "
                     "(enemy not modelled)"),
        confidence=0.9 if correct else 0.5,
    )
