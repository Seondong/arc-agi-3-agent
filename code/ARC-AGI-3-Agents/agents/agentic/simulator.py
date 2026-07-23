# [Apr 2] Observation-based executable simulator for ARC-AGI-3.
# Created by SD with Claude Opus 4.6.
#
# Transforms DynamicsRules (natural language hypotheses with confidence)
# into a runnable simulate(state, action) → next_state function.
# Supports BFS planning over the simulator and tracks evolution history.

"""Simulator module: build, run, search, and evolve game simulators
from observed dynamics rules.

The simulator is a probabilistic belief system:
- Each mechanic carries a confidence score
- Predictions include confidence estimates
- BFS can filter by minimum confidence (safe planning)
- Evolution is logged for SFT data generation

Usage::

    from agents.agentic.simulator import SimulatorBuilder, Simulator

    builder = SimulatorBuilder()
    sim = builder.build_from_belief(belief_ledger, perceived_objects, grid)
    plan = sim.search_bfs(current_state, goal_test, max_depth=15)
"""

from __future__ import annotations

import copy
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from .schemas import (
    BeliefLedger,
    DynamicsRule,
    InteractionRule,
    SimulatorEvolutionEntry,
    SimulatorSnapshot,
)

logger = logging.getLogger(__name__)


# ===================================================================
# Core data structures
# ===================================================================


@dataclass(frozen=True)
class EntityState:
    """Position and identity of one entity."""
    pid: str                # persistent object ID
    row: int
    col: int
    role: str = ""          # "agent" | "enemy" | "goal" | "wall" | "block" | ""
    value: int = -1         # grid color value


@dataclass
class GameState:
    """Abstract game state tracked by the simulator."""
    entities: dict[str, EntityState] = field(default_factory=dict)
    walls: set[tuple[int, int]] = field(default_factory=set)
    paths: set[tuple[int, int]] = field(default_factory=set)
    grid_rows: int = 64
    grid_cols: int = 64
    level: int = 0
    step: int = 0
    alive: bool = True
    won: bool = False

    def agent(self) -> EntityState | None:
        for e in self.entities.values():
            if e.role == "agent":
                return e
        return None

    def goal(self) -> EntityState | None:
        for e in self.entities.values():
            if e.role == "goal":
                return e
        return None

    def enemies(self) -> list[EntityState]:
        return [e for e in self.entities.values() if e.role == "enemy"]

    def clone(self) -> GameState:
        return GameState(
            entities=dict(self.entities),
            walls=set(self.walls),
            paths=set(self.paths),
            grid_rows=self.grid_rows,
            grid_cols=self.grid_cols,
            level=self.level,
            step=self.step + 1,
            alive=self.alive,
            won=self.won,
        )

    def fingerprint(self) -> tuple:
        """Hashable state for BFS visited set."""
        ents = tuple(sorted(
            (e.pid, e.row, e.col) for e in self.entities.values()
        ))
        return (ents, self.level, self.alive)


# ===================================================================
# Mechanic rules (executable)
# ===================================================================


@dataclass
class MechanicRule:
    """An executable rule derived from a DynamicsRule or InteractionRule."""
    rule_id: str
    action: str | None = None           # None = passive rule
    description: str = ""
    confidence: float = 0.5
    times_verified: int = 0
    times_violated: int = 0
    source_rule_ids: list[str] = field(default_factory=list)
    # The actual logic
    condition_fn: Callable[[GameState, str], bool] | None = None
    effect_fn: Callable[[GameState, str], GameState] | None = None

    def applies(self, state: GameState, action: str) -> bool:
        if self.condition_fn is None:
            return False
        if self.action and self.action != action:
            return False
        return self.condition_fn(state, action)

    def apply(self, state: GameState, action: str) -> GameState:
        if self.effect_fn is None:
            return state
        return self.effect_fn(state, action)

    def summary(self) -> str:
        act = self.action or "passive"
        return f"{act}→{self.description} (conf:{self.confidence:.2f}, v:{self.times_verified})"


# ===================================================================
# Pattern-matched rule builders
# ===================================================================

