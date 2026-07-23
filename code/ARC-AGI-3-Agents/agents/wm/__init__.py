"""wm — verified executable world-model solve core for ARC-AGI-3.

This package rebuilds the "heart" that the earlier agentic framework never had:
a persistent, executable world model (`step(state, action)`) that is
**verified against the full recorded interaction history** (`run_backtest`) and
**planned inside for free** (`run_bfs`). It mirrors the shape proven by the
publicly released Schema and Baseline1 harnesses, while emitting traces in the
project's own `data-logging-principles` schema so every episode doubles as
distillation data.

Design axes (see README.md):
  - Timeline  : append-only ground-truth history of real transitions.
  - WorldModel: brain-authored reconstruct / step / render / is_goal callables.
  - backtest  : replay every recorded transition; exact match or a pointed bug.
  - planner   : BFS inside a certified model, zero environment cost.
  - Brain     : pluggable author of the world model (ClaudeBrain | CallableBrain).
  - SolveLoop : observe -> deliberate (theorize -> certify -> plan) -> execute -> record.
"""

from .core import Action, Frame, Status, Transition, Timeline, WorldModel
from .backtest import BacktestReport, Mismatch, run_backtest
from .planner import Plan, run_bfs

__all__ = [
    "Action",
    "Frame",
    "Status",
    "Transition",
    "Timeline",
    "WorldModel",
    "BacktestReport",
    "Mismatch",
    "run_backtest",
    "Plan",
    "run_bfs",
]
