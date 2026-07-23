"""run_bfs — plan inside a certified world model, at zero environment cost.

Once `run_backtest` is green, the model IS a simulator: searching it spends no
real actions. This is where the RHAE win comes from — the agent pays real
actions once to discover a mechanic, then recomputes plans for free on every
later level. Breadth-first search returns the shortest action sequence to a goal
state; it is deliberately simple and swappable (A*/beam/MCTS later).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .core import Action, State, Status, WorldModel


@dataclass
class Plan:
    """Result of searching inside the model."""

    actions: list[Action] = field(default_factory=list)
    found: bool = False
    nodes_expanded: int = 0
    exhausted: bool = False  # searched the whole reachable space, no goal
    hit_limit: bool = False  # stopped on depth/node budget

    def __len__(self) -> int:
        return len(self.actions)

    def summary(self) -> str:
        if self.found:
            return f"plan {len(self.actions)} actions (expanded {self.nodes_expanded})"
        if self.exhausted:
            return f"no plan: goal unreachable in model (expanded {self.nodes_expanded})"
        return f"no plan: hit search budget (expanded {self.nodes_expanded})"


def run_bfs(
    model: WorldModel,
    start_state: State,
    available_actions: list[Action],
    *,
    max_depth: int = 60,
    max_nodes: int = 200_000,
) -> Plan:
    """Breadth-first search for the shortest action list reaching a goal state.

    Successors that the model predicts as GAME_OVER are pruned (we never plan
    through death). LEVEL_COMPLETED or `is_goal` ends the search.
    """
    if model.is_goal(start_state):
        return Plan(actions=[], found=True, nodes_expanded=0)

    start_key = model.fingerprint(start_state)
    visited = {start_key}
    queue: deque[tuple[State, list[Action]]] = deque([(start_state, [])])
    expanded = 0

    while queue:
        state, path = queue.popleft()
        if len(path) >= max_depth:
            continue
        expanded += 1
        if expanded > max_nodes:
            return Plan(actions=[], found=False, nodes_expanded=expanded,
                        hit_limit=True)

        for action in available_actions:
            try:
                nxt, status = model.step(state, action)
            except Exception:  # noqa: BLE001 - a step that throws is just a dead branch
                continue

            if status == Status.GAME_OVER:
                continue

            if status == Status.LEVEL_COMPLETED or model.is_goal(nxt):
                return Plan(actions=path + [action], found=True,
                            nodes_expanded=expanded)

            key = model.fingerprint(nxt)
            if key not in visited:
                visited.add(key)
                queue.append((nxt, path + [action]))

    return Plan(actions=[], found=False, nodes_expanded=expanded, exhausted=True)