# Direction deltas for common movement patterns
DIRECTION_DELTAS: dict[str, tuple[int, int]] = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}

# Action-to-direction mapping (common defaults, overridden per game)
DEFAULT_ACTION_DIRECTIONS: dict[str, str] = {
    "ACTION1": "up",
    "ACTION2": "down",
    "ACTION3": "left",
    "ACTION4": "right",
}


def _parse_direction_from_text(text: str) -> str | None:
    """Extract direction keyword from natural language rule text."""
    text_lower = text.lower()
    for direction in ["up", "down", "left", "right"]:
        if direction in text_lower:
            return direction
    return None


def _parse_move_distance(text: str) -> int:
    """Extract movement distance from text like 'moves 3 cells'."""
    m = re.search(r"(\d+)\s*(cell|pixel|step|block|node|unit)", text.lower())
    if m:
        return int(m.group(1))
    return 1  # default 1 cell


def build_movement_rule(
    rule: DynamicsRule,
    direction: str,
    distance: int = 1,
) -> MechanicRule:
    """Build a movement mechanic: agent moves in a direction."""
    dr, dc = DIRECTION_DELTAS[direction]
    dr *= distance
    dc *= distance

    def condition(state: GameState, action: str) -> bool:
        return state.agent() is not None

    def effect(state: GameState, action: str) -> GameState:
        new_state = state.clone()
        ag = state.agent()
        if ag is None:
            return new_state
        new_row = ag.row + dr
        new_col = ag.col + dc
        # Wall collision check
        if (new_row, new_col) in state.walls:
            return new_state  # blocked, no movement
        # Boundary check
        if not (0 <= new_row < state.grid_rows and 0 <= new_col < state.grid_cols):
            return new_state
        new_state.entities[ag.pid] = EntityState(
            pid=ag.pid, row=new_row, col=new_col,
            role=ag.role, value=ag.value,
        )
        return new_state

    return MechanicRule(
        rule_id=f"move_{rule.rule_id}",
        action=rule.action_name,
        description=f"move_{direction}_{distance}",
        confidence=rule.confidence,
        times_verified=rule.times_verified,
        times_violated=rule.times_violated,
        source_rule_ids=[rule.rule_id],
        condition_fn=condition,
        effect_fn=effect,
    )


def build_collision_death_rule(rule_id: str = "collision_death") -> MechanicRule:
    """Agent dies when overlapping with an enemy."""
    def condition(state: GameState, action: str) -> bool:
        ag = state.agent()
        if ag is None:
            return False
        return any(e.row == ag.row and e.col == ag.col for e in state.enemies())

    def effect(state: GameState, action: str) -> GameState:
        new_state = state.clone()
        new_state.alive = False
        return new_state

    return MechanicRule(
        rule_id=rule_id,
        action=None,  # passive rule, checked after every action
        description="collision_with_enemy_kills",
        confidence=1.0,
        condition_fn=condition,
        effect_fn=effect,
    )


def build_goal_reached_rule(rule_id: str = "goal_reached") -> MechanicRule:
    """Agent wins when overlapping with goal."""
    def condition(state: GameState, action: str) -> bool:
        ag = state.agent()
        gl = state.goal()
        if ag is None or gl is None:
            return False
        return ag.row == gl.row and ag.col == gl.col

    def effect(state: GameState, action: str) -> GameState:
        new_state = state.clone()
        new_state.won = True
        return new_state

    return MechanicRule(
        rule_id=rule_id,
        action=None,
        description="agent_reaches_goal_wins",
        confidence=0.9,
        condition_fn=condition,
        effect_fn=effect,
    )


