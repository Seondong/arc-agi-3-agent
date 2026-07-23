# [Mar 30] Agentic Solve Loop for ARC-AGI-3.
# Created by SD with Claude Opus 4.6.
# [Mar 31] Updated by SD with GPT-5.4.

"""Core solve loop that orchestrates one game episode using the full
agentic infrastructure: perception, experiment designer, phase manager,
surprise auditor, belief ledger, and episode memory.

This is the "brain" that ties everything together to actually score points.

Usage::

    # As a library
    from agents.agentic.solve_loop import solve_episode
    result = solve_episode("sk48", max_steps=100)

    # CLI
    uv run python -m agents.agentic.solve_loop --game sk48 --max-steps 100
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import FrameData, GameAction, GameState

from agents.grid_lib import (
    CHAR_MAP,
    compress_grid,
    compute_diff,
    diff_cell_count,
    map2d,
)
from agents.agentic.perception import (
    PersistentObjectTracker,
    PerceivedObject,
    RoleScorer,
    run_perception,
)
from agents.agentic.experiment_designer import (
    ExperimentDesigner,
    ProbeFamily,
    ProbeHistory,
)
from agents.agentic.phase_manager import (
    PhaseManager,
    PhaseState,
    exploration_guidance,
)
from agents.agentic.surprise_auditor import (
    AntiAnchoringGuard,
    PredictedChange,
    SurpriseReport,
    SurpriseSeverity,
    audit_step,
)
from agents.agentic.memory import (
    EpisodeMemoryStore,
    TrajectoryCurator,
    bootstrap_belief_ledger,
)
from agents.agentic.bootstrap_reasoner import (
    ProbeSuggestion,
    infer_bootstrap_motifs,
    reassess_motifs_from_effects,
)
from agents.agentic.schemas import (
    BeliefLedger,
    BeliefDiffSummary,
    DecisionRecord,
    GoalBelief,
    HypothesisEntry,
    MotifBelief,
    ObjectSummary,
    ObservationSnapshot,
    SimulatorEvolutionEntry,
    Subgoal,
    TrajectoryRecord,
)
from agents.agentic.simulator import (
    Simulator,
    SimulatorBuilder,
)

logger = logging.getLogger(__name__)

# ===================================================================
# Action name <-> GameAction mapping
# ===================================================================

_ACTION_NAME_MAP: dict[str, GameAction] = {
    "ACTION1": GameAction.ACTION1,
    "ACTION2": GameAction.ACTION2,
    "ACTION3": GameAction.ACTION3,
    "ACTION4": GameAction.ACTION4,
    "ACTION5": GameAction.ACTION5,
    "ACTION6": GameAction.ACTION6,
    "ACTION7": GameAction.ACTION7 if hasattr(GameAction, "ACTION7") else GameAction.ACTION5,
    "RESET": GameAction.RESET,
}

_SIMPLE_ACTIONS = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7"}


def _resolve_action(action_spec: Any) -> tuple[GameAction, dict[str, Any]]:
    """Convert a probe action spec (string, dict, or ProbeSuggestion) to GameAction + data."""
    if isinstance(action_spec, str):
        ga = _ACTION_NAME_MAP.get(action_spec, GameAction.ACTION5)
        return ga, {}
    if isinstance(action_spec, dict):
        name = action_spec.get("action", action_spec.get("type", "ACTION5"))
        ga = _ACTION_NAME_MAP.get(name, GameAction.ACTION5)
        data: dict[str, Any] = {}
        if "x" in action_spec and "y" in action_spec:
            data["x"] = action_spec["x"]
            data["y"] = action_spec["y"]
        elif "coordinate" in action_spec:
            coord = action_spec["coordinate"]
            data["x"] = coord[1]
            data["y"] = coord[0]
        return ga, data
    # Fallback
    return GameAction.ACTION5, {}


# ===================================================================
# Simple World Model for instrumental planning
# ===================================================================

@dataclass
class ActionEffect:
    """Learned effect of a single action."""
    action_name: str
    avg_cells_changed: float = 0.0
    times_used: int = 0
    caused_level_up: bool = False
    direction_hint: str = ""
    reversible: bool = False
    # Track consecutive same-action runs for progress
    consecutive_progress: int = 0


@dataclass
class WorldModel:
    """Simple world model that tracks discovered action effects.

    During INSTRUMENTAL phase, uses learned effects to plan goal-directed
    actions via greedy heuristic or BFS over known dynamics.
    """
    effects: dict[str, ActionEffect] = field(default_factory=dict)
    # Track which action sequences led to level-ups
    level_up_sequences: list[list[str]] = field(default_factory=list)
    # Track recent action -> diff_cells for heuristic planning
    recent_diffs: list[tuple[str, int]] = field(default_factory=list)
    # Previous level count for detecting level-ups
    _prev_levels: int = 0

    def record_action(
        self,
        action_name: str,
        diff_cells: int,
        levels_before: int,
        levels_after: int,
    ) -> None:
        """Record the observed effect of an action."""
        if action_name not in self.effects:
            self.effects[action_name] = ActionEffect(action_name=action_name)
        eff = self.effects[action_name]
        eff.times_used += 1
        # Running average of cells changed
        eff.avg_cells_changed = (
            (eff.avg_cells_changed * (eff.times_used - 1) + diff_cells)
            / eff.times_used
        )
        if levels_after > levels_before:
            eff.caused_level_up = True

        self.recent_diffs.append((action_name, diff_cells))
        if len(self.recent_diffs) > 50:
            self.recent_diffs = self.recent_diffs[-50:]

    def best_instrumental_action(
        self,
        available_actions: list[str],
        strategy: str = "most_progress",
        step_index: int = 0,
    ) -> str:
        """Pick the action most likely to make progress toward the goal.

        Strategies:
          - most_progress: cycle through actions that produce change
          - level_up: pick action that previously caused a level-up
          - cycle_untried: round-robin through less-used actions
          - diverse: rotate through all productive actions
        """
        if not available_actions:
            return "ACTION5"

        # If any action caused a level-up, prefer it
        for name in available_actions:
            eff = self.effects.get(name)
            if eff and eff.caused_level_up:
                return name

        # Filter to actions that actually do something (avg_diff > 0)
        productive = [
            name for name in available_actions
            if name not in ("ACTION6",)  # skip ACTION6 without coords
            and (not self.effects.get(name)
                 or self.effects[name].avg_cells_changed > 0)
        ]
        if not productive:
            productive = [a for a in available_actions if a != "ACTION6"]
        if not productive:
            productive = available_actions

        if strategy == "most_progress" or strategy == "diverse":
            # Cycle through productive actions using step_index
            # This prevents getting stuck repeating the same action
            idx = step_index % len(productive)
            return productive[idx]

        if strategy == "cycle_untried":
            # Pick least-used action
            min_uses = float("inf")
            best_name = productive[0]
            for name in productive:
                eff = self.effects.get(name)
                uses = eff.times_used if eff else 0
                if uses < min_uses:
                    min_uses = uses
                    best_name = name
            return best_name

        return productive[step_index % len(productive)]

    def suggest_instrumental_sequence(
        self,
        available_actions: list[str],
        max_len: int = 5,
    ) -> list[str]:
        """Return a short sequence of actions predicted to make progress.

        Uses the heuristic: "repeat the action that caused the most change".
        Falls back to cycling through less-used actions if stuck.
        """
        sequence: list[str] = []
        best = self.best_instrumental_action(available_actions, "most_progress")

        # If no action has been tried, start with ACTION1
        if not self.effects:
            return [available_actions[0]] if available_actions else ["ACTION5"]

        # Check if best action is actually doing something
        eff = self.effects.get(best)
        if eff and eff.avg_cells_changed > 0:
            # Repeat the productive action
            sequence = [best] * min(max_len, 3)
        else:
            # Stuck: cycle through all available actions
            for i in range(min(max_len, len(available_actions))):
                sequence.append(available_actions[i % len(available_actions)])

        return sequence

    def summary(self) -> str:
        """Human-readable summary of learned world model."""
        lines = ["World Model:"]
        for name, eff in sorted(self.effects.items()):
            lines.append(
                f"  {name}: used={eff.times_used} "
                f"avg_diff={eff.avg_cells_changed:.1f} "
                f"level_up={eff.caused_level_up}"
            )
        return "\n".join(lines)


# ===================================================================
# S3-2: SubgoalPlanner — generate and manage subgoals
# ===================================================================

class SubgoalPlanner:
    """Generate candidate subgoals from perception + belief state,
    then select the best action to pursue the active subgoal.

    Lifecycle:
      1. generate() — produce 2-3 candidate subgoals from current state
      2. select() — pick the highest-priority subgoal as active
      3. next_action() — return the next action from the active subgoal's outline
      4. update() — after each step, check if subgoal is achieved/failed
    """

    _counter: int = 0
    # Track failed subgoal types+targets to avoid repeating them
    _failed_keys: set[str] = field(default_factory=set) if False else None  # type: ignore[assignment]

    def __init__(self) -> None:
        self._counter = 0
        self._failed_keys: set[str] = set()

    def _subgoal_key(self, sg_type: str, target_pid: str | None) -> str:
        return f"{sg_type}:{target_pid or 'none'}"

    def record_failure(self, sg: Subgoal) -> None:
        """Remember that this subgoal type+target failed."""
        self._failed_keys.add(self._subgoal_key(sg.subgoal_type, sg.target_pid))

    def _make_id(self) -> str:
        self._counter += 1
        return f"SG_{self._counter}"

    def generate(
        self,
        objects: list,  # list[PerceivedObject]
        belief_state: BeliefLedger,
        available_actions: list[str],
        grid_rows: int,
        grid_cols: int,
    ) -> list[Subgoal]:
        """S3-2: Produce candidate subgoals from perception role scores + belief."""
        candidates: list[Subgoal] = []

        # Collect objects by role
        controllables = [o for o in objects if o.controllable_score >= 0.3]
        goals = [o for o in objects if o.goal_score >= 0.4]
        blockers = [o for o in objects if o.blocker_score >= 0.3 and o.controllable_score < 0.3]
        click_targets = [o for o in objects if o.click_score >= 0.4]

        # Find directional actions (include unknown actions — only exclude confirmed noops)
        directional = [
            a for a in available_actions
            if a in {"ACTION1", "ACTION2", "ACTION3", "ACTION4"}
            and not (belief_state.action_beliefs.get(a) and belief_state.action_beliefs[a].is_noop)
        ]

        # --- reach_target: move controllable toward goal ---
        if controllables and goals:
            ctrl = max(controllables, key=lambda o: o.controllable_score)
            goal = max(goals, key=lambda o: o.goal_score)
            # Build action outline: directional actions toward goal
            outline = self._direction_outline(
                ctrl, goal, directional,
                action_beliefs=dict(belief_state.action_beliefs),
            )
            candidates.append(Subgoal(
                subgoal_id=self._make_id(),
                subgoal_type="reach_target",
                target_pid=goal.persistent_id,
                target_region=(goal.row_min, goal.row_max, goal.col_min, goal.col_max),
                priority=0.8,
                confidence=min(ctrl.controllable_score, goal.goal_score),
                rationale=f"Move {ctrl.persistent_id} toward goal {goal.persistent_id}",
                action_outline=outline,
            ))

        # --- clear_path: deal with blocker between controllable and goal ---
        if controllables and blockers:
            ctrl = max(controllables, key=lambda o: o.controllable_score)
            blocker = max(blockers, key=lambda o: o.blocker_score)
            # Try actions that might move the blocker
            outline = []
            for a in directional[:3]:
                outline.append(a)
            candidates.append(Subgoal(
                subgoal_id=self._make_id(),
                subgoal_type="clear_path",
                target_pid=blocker.persistent_id,
                priority=0.7,
                confidence=blocker.blocker_score * 0.8,
                rationale=f"Clear blocker {blocker.persistent_id} "
                          f"(block_score={blocker.blocker_score:.2f})",
                action_outline=outline,
            ))

        # --- activate_switch: click or interact with target ---
        if click_targets:
            target = max(click_targets, key=lambda o: o.click_score)
            outline = ["ACTION5"] if "ACTION5" in available_actions else []
            if "ACTION6" in available_actions:
                outline = ["ACTION6"]
            candidates.append(Subgoal(
                subgoal_id=self._make_id(),
                subgoal_type="activate_switch",
                target_pid=target.persistent_id,
                target_region=(target.row_min, target.row_max,
                               target.col_min, target.col_max),
                priority=0.6,
                confidence=target.click_score * 0.7,
                rationale=f"Activate {target.persistent_id} "
                          f"(click_score={target.click_score:.2f})",
                action_outline=outline,
            ))

        # --- explore_region: if no clear goal, explore unvisited area ---
        if not goals and directional:
            candidates.append(Subgoal(
                subgoal_id=self._make_id(),
                subgoal_type="explore_region",
                priority=0.4,
                confidence=0.3,
                rationale="No clear goal detected; explore to find objectives",
                action_outline=directional[:4],
            ))

        # --- test_hypothesis: if a hypothesis needs verification ---
        weak_hypotheses = [
            h for h in belief_state.hypotheses
            if h.status == "provisional" and 0.15 < h.confidence < 0.5
        ]
        if weak_hypotheses and len(candidates) < 3:
            h = weak_hypotheses[0]
            candidates.append(Subgoal(
                subgoal_id=self._make_id(),
                subgoal_type="test_hypothesis",
                priority=0.5,
                confidence=0.4,
                rationale=f"Test hypothesis {h.hypothesis_id}: {h.summary[:60]}",
                action_outline=available_actions[:2],
            ))

        # Filter out subgoal types that already failed
        candidates = [
            sg for sg in candidates
            if self._subgoal_key(sg.subgoal_type, sg.target_pid) not in self._failed_keys
        ]
        return candidates

    @staticmethod
    def _direction_outline(
        ctrl: Any, goal: Any, directional: list[str],
        action_beliefs: dict | None = None,
    ) -> list[str]:
        """S3-3: Build action outline using action_beliefs for smarter planning.

        Uses action_beliefs to:
        - Prefer high-confidence directional actions
        - Avoid noop actions
        - Respect reversible pairs (don't cancel progress)
        - Cap outline at 5 actions
        """
        outline: list[str] = []
        dr = goal.center[0] - ctrl.center[0]
        dc = goal.center[1] - ctrl.center[1]

        # Build scored action list from beliefs
        scored: list[tuple[str, float]] = []
        for a in directional:
            ab = (action_beliefs or {}).get(a)
            if ab and ab.is_noop:
                continue  # skip confirmed noops
            score = 0.5
            if ab:
                score = ab.confidence * (1.0 if ab.is_directional else 0.5)
            scored.append((a, score))

        scored.sort(key=lambda x: -x[1])

        # Direction heuristic (ACTION1=UP, ACTION2=DOWN, ACTION3=LEFT, ACTION4=RIGHT)
        if abs(dr) > abs(dc):
            if dr < 0:
                primary = [a for a, _ in scored if a == "ACTION1"]
            else:
                primary = [a for a, _ in scored if a == "ACTION2"]
        else:
            if dc < 0:
                primary = [a for a, _ in scored if a == "ACTION3"]
            else:
                primary = [a for a, _ in scored if a == "ACTION4"]

        # Use primary direction if available, otherwise best directional
        chosen = primary[0] if primary else (scored[0][0] if scored else None)
        if chosen:
            # S3-3: Limit repetitions based on distance (capped at 5)
            dist = max(abs(dr), abs(dc))
            reps = min(5, max(1, int(dist / 6)))
            outline.extend([chosen] * reps)

        # Add secondary direction if needed
        if abs(dr) > 3 and abs(dc) > 3 and len(outline) < 5:
            if abs(dr) > abs(dc):
                sec_dir = "ACTION3" if dc < 0 else "ACTION4"
            else:
                sec_dir = "ACTION1" if dr < 0 else "ACTION2"
            if sec_dir in directional:
                sec_reps = min(2, 5 - len(outline))
                outline.extend([sec_dir] * sec_reps)

        if not outline and directional:
            outline = directional[:2]

        return outline[:5]  # hard cap at 5 actions

    def select(self, candidates: list[Subgoal]) -> Subgoal | None:
        """Pick the highest-priority candidate."""
        if not candidates:
            return None
        return max(candidates, key=lambda sg: sg.priority * sg.confidence)

    def update_status(
        self,
        subgoal: Subgoal,
        objects: list,  # list[PerceivedObject]
        levels_completed: int,
        prev_levels: int,
        diff_cells: int,
    ) -> None:
        """Check if the active subgoal was achieved or failed."""
        subgoal.steps_spent += 1

        # Level up = subgoal achieved (whatever it was)
        if levels_completed > prev_levels:
            subgoal.status = "achieved"
            return

        # reach_target: check if controllable is now near target
        if subgoal.subgoal_type == "reach_target" and subgoal.target_pid:
            target = next((o for o in objects if o.persistent_id == subgoal.target_pid), None)
            ctrl = next((o for o in objects if o.controllable_score >= 0.3), None)
            if target and ctrl:
                dist = ((target.center[0] - ctrl.center[0]) ** 2
                        + (target.center[1] - ctrl.center[1]) ** 2) ** 0.5
                if dist < 4.0:
                    subgoal.status = "achieved"
                    return

        # Exhausted action outline
        if subgoal.steps_spent >= len(subgoal.action_outline) + 2:
            subgoal.status = "failed"
            return

        # Hard cap: no single subgoal should run more than 8 steps
        if subgoal.steps_spent >= 8:
            subgoal.status = "failed"
            return

        # Stagnation: very small diff suggests no progress
        if diff_cells <= 1 and subgoal.steps_spent >= 3:
            subgoal.status = "failed"


# ===================================================================
# Observation builder
# ===================================================================

def _build_observation(
    game_id: str,
    step_index: int,
    grid: list[list[int]],
    prev_grid: list[list[int]] | None,
    state_name: str,
    levels_completed: int,
    available_actions: list[str],
    action_history: list[Any],
    objects: list[ObjectSummary],
) -> ObservationSnapshot:
    """Build an ObservationSnapshot from the current game state."""
    diff_str = "INITIAL"
    if prev_grid is not None:
        diff_str = compute_diff(prev_grid, grid)

    histogram: dict[str, int] = {}
    for row in grid:
        for v in row:
            key = str(v)
            histogram[key] = histogram.get(key, 0) + 1

    return ObservationSnapshot(
        game_id=game_id,
        step_index=step_index,
        state=state_name,
        levels_completed=levels_completed,
        grid_rows=len(grid),
        grid_cols=len(grid[0]) if grid else 0,
        available_actions=available_actions,
        diff_summary=diff_str,
        action_history=action_history[-20:],  # keep recent history
        value_histogram=histogram,
        objects=objects,
        compressed_grid=compress_grid(grid),
    )


# ===================================================================
# Step result
# ===================================================================

@dataclass
class BeliefDiff:
    """B2-3: Structured belief diff for one step — consumable by trace/export."""
    hypotheses_strengthened: int = 0
    hypotheses_weakened: int = 0
    hypotheses_discarded: int = 0
    hypotheses_suggested: int = 0
    motifs_updated: int = 0
    anchoring_alerts: int = 0
    max_confidence_delta: float = 0.0
    summary: str = ""


@dataclass
class StepResult:
    """Result of one solve_step call."""
    belief_state: BeliefLedger
    action_taken: str
    diff_cells: int
    levels_completed: int
    phase: PhaseState
    surprise_severity: SurpriseSeverity
    done: bool = False
    done_reason: str = ""
    # B2-3: Structured belief diff
    belief_diff: BeliefDiff = field(default_factory=BeliefDiff)
    # S3-1: Active subgoal info
    active_subgoal_type: str = ""
    active_subgoal_id: str = ""
    # LLM usage tracking
    llm_used: bool = False
    llm_model: str = ""
    # Prediction for the action just selected (PREDICT stage of this step,
    # becomes the RESULT reference for the NEXT step).
    predict_text: str = ""
    predicted_diff_cells: int | None = None
    predicted_diff_low: int | None = None
    predicted_diff_high: int | None = None


# ===================================================================
# Interaction & Dynamics inference helpers
# ===================================================================

def _infer_interactions(
    prev_objects: list[PerceivedObject],
    curr_objects: list[PerceivedObject],
    transitions: list,
    last_action: str,
    belief_state: BeliefLedger,
    step_index: int,
) -> None:
    """Detect causal object interactions from transitions.

    If two objects changed simultaneously and were adjacent,
    one likely caused the other's change (push, trigger, etc.).
    """
    from agents.agentic.schemas import InteractionRule

    # Find objects that changed this step
    changed_pids: set[str] = set()
    for t in transitions:
        # Map transition obj_id to persistent_id
        for obj in curr_objects:
            if obj.obj_id == t.obj_id and obj.persistent_id:
                changed_pids.add(obj.persistent_id)

    if len(changed_pids) < 2:
        return

    # Find controllable (likely cause) and others (likely affected)
    ctrl_pids = {o.persistent_id for o in curr_objects
                 if o.controllable_score >= 0.3 and o.persistent_id in changed_pids}
    affected_pids = changed_pids - ctrl_pids

    if not ctrl_pids or not affected_pids:
        return

    # Check if interaction already known
    known_pairs = {
        (ir.trigger_pid, ir.affected_pid)
        for ir in belief_state.interaction_rules
    }

    for cpid in ctrl_pids:
        for apid in affected_pids:
            if (cpid, apid) in known_pairs:
                # Update existing rule
                for ir in belief_state.interaction_rules:
                    if ir.trigger_pid == cpid and ir.affected_pid == apid:
                        ir.times_observed += 1
                        ir.confidence = min(0.3 + 0.15 * ir.times_observed, 0.95)
                        break
            else:
                # New interaction
                belief_state.interaction_rules.append(InteractionRule(
                    rule_id=f"IR_{len(belief_state.interaction_rules) + 1}",
                    trigger_pid=cpid,
                    affected_pid=apid,
                    trigger_action=last_action,
                    effect=f"{cpid} action caused {apid} to change",
                    rule_type="unknown",
                    confidence=0.3,
                    times_observed=1,
                    discovered_at_step=step_index,
                ))

    # Cap to prevent unbounded growth
    if len(belief_state.interaction_rules) > 30:
        belief_state.interaction_rules = sorted(
            belief_state.interaction_rules,
            key=lambda ir: ir.confidence, reverse=True,
        )[:20]


def _infer_dynamics_rule(
    action_name: str,
    prev_objects: list[PerceivedObject],
    curr_objects: list[PerceivedObject],
    diff_cells: int,
    belief_state: BeliefLedger,
    step_index: int,
) -> None:
    """Build/update dynamics rules from observed action effects.

    Captures: "ACTION1 moves the controllable object upward"
    by detecting which persistent objects moved and in what direction.
    """
    from agents.agentic.schemas import DynamicsRule

    if diff_cells == 0:
        # Check if we should record a "noop" rule
        existing = [r for r in belief_state.dynamics_rules if r.action_name == action_name]
        for r in existing:
            if "no effect" in r.effect:
                r.times_verified += 1
                r.confidence = min(0.3 + 0.15 * r.times_verified, 0.95)
                return
        return

    # Find what moved
    prev_by_pid = {o.persistent_id: o for o in prev_objects if o.persistent_id}
    movements: list[tuple[str, float, float]] = []  # (pid, dr, dc)

    for obj in curr_objects:
        pid = obj.persistent_id
        if pid and pid in prev_by_pid:
            prev_obj = prev_by_pid[pid]
            dr = obj.center[0] - prev_obj.center[0]
            dc = obj.center[1] - prev_obj.center[1]
            if abs(dr) > 0.5 or abs(dc) > 0.5:
                movements.append((pid, dr, dc))

    if not movements:
        return

    # Build effect description
    ctrl_movements = [
        (pid, dr, dc) for pid, dr, dc in movements
        if any(o.persistent_id == pid and o.controllable_score >= 0.3
               for o in curr_objects)
    ]

    if ctrl_movements:
        pid, dr, dc = ctrl_movements[0]
        if abs(dr) > abs(dc):
            direction = "up" if dr < 0 else "down"
            dist = abs(dr)
        else:
            direction = "left" if dc < 0 else "right"
            dist = abs(dc)
        effect = f"moves controllable {pid} {direction} ~{dist:.0f} cells ({diff_cells} cells changed)"
    else:
        effect = f"changes {len(movements)} objects ({diff_cells} cells changed)"

    # Find existing rule for this action+direction pattern
    for rule in belief_state.dynamics_rules:
        if rule.action_name == action_name and effect[:30] in rule.effect[:30]:
            rule.times_verified += 1
            rule.confidence = min(0.3 + 0.15 * rule.times_verified, 0.95)
            return

    # New rule
    belief_state.dynamics_rules.append(DynamicsRule(
        rule_id=f"DR_{len(belief_state.dynamics_rules) + 1}",
        action_name=action_name,
        condition="",
        effect=effect,
        confidence=0.3,
        times_verified=1,
        discovered_at_step=step_index,
    ))

    # Cap to prevent unbounded growth
    if len(belief_state.dynamics_rules) > 30:
        belief_state.dynamics_rules = sorted(
            belief_state.dynamics_rules,
            key=lambda r: r.confidence, reverse=True,
        )[:20]


# ===================================================================
# 6-stage reasoning chain composers
# ===================================================================

def _build_predict_text(
    action_name: str,
    action_data: dict[str, Any],
    belief_state: BeliefLedger,
    world_model: "WorldModel",
    expected_outcome: str | None,
    simulator: "Simulator | None",
) -> tuple[str, int | None, int | None, int | None]:
    """PREDICT stage: describe expected outcome of the action just selected.

    Returns (text, predicted_diff_cells, low_bound, high_bound).
    Low/high bounds drive automatic RESULT verification on the next step.
    """
    ab = belief_state.action_beliefs.get(action_name)
    pred_diff: int | None = None
    low: int | None = None
    high: int | None = None
    parts: list[str] = []

    if ab and ab.times_used >= 2:
        pred_diff = int(round(ab.avg_cells_changed))
        low = max(0, int(round(ab.avg_cells_changed * 0.5)))
        high = int(round(ab.avg_cells_changed * 2.0))
        tags: list[str] = []
        if ab.is_noop:
            tags.append("no-op")
        if ab.is_directional:
            tags.append("directional")
        if ab.is_reversible_with:
            tags.append(f"reverses {ab.is_reversible_with}")
        tag_str = f" ({', '.join(tags)})" if tags else ""
        parts.append(
            f"{action_name}{tag_str}: expect ~{pred_diff} cells changed "
            f"[range {low}-{high}] based on {ab.times_used} prior uses."
        )
        if ab.affected_pids:
            parts.append(f"Likely affects pids: {', '.join(ab.affected_pids[:3])}.")
    else:
        eff = world_model.effects.get(action_name)
        if eff and eff.times_used > 0:
            pred_diff = int(round(eff.avg_cells_changed))
            low = max(0, int(round(eff.avg_cells_changed * 0.4)))
            high = int(round(eff.avg_cells_changed * 2.5))
            parts.append(
                f"{action_name}: rough prior {pred_diff} cells "
                f"[range {low}-{high}] from world_model ({eff.times_used} uses)."
            )
        else:
            parts.append(
                f"{action_name}: untested action — no prior; any diff is informative."
            )

    if simulator is not None and simulator.avg_confidence >= 0.5:
        parts.append(
            f"Simulator v{simulator.version} (conf {simulator.avg_confidence:.2f}) available for this action."
        )

    if action_name == "ACTION6" and action_data:
        parts.append(f"Click coords: x={action_data.get('x')}, y={action_data.get('y')}.")

    if expected_outcome:
        parts.append(f"Expected: {expected_outcome}")

    return " ".join(parts), pred_diff, low, high


def _build_observe_text(
    step_index: int,
    actual_diff_cells: int,
    state_name: str,
    levels_completed: int,
    object_count: int,
    available_actions: list[str],
) -> str:
    """OBSERVE stage: pure facts about the post-action frame."""
    return (
        f"Step {step_index}: state={state_name}, L{levels_completed}, "
        f"diff={actual_diff_cells} cells, {object_count} non-bg objects, "
        f"available=[{','.join(available_actions)}]."
    )


def _build_interpret_text(
    last_action: str | None,
    actual_diff_cells: int,
    belief_state: BeliefLedger,
) -> str:
    """INTERPRET stage: give meaning to the raw observation."""
    if not last_action:
        return "Initial observation after RESET — no action effect to interpret yet."
    if actual_diff_cells == 0:
        ab = belief_state.action_beliefs.get(last_action)
        if ab and ab.is_noop:
            return f"{last_action} had no effect (confirmed no-op, conf {ab.confidence:.2f})."
        return f"{last_action} had no visible effect this time — may be blocked or conditionally no-op."
    matching_rules = [
        r for r in belief_state.dynamics_rules
        if r.action_name == last_action and r.confidence >= 0.4
    ]
    if matching_rules:
        top = matching_rules[0]
        return (
            f"{last_action} produced {actual_diff_cells} cells — consistent with rule "
            f"'{top.effect}' (conf {top.confidence:.2f}, verified {top.times_verified}x)."
        )
    return f"{last_action} produced {actual_diff_cells} cells — dynamics still being learned."


def _build_hypothesize_text(belief_state: BeliefLedger) -> str:
    """HYPOTHESIZE stage: top candidate explanations with confidences."""
    active = [h for h in belief_state.hypotheses if h.status in ("active", "provisional")]
    if not active:
        return "No active hypotheses yet."
    active.sort(key=lambda h: -h.confidence)
    top = active[:3]
    lines = [f"{h.hypothesis_id}({h.confidence:.2f}): {h.summary}" for h in top]
    goal_str = ""
    if belief_state.goal_beliefs:
        g = belief_state.goal_beliefs[0]
        goal_str = f" Goal({g.confidence:.2f}): {g.summary}."
    return " | ".join(lines) + goal_str


def _build_result_text(
    last_pred_text: str | None,
    last_pred_low: int | None,
    last_pred_high: int | None,
    actual_diff_cells: int,
    surprise_severity: SurpriseSeverity,
) -> tuple[str, bool | None]:
    """RESULT stage: compare last-step prediction against current actual diff.

    Returns (text, hit) where hit is None if no prediction was available.
    """
    if not last_pred_text:
        return (
            f"Actual diff={actual_diff_cells}. No prior prediction to verify.",
            None,
        )
    if last_pred_low is not None and last_pred_high is not None:
        hit = last_pred_low <= actual_diff_cells <= last_pred_high
        marker = "HIT" if hit else "MISS"
        return (
            f"Actual diff={actual_diff_cells}. Predicted [{last_pred_low}-{last_pred_high}] "
            f"→ {marker}. Surprise={surprise_severity.name}.",
            hit,
        )
    return (
        f"Actual diff={actual_diff_cells}. Predicted (qualitative only): {last_pred_text[:80]}. "
        f"Surprise={surprise_severity.name}.",
        None,
    )


def _build_revise_text(
    dynamics_revision: str,
    belief_revision_summary: list[str],
    suggested_hypotheses: list[str],
) -> str:
    """REVISE stage: summarize rule/hypothesis/plan updates from this step."""
    parts: list[str] = []
    if belief_revision_summary:
        parts.append("Updates: " + " | ".join(belief_revision_summary[:3]))
    if suggested_hypotheses:
        parts.append("New hypotheses: " + " | ".join(suggested_hypotheses[:2]))
    if dynamics_revision and dynamics_revision != "No explicit belief revision summary.":
        parts.append(dynamics_revision)
    return " ".join(parts) if parts else "No revisions this step."


# ===================================================================
# solve_step: one step of the solve loop
# ===================================================================

def solve_step(
    # Game environment state
    grid: list[list[int]],
    prev_grid: list[list[int]] | None,
    prev_objects: list[PerceivedObject] | None,
    game_id: str,
    step_index: int,
    state_name: str,
    levels_completed: int,
    available_action_names: list[str],
    action_history: list[str],
    # Agentic infrastructure
    belief_state: BeliefLedger,
    phase_manager: PhaseManager,
    experiment_designer: ExperimentDesigner,
    world_model: WorldModel,
    surprise_history: list[SurpriseReport],
    anti_anchoring: AntiAnchoringGuard,
    # Budget
    max_steps: int,
    # Episode memory (optional)
    memory: EpisodeMemoryStore | None = None,
    curator: TrajectoryCurator | None = None,
    # P1-1 / P1-2: persistent tracking and role scoring
    persistent_tracker: PersistentObjectTracker | None = None,
    role_scorer: RoleScorer | None = None,
    # S3-1 / S3-2: subgoal planning
    subgoal_planner: SubgoalPlanner | None = None,
    # Simulator-based planning
    simulator: Simulator | None = None,
    simulator_builder: SimulatorBuilder | None = None,
    # LLM brain (optional — replaces heuristics when provided)
    llm_brain: Any | None = None,
    # Previous step's PREDICT output (used to compose current step's RESULT).
    last_prediction_text: str | None = None,
    last_prediction_low: int | None = None,
    last_prediction_high: int | None = None,
) -> tuple[StepResult, list[PerceivedObject], str, dict[str, Any]]:
    """Execute one step of the agentic solve loop.

    Returns (StepResult, current_objects, action_name_taken, action_data).
    The caller is responsible for executing the action in the environment
    and calling this function again with the new grid.
    ``action_data`` carries coordinate info for ACTION6 (keys ``x``, ``y``).
    """
    # 1. Run perception (with persistent tracking + role scoring)
    last_action = action_history[-1] if action_history else None
    perc = run_perception(
        grid=grid,
        prev_grid=prev_grid,
        prev_objects=prev_objects,
        persistent_tracker=persistent_tracker,
        role_scorer=role_scorer,
        last_action=last_action,
    )
    current_objects: list[PerceivedObject] = perc["objects"]
    transitions = perc["transitions"]
    object_summaries: list[ObjectSummary] = perc["object_summaries"]
    affordances: dict[str, float] = perc["affordances"]
    regions: list[dict] = perc.get("regions", [])

    # 1b. Update regions and reference patterns in belief state
    if regions and (not belief_state.regions or step_index <= 3):
        from agents.agentic.schemas import Region as RegionSchema
        belief_state.regions = [
            RegionSchema(**{k: v for k, v in r.items() if k in RegionSchema.model_fields})
            for r in regions[:20]  # cap to avoid bloat
        ]

    # 1b-2. Extract reference pattern summaries from goal surfaces
    goal_surfaces = perc.get("goal_surfaces", [])
    if goal_surfaces and (not belief_state.reference_patterns or step_index <= 3):
        from agents.agentic.schemas import ReferencePatternSummary
        ref_pats: list[ReferencePatternSummary] = []
        for i, gs in enumerate(goal_surfaces):
            if gs.kind != "reference_box":
                continue
            # Build compact pattern_rows (≤8x8 only)
            pat_rows: list[str] = []
            if gs.internal_pattern:
                h = len(gs.internal_pattern)
                w = max((len(r) for r in gs.internal_pattern), default=0)
                if h <= 8 and w <= 8:
                    pat_rows = [
                        "".join(str(v) if v < 10 else chr(55 + v) for v in row)
                        for row in gs.internal_pattern
                    ]
            ref_pats.append(ReferencePatternSummary(
                surface_id=f"REF_{i + 1}",
                kind=gs.kind,
                row_min=gs.row_min,
                row_max=gs.row_max,
                col_min=gs.col_min,
                col_max=gs.col_max,
                pattern_rows=pat_rows,
                pattern_description=gs.pattern_description,
                confidence=0.6 if pat_rows else 0.3,
            ))
        if ref_pats:
            belief_state.reference_patterns = ref_pats[:5]

    # 1c. Infer interaction rules from transitions
    if prev_objects and transitions and action_history:
        _infer_interactions(
            prev_objects, current_objects, transitions,
            action_history[-1] if action_history else "",
            belief_state, step_index,
        )

    # 1d. Infer dynamics rules from action results
    if prev_objects and action_history:
        _infer_dynamics_rule(
            action_history[-1] if action_history else "",
            prev_objects, current_objects,
            diff_cell_count(prev_grid, grid) if prev_grid else 0,
            belief_state, step_index,
        )

    # 2. Build observation
    obs = _build_observation(
        game_id=game_id,
        step_index=step_index,
        grid=grid,
        prev_grid=prev_grid,
        state_name=state_name,
        levels_completed=levels_completed,
        available_actions=available_action_names,
        action_history=action_history,
        objects=object_summaries,
    )

    # 3. Update belief step_index
    belief_state.step_index = step_index

    # 4. Check phase transition
    budget_remaining = max(0.0, (max_steps - step_index) / max(max_steps, 1))
    phase = phase_manager.evaluate_transition(
        belief_ledger=belief_state,
        surprise_history=surprise_history,
        step=step_index,
        budget_remaining=budget_remaining,
        levels_completed=levels_completed,
    )
    # Keep exported belief/trace artifacts aligned with the phase that
    # actually drove action selection on this step.
    belief_state.mode = phase.name.lower()  # type: ignore[assignment]

    # 5. Phase-aware action selection
    action_name: str
    rationale: str
    expected_outcome: str | None = None
    action_data: dict[str, Any] = {}
    llm_used: bool = False
    llm_model_name: str = ""

    # --- LLM Brain override: replaces ALL heuristic decision-making ---
    if llm_brain is not None:
        from agents.agentic.llm_brain import BrainDecision
        # Build compact state for LLM
        last_surprise_str = ""
        if surprise_history:
            last = surprise_history[-1]
            if last.is_surprising:
                last_surprise_str = last.summary

        # Energy fraction from grid
        energy_frac = max(0.0, (max_steps - step_index) / max(max_steps, 1))

        brain_decision: BrainDecision = llm_brain.decide(
            grid_summary=obs.compressed_grid or "",
            objects=[o.model_dump() for o in object_summaries[:15]],
            diff_summary=obs.diff_summary,
            dynamics_rules=[r.model_dump() for r in belief_state.dynamics_rules[:6]],
            interaction_rules=[r.model_dump() for r in belief_state.interaction_rules[:4]],
            regions=[r.model_dump() for r in belief_state.regions[:6]],
            reference_patterns=[r.model_dump() for r in belief_state.reference_patterns[:3]],
            hypotheses=[h.model_dump() for h in belief_state.hypotheses[:4]],
            action_beliefs={k: v.model_dump() for k, v in list(belief_state.action_beliefs.items())[:6]},
            goal_beliefs=[g.model_dump() for g in belief_state.goal_beliefs[:2]],
            available_actions=available_action_names,
            action_history=action_history,
            phase=phase.name,
            step_index=step_index,
            levels_completed=levels_completed,
            energy_fraction=energy_frac,
            last_surprise=last_surprise_str,
        )

        action_name = brain_decision.action
        rationale = brain_decision.rationale or f"LLM chose {action_name}"
        expected_outcome = brain_decision.expected_outcome

        # Handle ACTION6 coordinates — pass through to _resolve_action
        if brain_decision.action_data and action_name == "ACTION6":
            action_data = {
                "x": brain_decision.action_data.get("x", 0),
                "y": brain_decision.action_data.get("y", 0),
            }
            belief_state.notes.append(
                f"ACTION6_COORDS:{action_data['x']},{action_data['y']}"
            )

        llm_used = True
        llm_model_name = getattr(llm_brain, "model", "")

        # Update goal belief if LLM has a hypothesis
        if brain_decision.goal_hypothesis:
            from agents.agentic.schemas import GoalBelief as GoalBeliefSchema
            if belief_state.goal_beliefs:
                belief_state.goal_beliefs[0].summary = brain_decision.goal_hypothesis
                belief_state.goal_beliefs[0].confidence = min(
                    belief_state.goal_beliefs[0].confidence + 0.1, 0.95
                )
            else:
                belief_state.goal_beliefs.append(GoalBeliefSchema(
                    summary=brain_decision.goal_hypothesis,
                    confidence=0.4,
                ))

        # Update motif beliefs from LLM
        if brain_decision.motifs:
            for motif in belief_state.top_motifs:
                if motif.name in brain_decision.motifs:
                    motif.confidence = brain_decision.motifs[motif.name]
            # Add new motifs not in bootstrap
            existing_names = {m.name for m in belief_state.top_motifs}
            for name, conf in brain_decision.motifs.items():
                if name not in existing_names:
                    belief_state.top_motifs.append(MotifBelief(
                        name=name, confidence=conf,
                        evidence=[f"LLM identified at step {step_index}"],
                    ))

        # Update hypotheses from LLM
        if brain_decision.hypotheses:
            # Replace bootstrap hypotheses with LLM's
            for llm_h in brain_decision.hypotheses:
                found = False
                for h in belief_state.hypotheses:
                    if h.hypothesis_id == llm_h["id"]:
                        h.summary = llm_h["summary"]
                        h.confidence = llm_h["confidence"]
                        h.status = "active" if llm_h["confidence"] >= 0.3 else "provisional"
                        found = True
                        break
                if not found and len(belief_state.hypotheses) < 6:
                    belief_state.hypotheses.append(HypothesisEntry(
                        hypothesis_id=llm_h["id"],
                        summary=llm_h["summary"],
                        confidence=llm_h["confidence"],
                        status="active" if llm_h["confidence"] >= 0.3 else "provisional",
                    ))

        # Update object labels from LLM
        if brain_decision.object_labels:
            for obj in current_objects:
                if obj.persistent_id and obj.persistent_id in brain_decision.object_labels:
                    # Update the label on the ObjectSummary
                    label = brain_decision.object_labels[obj.persistent_id]
                    for s in object_summaries:
                        if s.persistent_id == obj.persistent_id:
                            s.label = label

        # Log LLM interpretations for trace
        if brain_decision.dynamics_update:
            belief_state.notes.append(f"LLM_DYNAMICS: {brain_decision.dynamics_update}")
        if brain_decision.surprise_interpretation:
            belief_state.notes.append(f"LLM_SURPRISE: {brain_decision.surprise_interpretation}")
        if brain_decision.phase_reasoning:
            belief_state.notes.append(f"LLM_PHASE: {brain_decision.phase_reasoning}")
        if brain_decision.reference_interpretation:
            belief_state.notes.append(f"LLM_REFERENCE: {brain_decision.reference_interpretation}")

    elif phase == PhaseState.EPISTEMIC:
        # Use ExperimentDesigner to pick information-maximizing probe
        probe = experiment_designer.suggest_probe(
            belief_ledger=belief_state,
            available_actions=available_action_names,
            step_budget=max_steps,
            tested_actions=set(action_history),
            affordance_scores=affordances,
            grid_rows=len(grid),
            grid_cols=len(grid[0]) if grid else 30,
            current_step=step_index,
        )
        # Extract action name from probe
        if isinstance(probe.action, str):
            action_name = probe.action
        elif isinstance(probe.action, dict):
            action_name = probe.action.get("action", probe.action.get("type", "ACTION5"))
            # Handle sequence probes: just take the first action
            if "sequence" in probe.action:
                seq = probe.action["sequence"]
                action_name = seq[0] if seq else "ACTION5"
        else:
            action_name = "ACTION5"
        rationale = probe.rationale
        expected_outcome = probe.expected_outcome

        # Record probe in history
        family = ProbeFamily.MOVEMENT
        if action_name in {"ACTION5"}: family = ProbeFamily.TOGGLE
        elif action_name in {"ACTION6"}: family = ProbeFamily.CLICK
        elif action_name in {"ACTION7"}: family = ProbeFamily.UNDO
        experiment_designer.probe_history.record(
            action=action_name,
            family=family,
            step_index=step_index,
        )

    elif phase == PhaseState.INSTRUMENTAL:
        # --- Simulator-based planning (priority over subgoal planner) ---
        sim_plan_used = False
        if simulator and simulator.avg_confidence > 0.5 and simulator_builder:
            try:
                sim_state = simulator_builder.build_initial_state(current_objects, grid)
                goal_fn = lambda s: s.won
                plan = simulator.search_safe_bfs(
                    sim_state, goal_fn,
                    min_confidence=0.6,
                    max_depth=min(15, max_steps - step_index),
                )
                if plan:
                    action_name = plan[0]
                    rationale = (
                        f"Simulator BFS (v{simulator.version}, "
                        f"conf={simulator.avg_confidence:.2f}): "
                        f"plan={plan[:5]}{'...' if len(plan) > 5 else ''} "
                        f"({len(plan)} steps)"
                    )
                    expected_outcome = f"Simulator predicts path of {len(plan)} actions to goal"
                    sim_plan_used = True
                    logger.info("Simulator BFS found %d-step plan: %s", len(plan), plan[:5])
            except Exception as e:
                logger.warning("Simulator BFS failed: %s", e)

        # S3-2: Use subgoal planner for goal-directed action selection (fallback)
        if not sim_plan_used and subgoal_planner is not None:
            # Check/update existing active subgoal
            active_sg = next(
                (sg for sg in belief_state.active_subgoals if sg.status == "active"),
                None,
            )
            if active_sg:
                prev_diff = diff_cell_count(prev_grid, grid) if prev_grid else 0
                subgoal_planner.update_status(
                    active_sg, current_objects, levels_completed,
                    levels_completed, prev_diff,
                )

            # If no active subgoal or current one finished, generate new ones
            if not active_sg or active_sg.status in ("achieved", "failed", "abandoned"):
                # Record failed subgoals to avoid repeating them
                if active_sg and active_sg.status == "failed":
                    subgoal_planner.record_failure(active_sg)
                # Mark old ones as done
                for sg in belief_state.active_subgoals:
                    if sg.status == "active":
                        sg.status = "abandoned"

                candidates = subgoal_planner.generate(
                    objects=current_objects,
                    belief_state=belief_state,
                    available_actions=available_action_names,
                    grid_rows=len(grid),
                    grid_cols=len(grid[0]) if grid else 30,
                )
                active_sg = subgoal_planner.select(candidates)
                if active_sg:
                    active_sg.status = "active"
                    belief_state.active_subgoals = candidates

            # Pick action from active subgoal's outline
            if active_sg and active_sg.action_outline:
                idx = min(active_sg.steps_spent, len(active_sg.action_outline) - 1)
                action_name = active_sg.action_outline[idx]
                rationale = (f"Instrumental [{active_sg.subgoal_type}]: "
                             f"{active_sg.rationale} (step {active_sg.steps_spent + 1})")
                expected_outcome = (
                    f"Subgoal {active_sg.subgoal_id}: "
                    f"target={active_sg.target_pid or 'none'}"
                )
            else:
                # Fallback: diverse world model action
                action_name = world_model.best_instrumental_action(
                    available_action_names, strategy="diverse", step_index=step_index,
                )
                rationale = f"Instrumental: {action_name} (no active subgoal)"
                expected_outcome = f"Expected ~{world_model.effects.get(action_name, ActionEffect(action_name)).avg_cells_changed:.0f} cells change"
        else:
            # No subgoal planner: legacy behavior
            action_name = world_model.best_instrumental_action(
                available_action_names, strategy="diverse", step_index=step_index,
            )
            rationale = f"Instrumental: executing {action_name} (diverse progress)"
            expected_outcome = f"Expected ~{world_model.effects.get(action_name, ActionEffect(action_name)).avg_cells_changed:.0f} cells change"

    elif phase == PhaseState.RECOVERY:
        # Recovery: use experiment designer to try informative actions
        # but avoid ACTION6 without coords (it does nothing)
        recovery_actions = [a for a in available_action_names if a != "ACTION6"]
        if not recovery_actions:
            recovery_actions = available_action_names

        probe = experiment_designer.suggest_probe(
            belief_ledger=belief_state,
            available_actions=recovery_actions,
            step_budget=max_steps,
            tested_actions=set(action_history),
            current_step=step_index,
        )
        if isinstance(probe.action, str):
            action_name = probe.action
        elif isinstance(probe.action, dict):
            action_name = probe.action.get("action", recovery_actions[0])
        else:
            action_name = recovery_actions[0]
        rationale = f"Recovery: {probe.rationale}"
        expected_outcome = "Gather observation to diagnose failure"

        # Demote the worst-performing hypothesis and exit recovery
        worst_h = None
        worst_conf = float("inf")
        for h in belief_state.hypotheses:
            if h.status in ("active", "provisional") and h.confidence < worst_conf:
                worst_conf = h.confidence
                worst_h = h
        if worst_h:
            worst_h.confidence = max(0.0, worst_h.confidence - 0.15)
            if worst_h.confidence < 0.05:
                worst_h.status = "discarded"
        # Force transition back to epistemic to avoid recovery loop
        phase_manager.evaluate_transition(
            belief_ledger=belief_state,
            surprise_history=surprise_history,
            step=step_index,
            budget_remaining=budget_remaining,
            levels_completed=levels_completed,
            recovery_observation_done=True,
            old_hypothesis_demoted=True,
        )
    else:
        action_name = available_action_names[0] if available_action_names else "ACTION5"
        rationale = "Fallback action"

    # 5b. PREDICT stage: describe expected outcome of the action just selected.
    # This text becomes the RESULT reference on the next solve_step call.
    predict_text, predicted_diff_cells, predicted_diff_low, predicted_diff_high = (
        _build_predict_text(
            action_name=action_name,
            action_data=action_data,
            belief_state=belief_state,
            world_model=world_model,
            expected_outcome=expected_outcome,
            simulator=simulator,
        )
    )

    # 6. Build surprise audit (compare prediction with what actually happened)
    #
    # IMPORTANT: `transitions` reflect the effect of the action that was JUST
    # EXECUTED (i.e. action_history[-1]), not the action we just CHOSE for
    # next execution (action_name). So we audit against beliefs of the
    # just-executed action, not the newly picked one.
    #
    # During early exploration (few actions tested), we have no real predictions.
    # In that case, suppress surprise: mark all observed transitions as
    # "predicted" so the auditor doesn't fire SEVERE for normal exploration.
    executed_action = action_history[-1] if action_history else None
    tested_count = len(set(action_history))
    last_action_ab = (
        belief_state.action_beliefs.get(executed_action) if executed_action else None
    )
    action_still_learning = (last_action_ab is None or last_action_ab.times_used < 3)
    if (tested_count <= len(available_action_names) and step_index <= 15) or action_still_learning:
        # Early exploration or action still being learned: treat all as expected
        predicted_changes = [
            PredictedChange(obj_id=t.obj_id, kind=t.kind, description="auto-predicted (exploration)")
            for t in transitions
        ]
    else:
        # B2-2 enhanced: build predictions from action_beliefs + world model
        predicted_changes = []
        last_action_name = executed_action
        ab = belief_state.action_beliefs.get(last_action_name) if last_action_name else None
        actual_diff = diff_cell_count(prev_grid, grid) if prev_grid else 0

        if ab and ab.times_used > 0 and ab.confidence >= 0.3:
            # Key insight: if the overall magnitude matches expectations,
            # the action behaved as expected even if specific objects differ.
            # This prevents false SEVERE surprises for large-diff actions
            # (e.g., ACTION1=UP causing 96 cells to change every time).
            expected_lo = ab.avg_cells_changed * 0.4
            expected_hi = ab.avg_cells_changed * 2.5
            magnitude_matches = expected_lo <= actual_diff <= expected_hi

            if magnitude_matches and actual_diff > 20:
                # Large action with expected magnitude — auto-predict all
                # transitions to suppress false surprise
                predicted_changes = [
                    PredictedChange(
                        obj_id=t.obj_id, kind=t.kind,
                        description=f"auto-predicted: {last_action_name} "
                                    f"magnitude {actual_diff} within expected "
                                    f"[{expected_lo:.0f}, {expected_hi:.0f}]",
                    )
                    for t in transitions
                ]
            else:
                # Try pid-based predictions for smaller/unexpected changes
                for pid in ab.affected_pids[:5]:
                    matching_t = next(
                        (t for t in transitions
                         if any(o.persistent_id == pid and o.obj_id == t.obj_id
                                for o in current_objects)),
                        None,
                    )
                    if matching_t:
                        predicted_changes.append(
                            PredictedChange(
                                obj_id=matching_t.obj_id,
                                kind=matching_t.kind,
                                description=f"predicted from {last_action_name} "
                                            f"action_belief (pid={pid})",
                            )
                        )

                # Fall back to generic predictions
                if not predicted_changes:
                    for t in transitions[:3]:
                        predicted_changes.append(
                            PredictedChange(
                                obj_id=t.obj_id, kind=t.kind,
                                description=f"predicted from {last_action_name} history",
                            )
                        )
        elif ab and ab.is_noop:
            # Predict no change for noop actions
            pass  # empty predicted_changes → any change will be surprising
        else:
            # Fallback: world model effects
            eff = world_model.effects.get(last_action_name)
            if eff and eff.times_used > 0:
                for t in transitions[:3]:
                    predicted_changes.append(
                        PredictedChange(
                            obj_id=t.obj_id, kind=t.kind,
                            description=f"predicted from {last_action_name} history",
                        )
                    )

    audit_result = audit_step(
        predicted_changes=predicted_changes,
        actual_changes=transitions,
        belief_ledger=belief_state,
        step_index=step_index,
        anti_anchoring_guard=anti_anchoring,
    )
    surprise_report: SurpriseReport = audit_result["report"]
    revision = audit_result["revision"]
    anchoring_alerts = audit_result["alerts"]
    surprise_history.append(surprise_report)

    confidence_update = {
        action.hypothesis_id: (
            f"{action.old_confidence:.2f}->{action.new_confidence:.2f} "
            f"({action.old_status}->{action.new_status}) | {action.reason}"
        )
        for action in revision.actions[:8]
    }
    belief_revision_summary = [
        (
            f"{action.hypothesis_id}: {action.old_confidence:.2f}->{action.new_confidence:.2f} "
            f"({action.new_status})"
        )
        for action in revision.actions[:6]
    ]
    hypothesis_pruning_count = sum(
        1
        for action in revision.actions
        if action.old_status != "discarded" and action.new_status == "discarded"
    )
    belief_revision_score = round(
        min(
            1.0,
            sum(
                abs(action.new_confidence - action.old_confidence)
                for action in revision.actions
            ),
        ),
        3,
    )
    belief_revision_reasons = [
        action.reason for action in revision.actions[:4]
    ]
    if revision.motif_updates:
        belief_revision_reasons.extend(revision.motif_updates[:2])
    if anchoring_alerts:
        belief_revision_reasons.extend(
            alert.detail for alert in anchoring_alerts[:2]
        )
    suggested_hypotheses = revision.suggested_hypotheses[:3]
    motif_updates = revision.motif_updates[:3]
    anchoring_alert_summaries = [alert.detail for alert in anchoring_alerts[:3]]
    dynamics_revision_parts: list[str] = []
    if suggested_hypotheses:
        dynamics_revision_parts.append(
            "Suggested: " + " | ".join(suggested_hypotheses)
        )
    if motif_updates:
        dynamics_revision_parts.append(
            "Motifs: " + " | ".join(motif_updates)
        )
    if anchoring_alert_summaries:
        dynamics_revision_parts.append(
            "Anchoring: " + " | ".join(anchoring_alert_summaries)
        )
    dynamics_revision = (
        "; ".join(dynamics_revision_parts)
        if dynamics_revision_parts
        else "No explicit belief revision summary."
    )

    # 7. Update action semantics in belief ledger (B2-2: structured)
    if prev_grid is not None:
        prev_action = action_history[-1] if action_history else None
        if prev_action:
            n_changed = diff_cell_count(prev_grid, grid)
            desc = f"Changed {n_changed} cells"
            if n_changed == 0:
                desc = "No visible effect"
            # Legacy string-based semantics (backward compat)
            if prev_action not in belief_state.action_semantics:
                belief_state.action_semantics[prev_action] = []
            if len(belief_state.action_semantics[prev_action]) < 5:
                belief_state.action_semantics[prev_action].append(desc)

            # B2-2: Structured action belief update
            from agents.agentic.schemas import ActionSemanticsBelief
            if prev_action not in belief_state.action_beliefs:
                belief_state.action_beliefs[prev_action] = ActionSemanticsBelief(
                    action_name=prev_action
                )
            ab = belief_state.action_beliefs[prev_action]
            ab.times_used += 1
            # Running average of cells changed
            ab.avg_cells_changed = (
                ab.avg_cells_changed * (ab.times_used - 1) + n_changed
            ) / ab.times_used

            # Consistency: did result match expectation?
            expected_range = (ab.avg_cells_changed * 0.5, ab.avg_cells_changed * 2.0)
            if ab.times_used == 1:
                # First use — no expectation yet
                ab.consistent_streak = 1
            elif expected_range[0] <= n_changed <= expected_range[1]:
                ab.consistent_streak += 1
            else:
                ab.consistent_streak = 0

            ab.last_cells_changed = n_changed
            ab.is_noop = (ab.avg_cells_changed < 1.0 and ab.times_used >= 2)
            ab.is_directional = (
                prev_action in {"ACTION1", "ACTION2", "ACTION3", "ACTION4"}
                and ab.avg_cells_changed > 5.0
            )

            # B2-2: Confidence based on consistency
            if ab.times_used >= 2:
                ab.confidence = min(0.3 + 0.15 * ab.consistent_streak, 0.95)
            else:
                ab.confidence = 0.2

            # Track affected persistent IDs
            if current_objects:
                prev_pids = {o.persistent_id for o in (prev_objects or []) if o.persistent_id}
                for obj in current_objects:
                    if obj.persistent_id and obj.persistent_id in prev_pids:
                        # Check if this object moved/changed
                        prev_obj = next(
                            (p for p in (prev_objects or [])
                             if p.persistent_id == obj.persistent_id),
                            None,
                        )
                        if prev_obj and set(prev_obj.cells) != set(obj.cells):
                            if obj.persistent_id not in ab.affected_pids:
                                ab.affected_pids.append(obj.persistent_id)
                                if len(ab.affected_pids) > 10:
                                    ab.affected_pids = ab.affected_pids[-10:]

            # B2-2: Detect reversible pairs (e.g. ACTION1 <-> ACTION2)
            if len(action_history) >= 2 and ab.is_reversible_with is None:
                prev_prev_action = action_history[-2] if len(action_history) >= 2 else None
                if prev_prev_action and prev_prev_action != prev_action:
                    prev_prev_ab = belief_state.action_beliefs.get(prev_prev_action)
                    if prev_prev_ab and prev_prev_ab.avg_cells_changed > 5:
                        # If doing A then B returns to similar state...
                        if n_changed > 5 and abs(n_changed - prev_prev_ab.avg_cells_changed) < 10:
                            ab.is_reversible_with = prev_prev_action
                            prev_prev_ab.is_reversible_with = prev_action

            # Generate description from evidence
            parts = []
            if ab.is_noop:
                parts.append("no effect")
            elif ab.is_directional:
                parts.append(f"directional, ~{ab.avg_cells_changed:.0f} cells")
            else:
                parts.append(f"~{ab.avg_cells_changed:.0f} cells changed")
            if ab.is_reversible_with:
                parts.append(f"reverses {ab.is_reversible_with}")
            if ab.affected_pids:
                parts.append(f"affects {ab.affected_pids[:3]}")
            ab.description = "; ".join(parts)

    # Effect-based motif reassessment: every 5 steps after we have enough
    # action_beliefs, reweight top_motifs based on observed effects so that
    # e.g. `ACTION6 available -> click-semantics` bootstrap bias can be
    # corrected when ACTION6 proves inert.
    if step_index > 0 and step_index % 5 == 0:
        reassessment_notes = reassess_motifs_from_effects(belief_state)
        if reassessment_notes:
            belief_state.notes.append(
                f"MOTIF_REASSESS@{step_index}: " + " | ".join(reassessment_notes[:3])
            )

    # Boost hypothesis confidence modestly as we learn more about actions.
    # We cap at 0.6 because without hypothesis-specific evidence, uniformly
    # boosting all motif hypotheses to near-certainty makes HYPOTHESIZE a
    # no-op — confidences can't distinguish which motif is supported.
    # Above 0.6 must be earned via the BeliefReviser / prediction_hit path.
    n_beliefs = len(belief_state.action_beliefs)
    n_avail = max(len(available_action_names), 1)
    semantics_coverage = min(n_beliefs / n_avail, 1.0)
    for h in belief_state.hypotheses:
        if h.status in ("active", "provisional"):
            target = 0.3 + 0.3 * semantics_coverage  # up to 0.6
            if h.confidence < target:
                h.confidence = min(h.confidence + 0.02, target)

    # 8. Build decision record and trajectory
    diff_cells = 0
    if prev_grid is not None:
        diff_cells = diff_cell_count(prev_grid, grid)

    # B2-3: Build structured belief diff before exporting decision/trace.
    n_strengthened = sum(
        1 for action in revision.actions if action.new_confidence > action.old_confidence
    )
    n_weakened = sum(
        1 for action in revision.actions if action.new_confidence < action.old_confidence
    )
    n_discarded = hypothesis_pruning_count
    max_delta = max(
        (abs(action.new_confidence - action.old_confidence) for action in revision.actions),
        default=0.0,
    )
    belief_diff = BeliefDiff(
        hypotheses_strengthened=n_strengthened,
        hypotheses_weakened=n_weakened,
        hypotheses_discarded=n_discarded,
        hypotheses_suggested=len(suggested_hypotheses),
        motifs_updated=len(motif_updates),
        anchoring_alerts=len(anchoring_alert_summaries),
        max_confidence_delta=round(max_delta, 3),
        summary=dynamics_revision,
    )
    belief_diff_summary = BeliefDiffSummary(
        hypotheses_strengthened=belief_diff.hypotheses_strengthened,
        hypotheses_weakened=belief_diff.hypotheses_weakened,
        hypotheses_discarded=belief_diff.hypotheses_discarded,
        hypotheses_suggested=belief_diff.hypotheses_suggested,
        motifs_updated=belief_diff.motifs_updated,
        anchoring_alerts=belief_diff.anchoring_alerts,
        max_confidence_delta=belief_diff.max_confidence_delta,
        summary=belief_diff.summary,
    )

    decision = DecisionRecord(
        episode_id=belief_state.episode_id,
        game_id=game_id,
        step_index=step_index,
        mode=phase.name.lower(),  # type: ignore[arg-type]
        chosen_action=action_name,
        rationale=rationale,
        expected_outcome=expected_outcome,
        belief_diff=belief_diff_summary,
        belief_revision_summary=belief_revision_summary,
        suggested_hypotheses=suggested_hypotheses,
        motif_updates=motif_updates,
        anchoring_alerts=anchoring_alert_summaries,
    )
    if belief_revision_summary:
        decision.notes.append(
            "Belief revision: " + " | ".join(belief_revision_summary[:2])
        )
    if suggested_hypotheses:
        decision.notes.append(
            "Suggested hypotheses: " + " | ".join(suggested_hypotheses[:2])
        )
    if anchoring_alert_summaries:
        decision.notes.append(
            "Anchoring alerts: " + " | ".join(anchoring_alert_summaries[:2])
        )
    if (
        belief_diff_summary.hypotheses_strengthened
        or belief_diff_summary.hypotheses_weakened
        or belief_diff_summary.hypotheses_discarded
    ):
        decision.notes.append(
            "Belief diff: "
            f"up={belief_diff_summary.hypotheses_strengthened}, "
            f"down={belief_diff_summary.hypotheses_weakened}, "
            f"discarded={belief_diff_summary.hypotheses_discarded}"
        )

    # 8b. Six-stage reasoning chain (OBSERVE/INTERPRET/HYPOTHESIZE/PREDICT/
    # RESULT/REVISE) for SFT-quality logging. See docs/strategy/data-logging-principles.md.
    last_action_name = action_history[-1] if action_history else None
    observe_text = _build_observe_text(
        step_index=step_index,
        actual_diff_cells=diff_cells,
        state_name=state_name,
        levels_completed=levels_completed,
        object_count=len(object_summaries),
        available_actions=available_action_names,
    )
    interpret_text = _build_interpret_text(
        last_action=last_action_name,
        actual_diff_cells=diff_cells,
        belief_state=belief_state,
    )
    hypothesize_text = _build_hypothesize_text(belief_state)
    result_text, prediction_hit = _build_result_text(
        last_pred_text=last_prediction_text,
        last_pred_low=last_prediction_low,
        last_pred_high=last_prediction_high,
        actual_diff_cells=diff_cells,
        surprise_severity=surprise_report.severity,
    )

    # 8c. MISS handler: when the previous-step prediction missed, demote the
    # most-confident dynamics rule for the executed action and surface an
    # explicit note in REVISE. This closes the loop between prediction failure
    # and belief update — independent of surprise_auditor's suppression logic.
    miss_note = ""
    if prediction_hit is False and last_action_name:
        candidate_rules = [
            r for r in belief_state.dynamics_rules
            if r.action_name == last_action_name
        ]
        if candidate_rules:
            top_rule = max(candidate_rules, key=lambda r: r.confidence)
            old_conf = top_rule.confidence
            top_rule.confidence = max(0.0, top_rule.confidence - 0.1)
            top_rule.times_violated += 1
            miss_note = (
                f"Prediction MISS on {last_action_name}: actual {diff_cells} cells "
                f"outside predicted [{last_prediction_low}-{last_prediction_high}]. "
                f"Demoted rule {top_rule.rule_id} ({old_conf:.2f}→{top_rule.confidence:.2f}, "
                f"violations={top_rule.times_violated})."
            )
        else:
            miss_note = (
                f"Prediction MISS on {last_action_name}: actual {diff_cells} cells "
                f"outside predicted [{last_prediction_low}-{last_prediction_high}]. "
                f"No dynamics rule to demote yet."
            )

    revise_text = _build_revise_text(
        dynamics_revision=dynamics_revision,
        belief_revision_summary=belief_revision_summary,
        suggested_hypotheses=suggested_hypotheses,
    )
    if miss_note:
        revise_text = miss_note + " " + revise_text

    # 9. Record to memory
    if memory and curator:
        trajectory = curator.curate(
            observation=obs,
            belief=belief_state,
            decision=decision,
            prediction=predict_text,
            actual_diff=obs.diff_summary,
            surprise=surprise_report.summary,
            surprise_magnitude=(
                0.0 if surprise_report.severity == SurpriseSeverity.NONE else
                0.3 if surprise_report.severity == SurpriseSeverity.MILD else
                0.6 if surprise_report.severity == SurpriseSeverity.MODERATE else
                1.0
            ),
            confidence_update=confidence_update,
            belief_diff=belief_diff_summary,
            belief_revision_summary=belief_revision_summary,
            dynamics_revision=dynamics_revision,
            belief_revision_score=belief_revision_score,
            belief_revision_reasons=belief_revision_reasons,
            hypothesis_pruning_count=hypothesis_pruning_count,
            suggested_hypotheses=suggested_hypotheses,
            motif_updates=motif_updates,
            anchoring_alerts=anchoring_alert_summaries,
            llm_used=llm_used,
            llm_model=llm_model_name,
            observe_text=observe_text,
            interpret_text=interpret_text,
            hypothesize_text=hypothesize_text,
            predict_text=predict_text,
            result_text=result_text,
            revise_text=revise_text,
            predicted_diff_cells=predicted_diff_cells,
            predicted_diff_low=predicted_diff_low,
            predicted_diff_high=predicted_diff_high,
            prediction_hit=prediction_hit,
        )
        memory.write_observation(obs)
        memory.write_belief(belief_state)
        memory.write_decision(decision)
        memory.append_trace(trajectory)

    # 10. Current subgoal info
    active_sg = next(
        (sg for sg in belief_state.active_subgoals if sg.status == "active"),
        None,
    )

    result = StepResult(
        belief_state=belief_state,
        action_taken=action_name,
        diff_cells=diff_cells,
        levels_completed=levels_completed,
        phase=phase,
        surprise_severity=surprise_report.severity,
        belief_diff=belief_diff,
        active_subgoal_type=active_sg.subgoal_type if active_sg else "",
        active_subgoal_id=active_sg.subgoal_id if active_sg else "",
        llm_used=llm_used,
        llm_model=llm_model_name,
        predict_text=predict_text,
        predicted_diff_cells=predicted_diff_cells,
        predicted_diff_low=predicted_diff_low,
        predicted_diff_high=predicted_diff_high,
    )

    return result, current_objects, action_name, action_data


# ===================================================================
# solve_episode: full episode loop
# ===================================================================

@dataclass
class EpisodeResult:
    """Result of a full episode."""
    game_id: str
    episode_id: str
    levels_completed: int
    total_steps: int
    final_state: str
    phase_transitions: int
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    world_model_summary: str = ""
    llm_used: bool = False
    llm_model: str = ""
    llm_memory_window: int = 0


def solve_episode(
    game_id_prefix: str,
    max_steps: int = 200,
    memory_root: str = "data/episodes",
    verbose: bool = True,
    llm_model: str | None = None,
    llm_memory_window: int = 4,
) -> EpisodeResult:
    """Play one full game episode using the agentic solve loop.

    Parameters
    ----------
    game_id_prefix : prefix for the game ID (e.g., "sk48").
    max_steps : maximum actions before stopping.
    memory_root : directory for episode memory storage.
    verbose : print step-by-step progress.

    Returns
    -------
    EpisodeResult with trajectory and levels_completed.
    """
    # --- Initialize game ---
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    envs = arc.get_environments()
    full_game_id = None
    for e in envs:
        if e.game_id.startswith(game_id_prefix):
            full_game_id = e.game_id
            break
    if not full_game_id:
        available = [e.game_id for e in envs]
        raise ValueError(
            f"Game '{game_id_prefix}' not found. Available: {available}"
        )

    env = arc.make(full_game_id)

    # --- Initialize agentic infrastructure ---
    episode_id = f"{full_game_id}-{uuid.uuid4().hex[:8]}"
    phase_manager = PhaseManager()
    probe_history = ProbeHistory()
    experiment_designer = ExperimentDesigner(probe_history=probe_history)
    world_model = WorldModel()
    sim_builder = SimulatorBuilder()
    simulator: Simulator | None = None
    sim_evolution_log: list[SimulatorEvolutionEntry] = []
    surprise_history: list[SurpriseReport] = []
    anti_anchoring = AntiAnchoringGuard()
    curator = TrajectoryCurator()

    # Memory store
    memory = EpisodeMemoryStore.create(
        root_dir=memory_root,
        game_id=full_game_id,
        tags=["solve_loop"],
        notes=[f"max_steps={max_steps}"],
        episode_id=episode_id,
    )

    # --- RESET to start game ---
    reset_action = GameAction.RESET
    reset_action.reasoning = "Episode start"
    raw = env.step(reset_action, data=reset_action.action_data.model_dump(), reasoning={})
    if raw is None:
        raise RuntimeError("Failed to reset game")

    grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
    state = raw.state
    levels = raw.levels_completed
    avail_names = (
        [GameAction.from_id(a).name for a in raw.available_actions]
        if raw.available_actions
        else ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5"]
    )

    # Bootstrap beliefs
    initial_obs = _build_observation(
        game_id=full_game_id,
        step_index=0,
        grid=grid,
        prev_grid=None,
        state_name=state.name,
        levels_completed=levels,
        available_actions=avail_names,
        action_history=["RESET"],
        objects=[],
    )
    motifs = infer_bootstrap_motifs(initial_obs)
    belief_state = bootstrap_belief_ledger(
        episode_id=episode_id,
        observation=initial_obs,
        motif_names=[m.name for m in motifs],
    )
    # Add initial hypotheses based on motifs
    for i, motif in enumerate(motifs[:3]):
        belief_state.hypotheses.append(
            HypothesisEntry(
                hypothesis_id=f"H{i}",
                summary=f"Game follows a '{motif.name}' motif.",
                confidence=motif.confidence,
                status="provisional",
                predicted_observations=[
                    f"Actions will produce '{motif.name}'-style changes."
                ],
                evidence=motif.evidence,
            )
        )
    # If no motifs, add a generic hypothesis
    if not belief_state.hypotheses:
        belief_state.hypotheses.append(
            HypothesisEntry(
                hypothesis_id="H0",
                summary="Unknown game dynamics.",
                confidence=0.3,
                status="provisional",
            )
        )

    if verbose:
        print(f"{'='*60}")
        print(f"  SOLVE EPISODE: {full_game_id}")
        print(f"  Episode ID:    {episode_id}")
        print(f"  Max steps:     {max_steps}")
        print(f"  Grid:          {len(grid)}x{len(grid[0]) if grid else 0}")
        print(f"  Available:     {avail_names}")
        print(f"  Motifs:        {[m.name for m in motifs]}")
        print(f"{'='*60}")

    # --- P1-1 / P1-2: persistent tracking and role scoring ---
    persistent_tracker = PersistentObjectTracker()
    role_scorer = RoleScorer()
    subgoal_planner = SubgoalPlanner()

    # --- LLM Brain (optional) ---
    llm_brain = None
    if llm_model:
        from agents.agentic.llm_brain import LLMBrain
        llm_brain = LLMBrain(model=llm_model, memory_window=llm_memory_window)
        if verbose:
            print(f"  LLM Brain:     {llm_model}")
            print(f"  LLM Memory:    {llm_memory_window}")

    # --- Main loop ---
    prev_grid: list[list[int]] | None = None
    prev_objects: list[PerceivedObject] | None = None
    action_history: list[str] = ["RESET"]
    trajectory_log: list[dict[str, Any]] = []
    step_index = 0
    max_levels = levels
    # Carry the previous step's PREDICT output into the next solve_step so its
    # RESULT stage can verify actual-vs-predicted diff automatically.
    last_prediction_text: str | None = None
    last_prediction_low: int | None = None
    last_prediction_high: int | None = None

    for step_index in range(1, max_steps + 1):
        # Check terminal conditions before solving
        if state == GameState.WIN:
            if verbose:
                print(f"\n  WIN at step {step_index - 1}!")
            break

        # If GAME_OVER, reset and continue
        if state == GameState.GAME_OVER:
            if verbose:
                print(f"  Step {step_index}: GAME_OVER -> RESET")
            reset_action = GameAction.RESET
            reset_action.reasoning = f"GAME_OVER at step {step_index}"
            raw = env.step(reset_action, data=reset_action.action_data.model_dump(), reasoning={})
            if raw is None:
                break
            grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
            state = raw.state
            levels = raw.levels_completed
            avail_names = (
                [GameAction.from_id(a).name for a in raw.available_actions]
                if raw.available_actions
                else avail_names
            )
            prev_grid = None
            prev_objects = None
            action_history.append("RESET")
            continue

        # NOT_PLAYED: need reset
        if state == GameState.NOT_PLAYED:
            reset_action = GameAction.RESET
            reset_action.reasoning = f"NOT_PLAYED at step {step_index}"
            raw = env.step(reset_action, data=reset_action.action_data.model_dump(), reasoning={})
            if raw is None:
                break
            grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
            state = raw.state
            levels = raw.levels_completed
            avail_names = (
                [GameAction.from_id(a).name for a in raw.available_actions]
                if raw.available_actions
                else avail_names
            )
            prev_grid = None
            prev_objects = None
            action_history.append("RESET")
            continue

        # --- Solve step ---
        result, current_objects, chosen_action, chosen_action_data = solve_step(
            grid=grid,
            prev_grid=prev_grid,
            prev_objects=prev_objects,
            game_id=full_game_id,
            step_index=step_index,
            state_name=state.name,
            levels_completed=levels,
            available_action_names=avail_names,
            action_history=action_history,
            belief_state=belief_state,
            phase_manager=phase_manager,
            experiment_designer=experiment_designer,
            world_model=world_model,
            surprise_history=surprise_history,
            anti_anchoring=anti_anchoring,
            max_steps=max_steps,
            memory=memory,
            curator=curator,
            persistent_tracker=persistent_tracker,
            role_scorer=role_scorer,
            subgoal_planner=subgoal_planner,
            simulator=simulator,
            simulator_builder=sim_builder,
            llm_brain=llm_brain,
            last_prediction_text=last_prediction_text,
            last_prediction_low=last_prediction_low,
            last_prediction_high=last_prediction_high,
        )
        # Stash prediction for next iteration's RESULT verification.
        last_prediction_text = result.predict_text or None
        last_prediction_low = result.predicted_diff_low
        last_prediction_high = result.predicted_diff_high

        # --- Execute the chosen action in the environment ---
        ga, extra_data = _resolve_action(chosen_action)
        # Merge coordinate data from LLM brain (or other sources)
        if chosen_action_data:
            extra_data.update(chosen_action_data)
        # Clamp coordinates to valid [0, 63] grid range — LLMs sometimes
        # emit y=64 or x=64 (off-by-one from 64x64 grid). Unclamped, pydantic
        # raises ValidationError and kills the episode.
        if "x" in extra_data:
            extra_data["x"] = max(0, min(63, int(extra_data["x"])))
        if "y" in extra_data:
            extra_data["y"] = max(0, min(63, int(extra_data["y"])))
        if extra_data:
            ga.set_data(extra_data)
        ga.reasoning = f"Step {step_index}: {result.phase.name} | {chosen_action}"

        prev_grid = [row[:] for row in grid]
        prev_objects = current_objects

        raw = env.step(ga, data=ga.action_data.model_dump(), reasoning={})
        if raw is None:
            if verbose:
                print(f"  Step {step_index}: {chosen_action} -> ERROR (no frame)")
            continue

        new_grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else grid
        new_state = raw.state
        new_levels = raw.levels_completed
        new_avail = (
            [GameAction.from_id(a).name for a in raw.available_actions]
            if raw.available_actions
            else avail_names
        )

        # Update world model
        n_diff = diff_cell_count(grid, new_grid)
        world_model.record_action(
            action_name=chosen_action,
            diff_cells=n_diff,
            levels_before=levels,
            levels_after=new_levels,
        )

        # --- Simulator: build / verify / update ---
        # Build simulator once we have enough dynamics rules (after ~5 steps)
        if simulator is None and len(belief_state.dynamics_rules) >= 2:
            try:
                simulator = sim_builder.build_from_belief(
                    belief_state,
                    objects=current_objects,
                    grid=new_grid,
                    available_actions=avail_names,
                )
                snap = simulator.snapshot(step_index, trigger="initial")
                sim_evolution_log.append(SimulatorEvolutionEntry(
                    step_index=step_index,
                    version_before=0,
                    version_after=0,
                    trigger="initial_build",
                    rules_added=[m.summary() for m in simulator.mechanics],
                ))
                if verbose:
                    print(f"  [SIM] Built v{simulator.version}: {len(simulator.mechanics)} mechanics, avg_conf={simulator.avg_confidence:.2f}")
            except Exception as e:
                logger.warning("Failed to build simulator: %s", e)

        # Update simulator on surprise (prediction mismatch)
        elif simulator and result.surprise_severity in (SurpriseSeverity.MODERATE, SurpriseSeverity.SEVERE):
            try:
                simulator, evo_entry = sim_builder.update_from_surprise(
                    simulator,
                    step_index=step_index,
                    prediction_summary=f"action={chosen_action}",
                    actual_summary=f"diff={n_diff}, state={new_state.name}",
                    new_dynamics=belief_state.dynamics_rules,
                )
                sim_evolution_log.append(evo_entry)
                if verbose:
                    print(f"  [SIM] Updated v{simulator.version}: {evo_entry.trigger} (+{len(evo_entry.rules_added)} -{len(evo_entry.rules_removed)})")
            except Exception as e:
                logger.warning("Failed to update simulator: %s", e)
        elif simulator:
            # Prediction was correct — boost confidence
            sim_builder.confirm_prediction(simulator)

        # Detect level-up
        if new_levels > levels:
            world_model.level_up_sequences.append(list(action_history[-10:]))
            # Reset perception trackers for new level (new scene)
            persistent_tracker.reset()
            role_scorer.reset()
            # Reset simulator for new level (mechanics may differ)
            if simulator:
                if verbose:
                    print(f"  [SIM] Level change — will rebuild simulator")
                simulator = None
            # Stale prediction from previous level — drop it.
            last_prediction_text = None
            last_prediction_low = None
            last_prediction_high = None
            if verbose:
                print(f"  *** LEVEL UP: {levels} -> {new_levels} ***")

        max_levels = max(max_levels, new_levels)

        # Log step
        step_log = {
            "step": step_index,
            "phase": result.phase.name,
            "action": chosen_action,
            "diff_cells": n_diff,
            "levels": new_levels,
            "surprise": result.surprise_severity.name,
            "state": new_state.name,
            "llm_used": result.llm_used,
            "llm_model": result.llm_model,
            "llm_memory_window": llm_memory_window if result.llm_used else 0,
        }
        trajectory_log.append(step_log)

        if verbose:
            surprise_marker = ""
            if result.surprise_severity == SurpriseSeverity.MODERATE:
                surprise_marker = " [!MODERATE]"
            elif result.surprise_severity == SurpriseSeverity.SEVERE:
                surprise_marker = " [!!SEVERE]"
            level_marker = f" L{new_levels}" if new_levels > 0 else ""
            print(
                f"  Step {step_index:3d}: "
                f"{result.phase.name:13s} | "
                f"{chosen_action:8s} | "
                f"diff={n_diff:3d}"
                f"{level_marker}"
                f"{surprise_marker}"
            )

        # Update state for next iteration
        grid = new_grid
        state = new_state
        levels = new_levels
        avail_names = new_avail
        action_history.append(chosen_action)
        belief_state = result.belief_state

    # --- Episode complete ---
    if verbose:
        print(f"\n{'='*60}")
        print(f"  EPISODE COMPLETE")
        print(f"  Total steps:      {step_index}")
        print(f"  Levels completed: {max_levels}")
        print(f"  Final state:      {state.name}")
        print(f"  Phase transitions: {len(phase_manager.history)}")
        print(f"\n{world_model.summary()}")
        if llm_brain:
            print(f"\n{llm_brain.token_summary()}")
        print(f"\n{phase_manager.summary()}")
        print(f"{'='*60}")

    # Save simulator evolution log
    if memory and sim_evolution_log:
        for evo_entry in sim_evolution_log:
            memory.append_simulator_evolution(evo_entry)
        if simulator:
            memory.write_simulator_snapshot(simulator.snapshot(step_index, trigger="final"))
        if verbose:
            print(f"  [SIM] Saved {len(sim_evolution_log)} evolution entries")

    return EpisodeResult(
        game_id=full_game_id,
        episode_id=episode_id,
        levels_completed=max_levels,
        total_steps=step_index,
        final_state=state.name,
        phase_transitions=len(phase_manager.history),
        trajectory=trajectory_log,
        world_model_summary=world_model.summary(),
        llm_used=any(bool(step.get("llm_used")) for step in trajectory_log),
        llm_model=llm_model or "",
        llm_memory_window=llm_memory_window if llm_model else 0,
    )


# ===================================================================
# CLI
# ===================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agentic Solve Loop for ARC-AGI-3",
    )
    parser.add_argument(
        "--game", required=True,
        help="Game ID prefix (e.g., sk48, ls20)",
    )
    parser.add_argument(
        "--max-steps", type=int, default=200,
        help="Maximum steps per episode (default: 200)",
    )
    parser.add_argument(
        "--memory-root", type=str, default="data/episodes",
        help="Root directory for episode memory (default: data/episodes)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress step-by-step output",
    )
    parser.add_argument(
        "--llm-model", type=str, default=None,
        help="LLM model name to use as brain (e.g., claude-sonnet-4-20250514)",
    )
    parser.add_argument(
        "--llm-memory-window", type=int, default=4,
        help="Rolling compact reasoning memory size for the LLM brain (default: 4)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        result = solve_episode(
            game_id_prefix=args.game,
            max_steps=args.max_steps,
            memory_root=args.memory_root,
            verbose=not args.quiet,
            llm_model=args.llm_model,
            llm_memory_window=args.llm_memory_window,
        )
        print(f"\nResult: levels_completed={result.levels_completed}, "
              f"steps={result.total_steps}, state={result.final_state}")
        sys.exit(0 if result.levels_completed > 0 else 1)
    except Exception as e:
        logger.error(f"Episode failed: {e}")
        raise


if __name__ == "__main__":
    main()
