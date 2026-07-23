# [Apr 2] tu93 game-specific simulator.
# Built from Claude Code observations during session-002.
#
# Simulator evolution history:
#   v1: graph movement only (L0 solved)
#   v2: enemy horizontal entry → DEAD, vertical entry → SWAP/EAT (L1 solved)
#   v3: sight cone model (L2 attempted, partially correct)
#   v4: TODO — enemy chase behavior on sight detection
#
# Mechanic summary:
#   - 64x64 grid composed of 3x3 block tiles
#   - 0-blocks = nodes, 2-blocks = edges, 5-blocks = walls
#   - Agent (9+4 block) jumps between nodes via edges
#   - Goal (e=14 block): reach it to clear level
#   - Enemy (8+f/b block): has an "eye" (f=15 or b=11 pixel)
#     - Eye offset from block center → sight direction
#     - Entering enemy cell horizontally → DEAD
#     - Entering enemy cell vertically → SWAP (eat enemy, remove it)
#     - Entering enemy's sight node (1 node in eye direction) → DEAD
#   - Bottom bar (value 6) = action counter

"""tu93 simulator: 3x3 block graph maze with sight-cone enemies.

Usage::

    from agents.agentic.simulators.tu93_simulator import Tu93Simulator

    sim = Tu93Simulator.from_grid(grid)
    path = sim.search_bfs(sim.state, lambda s: s.won, max_depth=30)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from agents.agentic.simulator import BaseSimulator, GameState


@dataclass(frozen=True)
class Tu93State:
    """tu93-specific state: agent position + enemy positions (None = eaten)."""
    agent: tuple[int, int]
    enemies: tuple[tuple[int, int] | None, ...]
    goal: tuple[int, int]

    def fingerprint(self) -> tuple:
        return (self.agent, self.enemies)


@dataclass
class EnemyInfo:
    """Enemy with position and eye direction."""
    center: tuple[int, int]
    eye_dir: tuple[int, int] | None  # (dr, dc) relative, e.g. (0, 1) = looking right
    sight_node: tuple[int, int] | None  # the node the enemy can see


class Tu93Simulator(BaseSimulator):
    """Game-specific simulator for tu93.

    Operates on a graph of 3x3 block nodes connected by 2-block edges.
    Supports multiple enemies with sight cones and SWAP/EAT mechanics.
    """

    def __init__(
        self,
        adj: dict[tuple, dict[str, tuple]],
        enemy_infos: list[EnemyInfo],
        goal: tuple[int, int],
        available_actions: list[str] | None = None,
    ):
        super().__init__(available_actions)
        self.adj = adj              # node → {action_short → neighbor_node}
        self.enemy_infos = enemy_infos
        self.goal_pos = goal
        self.avg_confidence = 0.8

    @classmethod
    def from_grid(cls, grid: list[list[int]]) -> Tu93Simulator:
        """Parse a tu93 grid into a simulator instance."""
        nodes, adj, block_vals = _parse_graph(grid)

        agent = None
        goal = None
        enemy_infos = []

        for center, ntype in nodes.items():
            if ntype == "agent":
                agent = center
            elif ntype == "goal":
                goal = center
            elif ntype == "enemy":
                eye = _get_eye_dir(center, block_vals)
                sight = _get_sight_node(center, eye, adj) if eye else None
                enemy_infos.append(EnemyInfo(center=center, eye_dir=eye, sight_node=sight))

        sim = cls(
            adj=adj,
            enemy_infos=enemy_infos,
            goal=goal or (0, 0),
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
        )
        sim._agent_start = agent
        sim._nodes = nodes
        sim._block_vals = block_vals
        return sim

    def initial_state(self) -> Tu93State:
        enemies = tuple(ei.center for ei in self.enemy_infos)
        return Tu93State(
            agent=self._agent_start,
            enemies=enemies,
            goal=self.goal_pos,
        )

    def predict(self, state: GameState, action: str) -> tuple[GameState, float]:
        """Adapter for BaseSimulator interface. Wraps Tu93State."""
        # This method exists for compatibility with BaseSimulator.search_bfs
        # which expects GameState. We store Tu93State inside GameState.entities.
        raise NotImplementedError("Use predict_tu93() or search_tu93() directly.")

    def predict_tu93(
        self,
        state: Tu93State,
        action: str,
    ) -> tuple[Tu93State, bool, float]:
        """Predict next state. Returns (new_state, alive, confidence).

        Rules (v3 — sight cone + eat):
        1. Agent moves to next node via graph edge
        2. If agent enters enemy cell vertically → EAT (remove enemy)
        3. If agent enters enemy cell horizontally → DEAD
        4. If agent enters enemy's sight node → DEAD
        5. Otherwise enemies don't move
        """
        a = "A" + action[-1]
        new_agent = self.adj.get(state.agent, {}).get(a, state.agent)
        enemies = list(state.enemies)

        # No movement
        if new_agent == state.agent:
            return Tu93State(new_agent, tuple(enemies), state.goal), True, 0.9

        # Check each enemy
        for i, en in enumerate(enemies):
            if en is None:
                continue

            # Direct entry to enemy cell
            if new_agent == en:
                if a in ("A1", "A2"):
                    # Vertical approach → EAT (remove enemy)
                    enemies[i] = None
                    return Tu93State(new_agent, tuple(enemies), state.goal), True, 0.8
                else:
                    # Horizontal approach → DEAD
                    return Tu93State(new_agent, tuple(enemies), state.goal), False, 0.9

            # Sight cone check
            sight = self._get_enemy_sight(i, enemies)
            if sight and new_agent == sight:
                return Tu93State(new_agent, tuple(enemies), state.goal), False, 0.7

        return Tu93State(new_agent, tuple(enemies), state.goal), True, 0.9

    def _get_enemy_sight(self, idx: int, current_enemies: list) -> tuple[int, int] | None:
        """Get the sight node for enemy at index idx, using current position."""
        if idx >= len(self.enemy_infos):
            return None
        info = self.enemy_infos[idx]
        en_pos = current_enemies[idx]
        if en_pos is None or info.eye_dir is None:
            return None
        # Compute sight node from current position + eye direction
        return _get_sight_node(en_pos, info.eye_dir, self.adj)

    def search_tu93(
        self,
        state: Tu93State,
        max_depth: int = 40,
    ) -> list[str] | None:
        """BFS over Tu93State to find path to goal."""
        visited: set[tuple] = {state.fingerprint()}
        queue: deque[tuple[Tu93State, list[str]]] = deque([(state, [])])

        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue

            for action in self.available_actions:
                next_state, alive, conf = self.predict_tu93(current, action)

                if not alive:
                    continue

                if next_state.agent == next_state.goal:
                    return path + [action]

                fp = next_state.fingerprint()
                if fp not in visited:
                    visited.add(fp)
                    queue.append((next_state, path + [action]))

        return None


# ===================================================================
# Grid parsing utilities (tu93-specific)
# ===================================================================


def _parse_graph(
    grid: list[list[int]],
) -> tuple[dict, dict, dict]:
    """Parse tu93 grid into graph structure.

    Returns:
        nodes: {center → type} where type is 'agent'|'goal'|'enemy'|'node'
        adj: {center → {'A1': neighbor, 'A2': neighbor, ...}}
        block_vals: {center → [(val, dr, dc), ...]} raw block data
    """
    non_bg = [
        (r, c)
        for r, row in enumerate(grid)
        for c, v in enumerate(row)
        if v not in (5, 6)
    ]
    if not non_bg:
        return {}, {}, {}

    min_r = min(r for r, c in non_bg)
    min_c = min(c for r, c in non_bg)

    nodes: dict[tuple, str] = {}
    conns: set[tuple] = set()
    block_vals: dict[tuple, list] = {}

    for ri in range(22):
        for ci in range(22):
            r = min_r + ri * 3
            c = min_c + ci * 3
            if r + 2 >= 64 or c + 2 >= 64:
                continue

            cells = [
                (grid[r + dr][c + dc], dr, dc)
                for dr in range(3)
                for dc in range(3)
            ]
            vals = set(v for v, _, _ in cells)
            center = (r + 1, c + 1)
            block_vals[center] = cells

            if vals <= {5, 6}:
                continue
            elif vals == {2}:
                conns.add(center)
            elif 4 in vals:
                nodes[center] = "agent"
            elif 14 in vals and len(vals) == 1:
                nodes[center] = "goal"
            elif 8 in vals or 15 in vals:
                nodes[center] = "enemy"
            elif vals == {0}:
                nodes[center] = "node"

    # Build adjacency
    adj: dict[tuple, dict[str, tuple]] = {}
    for nc in nodes:
        adj[nc] = {}
        for dr, dc, a in [(-3, 0, "A1"), (3, 0, "A2"), (0, -3, "A3"), (0, 3, "A4")]:
            r, c = nc[0] + dr, nc[1] + dc
            while (r, c) in conns:
                r += dr
                c += dc
            if (r, c) in nodes:
                adj[nc][a] = (r, c)

    return nodes, adj, block_vals


def _get_eye_dir(
    center: tuple[int, int],
    block_vals: dict[tuple, list],
) -> tuple[int, int] | None:
    """Find the eye direction of an enemy block.

    The eye is the f(15) or b(11) pixel within the 3x3 block.
    Its offset from block center (1,1) gives the sight direction.
    """
    for val, dr, dc in block_vals.get(center, []):
        if val in (15, 11):
            return (dr - 1, dc - 1)
    return None


def _get_sight_node(
    enemy_center: tuple[int, int],
    eye_dir: tuple[int, int] | None,
    adj: dict[tuple, dict[str, tuple]],
) -> tuple[int, int] | None:
    """Get the node that the enemy can see (1 hop in eye direction)."""
    if not eye_dir:
        return None
    dr, dc = eye_dir
    action_map = {
        (-1, 0): "A1",  # up
        (1, 0): "A2",   # down
        (0, -1): "A3",  # left
        (0, 1): "A4",   # right
    }
    a = action_map.get((dr, dc))
    if not a:
        return None
    return adj.get(enemy_center, {}).get(a)