def build_enemy_mirror_rule(
    rule: DynamicsRule | InteractionRule,
    axis: str = "horizontal",
) -> MechanicRule:
    """Enemy mirrors agent movement on shared axis."""
    opposite = {"ACTION1": "ACTION2", "ACTION2": "ACTION1",
                "ACTION3": "ACTION4", "ACTION4": "ACTION3"}

    def condition(state: GameState, action: str) -> bool:
        ag = state.agent()
        enemies = state.enemies()
        if ag is None or not enemies:
            return False
        for enemy in enemies:
            if axis == "horizontal" and ag.row == enemy.row:
                return action in ("ACTION3", "ACTION4")
            if axis == "vertical" and ag.col == enemy.col:
                return action in ("ACTION1", "ACTION2")
        return False

    def effect(state: GameState, action: str) -> GameState:
        new_state = state.clone()
        ag = state.agent()
        if ag is None:
            return new_state
        opp = opposite.get(action, action)
        opp_dir = DEFAULT_ACTION_DIRECTIONS.get(opp)
        if not opp_dir:
            return new_state
        dr, dc = DIRECTION_DELTAS[opp_dir]
        for enemy in state.enemies():
            should_move = False
            if axis == "horizontal" and ag.row == enemy.row:
                should_move = True
            elif axis == "vertical" and ag.col == enemy.col:
                should_move = True
            if should_move:
                new_row = enemy.row + dr
                new_col = enemy.col + dc
                if (new_row, new_col) not in state.walls:
                    new_state.entities[enemy.pid] = EntityState(
                        pid=enemy.pid, row=new_row, col=new_col,
                        role=enemy.role, value=enemy.value,
                    )
        return new_state

    rule_id_str = getattr(rule, "rule_id", "enemy_mirror")
    return MechanicRule(
        rule_id=f"mirror_{rule_id_str}",
        action=None,  # applies to multiple actions
        description=f"enemy_mirrors_{axis}",
        confidence=getattr(rule, "confidence", 0.5),
        times_verified=getattr(rule, "times_verified", 0),
        times_violated=getattr(rule, "times_violated", 0),
        source_rule_ids=[rule_id_str],
        condition_fn=condition,
        effect_fn=effect,
    )


# ===================================================================
# Rule conversion: DynamicsRule (NL) → MechanicRule (callable)
# ===================================================================

# Keywords that indicate mechanic types in rule text
MOVEMENT_KEYWORDS = ["move", "shift", "slide", "jump", "walk", "push", "displace"]
COLLISION_KEYWORDS = ["collide", "collision", "die", "kill", "death", "game_over", "game over"]
GOAL_KEYWORDS = ["win", "goal", "reach", "arrive", "complete", "level_up", "level up"]
MIRROR_KEYWORDS = ["mirror", "opposite", "reverse", "follow", "chase", "copy"]
TOGGLE_KEYWORDS = ["toggle", "switch", "flip", "on/off", "activate"]


def convert_dynamics_rule(rule: DynamicsRule) -> MechanicRule | None:
    """Convert a natural-language DynamicsRule to an executable MechanicRule.

    Uses pattern matching on common keywords. Returns None if the rule
    cannot be converted (unknown pattern).
    """
    text = f"{rule.condition} {rule.effect}".lower()

    # Movement rule
    if any(kw in text for kw in MOVEMENT_KEYWORDS):
        # Priority: action_name → text direction
        # The NL text often has wrong directions (e.g., "left" when it means "down")
        # because it's auto-generated from diff analysis. The action_name is more reliable.
        direction = None
        if rule.action_name:
            direction = DEFAULT_ACTION_DIRECTIONS.get(rule.action_name)
        if direction is None:
            direction = _parse_direction_from_text(text)
        if direction:
            distance = _parse_move_distance(text)
            return build_movement_rule(rule, direction, distance)

    # Collision/death rule
    if any(kw in text for kw in COLLISION_KEYWORDS):
        return MechanicRule(
            rule_id=f"death_{rule.rule_id}",
            action=rule.action_name,
            description="collision_or_death",
            confidence=rule.confidence,
            source_rule_ids=[rule.rule_id],
            condition_fn=build_collision_death_rule().condition_fn,
            effect_fn=build_collision_death_rule().effect_fn,
        )

    # Goal/win rule
    if any(kw in text for kw in GOAL_KEYWORDS):
        return MechanicRule(
            rule_id=f"goal_{rule.rule_id}",
            action=rule.action_name,
            description="goal_reached",
            confidence=rule.confidence,
            source_rule_ids=[rule.rule_id],
            condition_fn=build_goal_reached_rule().condition_fn,
            effect_fn=build_goal_reached_rule().effect_fn,
        )

    # Mirror/enemy behavior
    if any(kw in text for kw in MIRROR_KEYWORDS):
        axis = "horizontal" if any(w in text for w in ["row", "horizontal"]) else "vertical"
        return build_enemy_mirror_rule(rule, axis)

    logger.debug("Could not convert DynamicsRule %s: '%s %s'", rule.rule_id, rule.condition, rule.effect)
    return None


