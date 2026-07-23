"""ArcAgiEnv — adapt the offline `arc_agi` Arcade to the wm `Environment` protocol.

This is the seam that lets the verified world-model loop play real ARC-AGI-3
games. It mirrors exactly how `agents/agentic/solve_loop.py` drives the engine:

    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    env = arc.make(full_game_id)
    raw = env.step(GameAction.RESET, data=..., reasoning={})
    grid   = [arr.tolist() for arr in raw.frame][-1]
    state  = raw.state              # GameState enum
    levels = raw.levels_completed
    actions = [GameAction.from_id(a).name for a in raw.available_actions]

`arc_agi` / `arcengine` are imported lazily so the rest of the wm package (and
its offline tests) never need the game engine installed. Run this on the Mac
where the game files live.
"""

from __future__ import annotations

from typing import Optional

from .core import Action, Frame, Status
from .env import StepResult


class ArcAgiEnv:
    """Wraps one offline arc_agi game as a wm Environment.

    Status mapping (per-attempt, matching the wm vocabulary):
      - GameState.GAME_OVER              -> Status.GAME_OVER
      - GameState.WIN                    -> Status.LEVEL_COMPLETED (whole game done)
      - levels_completed increased       -> Status.LEVEL_COMPLETED (this level cleared)
      - otherwise (NOT_FINISHED)         -> Status.RUNNING
    """

    def __init__(self, game_id_prefix: str):
        self.game_id_prefix = game_id_prefix
        self._arc = None
        self._env = None
        self.full_game_id: Optional[str] = None
        self.available_actions: list[str] = []
        self._prev_levels = 0
        self._GameAction = None  # cached arcengine.GameAction
        self._GameState = None

    # -- lazy engine handles -------------------------------------------------
    def _ensure_engine(self):
        if self._env is not None:
            return
        from arc_agi import Arcade, OperationMode
        from arcengine import GameAction, GameState

        self._GameAction = GameAction
        self._GameState = GameState
        self._arc = Arcade(operation_mode=OperationMode.OFFLINE)
        for e in self._arc.get_environments():
            if e.game_id.startswith(self.game_id_prefix):
                self.full_game_id = e.game_id
                break
        if not self.full_game_id:
            available = [e.game_id for e in self._arc.get_environments()]
            raise ValueError(
                f"game '{self.game_id_prefix}' not found. available: {available}"
            )
        self._env = self._arc.make(self.full_game_id)

    # -- action conversion ---------------------------------------------------
    def _to_game_action(self, action: Action):
        GA = self._GameAction
        ga = getattr(GA, action.name, GA.ACTION5)
        if action.x is not None and action.y is not None:
            ga.set_data({"x": int(action.x), "y": int(action.y)})
        return ga

    def _extract(self, raw) -> StepResult:
        grid: Frame = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
        levels = raw.levels_completed
        gs = self._GameState

        if raw.state is gs.GAME_OVER:
            status = Status.GAME_OVER
        elif raw.state is gs.WIN:
            status = Status.LEVEL_COMPLETED
        elif levels > self._prev_levels:
            status = Status.LEVEL_COMPLETED
        else:
            status = Status.RUNNING
        self._prev_levels = levels

        self.available_actions = [
            self._GameAction.from_id(a).name
            for a in (raw.available_actions or [])
            if self._GameAction.from_id(a).name != "RESET"
        ] or self.available_actions
        return StepResult(frame=grid, status=status, changed_cells=0)

    # -- Environment protocol ------------------------------------------------
    def reset(self) -> Frame:
        self._ensure_engine()
        self._prev_levels = 0
        reset_action = self._GameAction.RESET
        reset_action.reasoning = "wm episode start"
        raw = self._env.step(
            reset_action,
            data=reset_action.action_data.model_dump(),
            reasoning={},
        )
        if raw is None:
            raise RuntimeError("failed to reset game")
        result = self._extract(raw)
        return result.frame

    def step(self, action: Action) -> StepResult:
        ga = self._to_game_action(action)
        ga.reasoning = f"wm: {action}"
        raw = self._env.step(ga, data=ga.action_data.model_dump(), reasoning={})
        if raw is None:
            # Treat a dropped frame as a no-op RUNNING step (loop will re-observe).
            from .core import _copy_frame  # local import to avoid cycle at top
            return StepResult(_copy_frame([]), Status.RUNNING, 0)
        return self._extract(raw)