def convert_interaction_rule(rule: InteractionRule) -> MechanicRule | None:
    """Convert an InteractionRule to an executable MechanicRule."""
    text = f"{rule.rule_type} {rule.effect}".lower()

    if any(kw in text for kw in MIRROR_KEYWORDS):
        axis = "horizontal" if any(w in text for w in ["row", "horizontal"]) else "vertical"
        return build_enemy_mirror_rule(rule, axis)

    if any(kw in text for kw in COLLISION_KEYWORDS):
        return MechanicRule(
            rule_id=f"interact_death_{rule.rule_id}",
            description="interaction_death",
            confidence=rule.confidence,
            source_rule_ids=[rule.rule_id],
            condition_fn=build_collision_death_rule().condition_fn,
            effect_fn=build_collision_death_rule().effect_fn,
        )

    return None


# ===================================================================
# Simulator: predict + search
# ===================================================================


class BaseSimulator:
    """Abstract base for all simulators (game-specific or rule-based).

    Subclasses must implement predict(). BFS search is inherited for free.
    Game-specific simulators (e.g., tu93_simulator) override predict()
    with game-specific logic discovered from observations.
    """

    def __init__(self, available_actions: list[str] | None = None):
        self.available_actions = available_actions or ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]
        self.version = 0
        # avg_confidence is set by subclasses: Simulator exposes it via
        # @property (computed from mechanics); Tu93Simulator sets it as a
        # plain attribute. Setting it here would clash with the property.

    def predict(self, state: GameState, action: str) -> tuple[GameState, float]:
        """Predict next state. Must be overridden by subclasses.

        Returns (new_state, confidence).
        """
        raise NotImplementedError

    def snapshot(self, step: int, trigger: str = "initial") -> SimulatorSnapshot:
        return SimulatorSnapshot(
            version=self.version,
            step_created=step,
            mechanic_count=0,
            mechanics_summary=[],
            avg_confidence=self.avg_confidence,
            trigger=trigger,
        )

    def search_bfs(
        self,
        state: GameState,
        goal_test: Callable[[GameState], bool],
        max_depth: int = 15,
    ) -> list[str] | None:
        """BFS over simulator to find shortest action sequence to goal."""
        visited: set[tuple] = {state.fingerprint()}
        queue: deque[tuple[GameState, list[str]]] = deque([(state, [])])

        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue

            for action in self.available_actions:
                next_state, conf = self.predict(current, action)

                if not next_state.alive:
                    continue

                if goal_test(next_state):
                    return path + [action]

                fp = next_state.fingerprint()
                if fp not in visited:
                    visited.add(fp)
                    queue.append((next_state, path + [action]))

        return None

    def search_safe_bfs(
        self,
        state: GameState,
        goal_test: Callable[[GameState], bool],
        min_confidence: float = 0.7,
        max_depth: int = 15,
    ) -> list[str] | None:
        """BFS that only follows paths through high-confidence predictions."""
        visited: set[tuple] = {state.fingerprint()}
        queue: deque[tuple[GameState, list[str], float]] = deque(
            [(state, [], 1.0)]
        )

        while queue:
            current, path, path_conf = queue.popleft()
            if len(path) >= max_depth:
                continue

            for action in self.available_actions:
                next_state, step_conf = self.predict(current, action)

                if not next_state.alive:
                    continue

                new_path_conf = min(path_conf, step_conf)
                if new_path_conf < min_confidence:
                    continue

                if goal_test(next_state):
                    return path + [action]

                fp = next_state.fingerprint()
                if fp not in visited:
                    visited.add(fp)
                    queue.append((next_state, path + [action], new_path_conf))

        return None


class Simulator(BaseSimulator):
    """Rule-based simulator using MechanicRule pattern matching.

    This is the default simulator built by SimulatorBuilder from
    DynamicsRules. For game-specific simulators with custom logic,
    subclass BaseSimulator directly (see simulators/ directory).
    """

    def __init__(
        self,
        mechanics: list[MechanicRule],
        available_actions: list[str] | None = None,
    ):
        super().__init__(available_actions)
        self.mechanics = mechanics
        self._history: list[SimulatorSnapshot] = []

    @property
    def avg_confidence(self) -> float:
        if not self.mechanics:
            return 0.0
        return sum(m.confidence for m in self.mechanics) / len(self.mechanics)

    def snapshot(self, step: int, trigger: str = "initial") -> SimulatorSnapshot:
        return SimulatorSnapshot(
            version=self.version,
            step_created=step,
            mechanic_count=len(self.mechanics),
            mechanics_summary=[m.summary() for m in self.mechanics],
            avg_confidence=self.avg_confidence,
            trigger=trigger,
        )

    def predict(self, state: GameState, action: str) -> tuple[GameState, float]:
        """Predict by applying MechanicRules in order."""
        new_state = state.clone()
        min_conf = 1.0
        applied = False

        for rule in self.mechanics:
            if rule.action and rule.applies(new_state, action):
                new_state = rule.apply(new_state, action)
                min_conf = min(min_conf, rule.confidence)
                applied = True

        for rule in self.mechanics:
            if rule.action is None and rule.applies(new_state, action):
                new_state = rule.apply(new_state, action)
                min_conf = min(min_conf, rule.confidence)
                applied = True

        if not applied:
            min_conf = 0.1

        return new_state, min_conf


# ===================================================================
# SimulatorBuilder: belief → simulator
# ===================================================================


class SimulatorBuilder:
    """Constructs a Simulator from the current BeliefLedger and perception."""

    def build_from_belief(
        self,
        belief: BeliefLedger,
        objects: list[Any] | None = None,
        grid: list[list[int]] | None = None,
        available_actions: list[str] | None = None,
    ) -> Simulator:
        """Build a simulator from current belief state.

        Steps:
        1. Convert DynamicsRules → MechanicRules via pattern matching
        2. Convert InteractionRules → MechanicRules
        3. Add default passive rules (collision, goal)
        4. Return configured Simulator
        """
        mechanics: list[MechanicRule] = []
        converted_ids: set[str] = set()

        # Convert dynamics rules
        for rule in belief.dynamics_rules:
            mechanic = convert_dynamics_rule(rule)
            if mechanic:
                mechanics.append(mechanic)
                converted_ids.add(rule.rule_id)
            else:
                logger.debug("Skipped unconvertible DynamicsRule: %s", rule.rule_id)

        # Convert interaction rules
        for rule in belief.interaction_rules:
            mechanic = convert_interaction_rule(rule)
            if mechanic:
                mechanics.append(mechanic)

        # Add default passive rules if not already covered
        has_collision = any("death" in m.rule_id or "collision" in m.rule_id for m in mechanics)
        has_goal = any("goal" in m.rule_id for m in mechanics)

        if not has_collision:
            mechanics.append(build_collision_death_rule())
        if not has_goal:
            mechanics.append(build_goal_reached_rule())

        sim = Simulator(
            mechanics=mechanics,
            available_actions=available_actions,
        )

        logger.info(
            "Built simulator v%d: %d mechanics (avg conf %.2f), %d rules skipped",
            sim.version, len(mechanics), sim.avg_confidence,
            len(belief.dynamics_rules) - len(converted_ids),
        )
        return sim

    def build_initial_state(
        self,
        objects: list[Any],
        grid: list[list[int]] | None = None,
    ) -> GameState:
        """Build initial GameState from perceived objects."""
        entities: dict[str, EntityState] = {}
        walls: set[tuple[int, int]] = set()

        for obj in objects:
            pid = getattr(obj, "persistent_id", None) or str(id(obj))
            row = (getattr(obj, "row_min", 0) + getattr(obj, "row_max", 0)) // 2
            col = (getattr(obj, "col_min", 0) + getattr(obj, "col_max", 0)) // 2
            value = getattr(obj, "value", -1)

            # Determine role from perception scores
            role = ""
            ctrl = getattr(obj, "controllable_score", 0)
            goal = getattr(obj, "goal_score", 0)
            block = getattr(obj, "blocker_score", 0)

            if ctrl >= 0.3:
                role = "agent"
            elif goal >= 0.4:
                role = "goal"
            elif block >= 0.5:
                role = "wall"

            entities[pid] = EntityState(
                pid=pid, row=row, col=col, role=role, value=value,
            )

        rows = len(grid) if grid else 64
        cols = len(grid[0]) if grid and grid[0] else 64

        return GameState(
            entities=entities,
            walls=walls,
            grid_rows=rows,
            grid_cols=cols,
        )

    def update_from_surprise(
        self,
        simulator: Simulator,
        step_index: int,
        prediction_summary: str,
        actual_summary: str,
        new_dynamics: list[DynamicsRule] | None = None,
        new_interactions: list[InteractionRule] | None = None,
    ) -> tuple[Simulator, SimulatorEvolutionEntry]:
        """Update simulator based on prediction failure.

        Returns updated simulator and an evolution log entry.
        """
        old_version = simulator.version
        rules_added: list[str] = []
        rules_modified: list[str] = []
        rules_removed: list[str] = []
        conf_changes: dict[str, list[float]] = {}

        # Decrease confidence of rules that may have caused the wrong prediction
        for m in simulator.mechanics:
            if m.confidence > 0.1:
                old_conf = m.confidence
                m.confidence *= 0.85  # decay on failure
                m.times_violated += 1
                conf_changes[m.rule_id] = [old_conf, m.confidence]
                rules_modified.append(m.rule_id)

        # Add ONLY genuinely new rules (avoid duplication)
        existing_source_ids: set[str] = set()
        for m in simulator.mechanics:
            existing_source_ids.update(m.source_rule_ids)

        if new_dynamics:
            for rule in new_dynamics:
                if rule.rule_id in existing_source_ids:
                    # Rule already exists — update confidence of existing mechanic instead
                    for m in simulator.mechanics:
                        if rule.rule_id in m.source_rule_ids:
                            m.confidence = max(m.confidence, rule.confidence)
                    continue
                mechanic = convert_dynamics_rule(rule)
                if mechanic:
                    simulator.mechanics.append(mechanic)
                    rules_added.append(mechanic.rule_id)
                    existing_source_ids.add(rule.rule_id)

        if new_interactions:
            for rule in new_interactions:
                if rule.rule_id in existing_source_ids:
                    for m in simulator.mechanics:
                        if rule.rule_id in m.source_rule_ids:
                            m.confidence = max(m.confidence, rule.confidence)
                    continue
                mechanic = convert_interaction_rule(rule)
                if mechanic:
                    simulator.mechanics.append(mechanic)
                    rules_added.append(mechanic.rule_id)
                    existing_source_ids.add(rule.rule_id)

        # Remove rules with very low confidence
        before_count = len(simulator.mechanics)
        simulator.mechanics = [m for m in simulator.mechanics if m.confidence > 0.05]
        removed_count = before_count - len(simulator.mechanics)
        if removed_count > 0:
            rules_removed.append(f"{removed_count}_low_confidence_rules")

        simulator.version += 1

        entry = SimulatorEvolutionEntry(
            step_index=step_index,
            version_before=old_version,
            version_after=simulator.version,
            trigger="surprise_update",
            rules_added=rules_added,
            rules_modified=rules_modified,
            rules_removed=rules_removed,
            prediction_that_failed=prediction_summary,
            actual_observation=actual_summary,
            confidence_changes=conf_changes,
        )

        logger.info(
            "Simulator updated v%d→v%d: +%d -%d ~%d rules",
            old_version, simulator.version,
            len(rules_added), removed_count, len(rules_modified),
        )
        return simulator, entry

    def confirm_prediction(self, simulator: Simulator) -> None:
        """Increase confidence of all rules when prediction was correct."""
        for m in simulator.mechanics:
            m.times_verified += 1
            m.confidence = min(1.0, m.confidence * 1.05 + 0.01)
