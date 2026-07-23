# [Mar 31] LLM Brain for solve_loop.
# Created by SD with Claude Opus 4.6.

"""LLM Brain: pluggable reasoning module for solve_loop.

Replaces heuristic decision-making with LLM inference.
Takes the current structured state (belief, objects, dynamics, regions)
and asks the LLM to choose an action + provide reasoning.

Usage:
    brain = LLMBrain(model="gpt-5.4-mini")
    action, rationale, extras = brain.decide(...)
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BrainDecision:
    """Output from the LLM brain."""
    action: str = "ACTION1"            # e.g. "ACTION1"
    action_data: dict | None = None    # for ACTION6: {"x": 10, "y": 20}
    rationale: str = ""                # LLM's reasoning
    expected_outcome: str = ""         # what it thinks will happen
    dynamics_update: str = ""          # any new rule discovered
    goal_hypothesis: str = ""          # what it thinks the goal is
    # Extended fields — LLM fills what templates used to fill
    motifs: dict[str, float] = field(default_factory=dict)       # motif -> confidence
    hypotheses: list[dict] = field(default_factory=list)          # [{id, summary, confidence}]
    object_labels: dict[str, str] = field(default_factory=dict)  # pid -> label
    surprise_interpretation: str = ""   # WHY something was unexpected
    phase_reasoning: str = ""           # WHY this phase is appropriate
    reference_interpretation: str = ""  # WHAT the reference pattern means
    raw_response: str = ""             # full LLM output for logging


@dataclass
class RollingMemoryEntry:
    """One step's compact reasoning memory."""
    step: int
    action: str
    why: str              # why this action was chosen (1 sentence)
    surprise: str         # what was unexpected ("none" if nothing)
    learned: str          # what hypothesis/rule changed ("none" if nothing)
    unresolved: str       # what remains unknown ("none" if nothing)
    clicked_coordinate: tuple[int, int] | None = None
    target_pid: str | None = None
    target_region_id: str | None = None
    outcome_class: str = "pending"
    candidate_status: str = "unknown"
    avoid_note: str = "none"
    levels_completed_at_decision: int = 0


class LLMBrain:
    """Pluggable LLM reasoning for solve_loop."""

    def __init__(
        self,
        model: str = "gpt-5.4-mini",
        max_tokens: int = 512,
        temperature: float = 0.3,
        memory_window: int = 4,
    ):
        from openai import OpenAI
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.memory_window = memory_window
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._call_count = 0
        # Rolling memory: compact reasoning trail
        self._memory: list[RollingMemoryEntry] = []
        # Cumulative working theory (updated by LLM each step)
        self._working_theory: str = ""

    def decide(
        self,
        # Current state
        grid_summary: str,
        objects: list[dict],
        diff_summary: str,
        # Belief state
        dynamics_rules: list[dict],
        interaction_rules: list[dict],
        regions: list[dict],
        reference_patterns: list[dict],
        hypotheses: list[dict],
        action_beliefs: dict[str, dict],
        goal_beliefs: list[dict],
        # Context
        available_actions: list[str],
        action_history: list[str],
        phase: str,
        step_index: int,
        levels_completed: int,
        energy_fraction: float,
        last_surprise: str = "",
    ) -> BrainDecision:
        """Ask the LLM to choose the next action."""

        self._backfill_previous_outcome(
            diff_summary=diff_summary,
            last_surprise=last_surprise,
            levels_completed=levels_completed,
        )

        prompt = self._build_prompt(
            grid_summary=grid_summary,
            objects=objects,
            diff_summary=diff_summary,
            dynamics_rules=dynamics_rules,
            interaction_rules=interaction_rules,
            regions=regions,
            reference_patterns=reference_patterns,
            hypotheses=hypotheses,
            action_beliefs=action_beliefs,
            goal_beliefs=goal_beliefs,
            available_actions=available_actions,
            action_history=action_history,
            phase=phase,
            step_index=step_index,
            levels_completed=levels_completed,
            energy_fraction=energy_fraction,
            last_surprise=last_surprise,
        )

        try:
            # GPT 5.x models use max_completion_tokens instead of max_tokens
            token_param = {}
            if "gpt-5" in self.model or "o1" in self.model or "o3" in self.model:
                token_param["max_completion_tokens"] = self.max_tokens
            else:
                token_param["max_tokens"] = self.max_tokens

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                **token_param,
            )
            raw = response.choices[0].message.content or ""
            self._total_input_tokens += response.usage.prompt_tokens if response.usage else 0
            self._total_output_tokens += response.usage.completion_tokens if response.usage else 0
            self._call_count += 1
        except Exception as e:
            logger.error(f"LLM Brain error: {e}")
            return BrainDecision(
                action=available_actions[0] if available_actions else "ACTION1",
                rationale=f"LLM error: {e}",
                raw_response=str(e),
            )

        decision = self._parse_response(raw, available_actions)

        # Update rolling memory from this decision
        self._append_memory_from_decision(
            decision=decision,
            step_index=step_index,
            objects=objects,
            regions=regions,
            levels_completed=levels_completed,
        )

        # Update working theory from GOAL + DYNAMICS
        if decision.goal_hypothesis:
            self._working_theory = decision.goal_hypothesis
        if decision.dynamics_update and decision.dynamics_update not in self._working_theory:
            self._working_theory += f" | {decision.dynamics_update[:60]}"
            # Keep it compact
            if len(self._working_theory) > 300:
                self._working_theory = self._working_theory[-300:]

        return decision

    def token_summary(self) -> str:
        return (f"LLM Brain: {self._call_count} calls, "
                f"{self._total_input_tokens} in / {self._total_output_tokens} out tokens, "
                f"memory={len(self._memory)} steps")

    def reset_memory(self) -> None:
        """Clear rolling memory (call on level change)."""
        self._memory.clear()
        self._working_theory = ""

    def _append_memory_from_decision(
        self,
        decision: BrainDecision,
        step_index: int,
        objects: list[dict[str, Any]],
        regions: list[dict[str, Any]],
        levels_completed: int,
    ) -> None:
        clicked_coordinate: tuple[int, int] | None = None
        target_pid: str | None = None
        target_region_id: str | None = None
        candidate_status = "movement_probe"

        if decision.action == "ACTION6" and decision.action_data:
            x = int(decision.action_data.get("x", 0))
            y = int(decision.action_data.get("y", 0))
            clicked_coordinate = (x, y)
            target_pid = self._find_target_pid(objects, x, y)
            target_region_id = self._find_target_region_id(regions, x, y)
            candidate_status = "probing_candidate"
            if target_pid is None and target_region_id is None:
                candidate_status = "coordinate_probe"
        elif decision.action == "RESET":
            candidate_status = "reset"

        self._memory.append(
            RollingMemoryEntry(
                step=step_index,
                action=decision.action,
                why=decision.rationale[:100] if decision.rationale else "",
                surprise=decision.surprise_interpretation[:80] if decision.surprise_interpretation else "none",
                learned=decision.dynamics_update[:80] if decision.dynamics_update else "none",
                unresolved=decision.phase_reasoning[:80] if decision.phase_reasoning else "none",
                clicked_coordinate=clicked_coordinate,
                target_pid=target_pid,
                target_region_id=target_region_id,
                candidate_status=candidate_status,
                levels_completed_at_decision=levels_completed,
            )
        )
        self._trim_memory_to_window()

    def _backfill_previous_outcome(
        self,
        diff_summary: str,
        last_surprise: str,
        levels_completed: int,
    ) -> None:
        if not self._memory:
            return

        previous = self._memory[-1]
        if previous.outcome_class != "pending":
            return

        previous.outcome_class = self._classify_outcome(
            diff_summary=diff_summary,
            previous_levels=previous.levels_completed_at_decision,
            current_levels=levels_completed,
        )
        if last_surprise and previous.surprise == "none":
            previous.surprise = last_surprise[:80]

        if previous.action == "ACTION6":
            if previous.outcome_class == "no_change":
                previous.candidate_status = "confirmed_inert"
                target_hint = self._target_hint(previous)
                if target_hint:
                    previous.avoid_note = f"avoid retrying {target_hint}"
            elif previous.outcome_class in {"local_change", "global_change", "level_up"}:
                previous.candidate_status = "likely_active"
            elif previous.outcome_class == "surprising_change":
                previous.candidate_status = "ambiguous"

    def _trim_memory_to_window(self) -> None:
        if self.memory_window <= 0:
            self._memory.clear()
            return
        if len(self._memory) > self.memory_window:
            self._memory = self._memory[-self.memory_window:]

    @staticmethod
    def _classify_outcome(
        diff_summary: str,
        previous_levels: int,
        current_levels: int,
    ) -> str:
        if current_levels > previous_levels:
            return "level_up"

        summary = (diff_summary or "").strip()
        if not summary or summary.upper() == "INITIAL":
            return "unknown"

        summary_upper = summary.upper()
        if "NO CHANGE" in summary_upper:
            return "no_change"

        match = re.search(r"(\d+)\s+cells?\s+changed", summary, re.IGNORECASE)
        if match:
            changed = int(match.group(1))
            if changed == 0:
                return "no_change"
            if changed >= 32:
                return "global_change"
            return "local_change"

        return "surprising_change"

    @staticmethod
    def _find_target_pid(objects: list[dict[str, Any]], x: int, y: int) -> str | None:
        matches: list[dict[str, Any]] = []
        for obj in objects:
            if (
                obj.get("row_min", 0) <= y <= obj.get("row_max", -1)
                and obj.get("col_min", 0) <= x <= obj.get("col_max", -1)
            ):
                matches.append(obj)

        if not matches:
            return None

        matches.sort(
            key=lambda obj: (
                ((obj.get("row_max", 0) - obj.get("row_min", 0) + 1)
                 * (obj.get("col_max", 0) - obj.get("col_min", 0) + 1)),
                obj.get("cell_count", 0),
            )
        )
        best = matches[0]
        return best.get("persistent_id") or best.get("obj_id")

    @staticmethod
    def _find_target_region_id(regions: list[dict[str, Any]], x: int, y: int) -> str | None:
        matches: list[dict[str, Any]] = []
        for region in regions:
            if (
                region.get("row_min", 0) <= y <= region.get("row_max", -1)
                and region.get("col_min", 0) <= x <= region.get("col_max", -1)
            ):
                matches.append(region)

        if not matches:
            return None

        def _priority(region: dict[str, Any]) -> tuple[int, int]:
            role = region.get("role", "unknown")
            specificity = 2
            if role not in {"unknown", "play_area"}:
                specificity = 0
            elif role == "play_area":
                specificity = 1
            area = (
                (region.get("row_max", 0) - region.get("row_min", 0) + 1)
                * (region.get("col_max", 0) - region.get("col_min", 0) + 1)
            )
            return specificity, area

        matches.sort(key=_priority)
        best = matches[0]
        return best.get("region_id") or best.get("name")

    @staticmethod
    def _target_hint(memory: RollingMemoryEntry) -> str:
        if memory.target_pid and memory.target_region_id:
            return f"{memory.target_pid} in {memory.target_region_id}"
        if memory.target_pid:
            return memory.target_pid
        if memory.target_region_id:
            return memory.target_region_id
        if memory.clicked_coordinate:
            x, y = memory.clicked_coordinate
            return f"({x},{y})"
        return ""

    @staticmethod
    def _system_prompt() -> str:
        return """You are an ARC-AGI-3 game-solving agent. You play turn-based 2D grid games where you must discover the rules and goals through observation. You are NEVER told the objective — you must infer it.

You will receive structured state information. Your job is to reason about the game and choose the next action.

Reply in this exact format (every field required):
ACTION: <action name, e.g. ACTION1>
COORDINATES: <x,y if ACTION6, otherwise "none">
REASONING: <1-3 sentences explaining why this action>
EXPECTED: <what you predict will happen>
MOTIFS: <game type guesses with confidence, e.g. "navigation 0.5, threading 0.3, push-puzzle 0.2">
HYPOTHESES: <H1(0.7): specific testable hypothesis | H2(0.3): alternative hypothesis>
OBJECT_LABELS: <pid=role pairs, e.g. "P_ctrl=player, P_◆9=target, P_▓5=wall">
DYNAMICS: <any rule you learned or updated, or "none">
GOAL: <your best guess about the win condition>
SURPRISE: <if last observation was unexpected, explain WHY — or "none">
PHASE: <should we keep exploring or start executing? why?>
REFERENCE: <what does the reference pattern mean for solving? or "none">

Keep each field to 1-2 sentences max. Focus on what changed since last step."""

    def _build_prompt(self, **kwargs) -> str:
        parts = []

        parts.append(f"Step {kwargs['step_index']} | Level {kwargs['levels_completed']} | "
                     f"Phase: {kwargs['phase']} | Energy: {kwargs['energy_fraction']:.0%}")
        parts.append(f"Available actions: {', '.join(kwargs['available_actions'])}")
        parts.append(f"Last 10 actions: {kwargs['action_history'][-10:]}")

        if kwargs['last_surprise']:
            parts.append(f"LAST SURPRISE: {kwargs['last_surprise']}")

        parts.append(f"\nLAST DIFF: {kwargs['diff_summary']}")

        # Objects (top 8 by role score)
        objs = kwargs['objects']
        if objs:
            objs_sorted = sorted(objs, key=lambda o: max(
                o.get('controllable_score', 0), o.get('goal_score', 0),
                o.get('blocker_score', 0), o.get('click_score', 0)
            ), reverse=True)[:8]
            parts.append("\nOBJECTS:")
            for o in objs_sorted:
                pid = o.get('persistent_id', '?')
                scores = []
                if o.get('controllable_score', 0) > 0.1:
                    scores.append(f"ctrl={o['controllable_score']:.1f}")
                if o.get('goal_score', 0) > 0.1:
                    scores.append(f"goal={o['goal_score']:.1f}")
                if o.get('blocker_score', 0) > 0.1:
                    scores.append(f"block={o['blocker_score']:.1f}")
                if o.get('click_score', 0) > 0.1:
                    scores.append(f"click={o['click_score']:.1f}")
                score_str = " " + " ".join(scores) if scores else ""
                parts.append(
                    f"  {pid} val={o['value']} char={o['char']} "
                    f"cells={o['cell_count']} "
                    f"bbox=({o['row_min']},{o['col_min']})-({o['row_max']},{o['col_max']})"
                    f"{score_str}"
                )

        # Dynamics rules
        rules = kwargs['dynamics_rules']
        if rules:
            top_rules = sorted(rules, key=lambda r: r.get('confidence', 0), reverse=True)[:4]
            parts.append("\nKNOWN DYNAMICS:")
            for r in top_rules:
                parts.append(f"  {r.get('action_name','?')}: {r.get('effect','')} "
                            f"(conf={r.get('confidence',0):.2f}, verified={r.get('times_verified',0)}x)")

        # Interaction rules
        interactions = kwargs['interaction_rules']
        if interactions:
            parts.append("\nINTERACTIONS:")
            for ir in interactions[:3]:
                parts.append(f"  {ir.get('trigger_pid','')} -> {ir.get('affected_pid','')}: "
                            f"{ir.get('effect','')} (conf={ir.get('confidence',0):.2f})")

        # Regions
        regions = kwargs['regions']
        if regions:
            named = [r for r in regions if r.get('role') != 'unknown'][:5]
            if named:
                parts.append("\nREGIONS:")
                for r in named:
                    parts.append(f"  {r.get('name','?')} ({r.get('role','?')}) "
                                f"bbox=({r.get('row_min',0)},{r.get('col_min',0)})-"
                                f"({r.get('row_max',0)},{r.get('col_max',0)}) "
                                f"traversable={r.get('traversable',True)}")

        # Reference patterns
        ref_pats = kwargs['reference_patterns']
        if ref_pats:
            parts.append("\nREFERENCE PATTERNS:")
            for rp in ref_pats[:2]:
                rows_str = " / ".join(rp.get('pattern_rows', [])[:4])
                parts.append(f"  {rp.get('surface_id','?')} at "
                            f"({rp.get('row_min',0)},{rp.get('col_min',0)})-"
                            f"({rp.get('row_max',0)},{rp.get('col_max',0)}): "
                            f"{rows_str}")
                if rp.get('pattern_description'):
                    parts.append(f"    desc: {rp['pattern_description']}")

        # Hypotheses
        hyps = kwargs['hypotheses']
        if hyps:
            active = [h for h in hyps if h.get('status') in ('active', 'provisional')][:3]
            if active:
                parts.append("\nHYPOTHESES:")
                for h in active:
                    parts.append(f"  {h.get('hypothesis_id','?')}: {h.get('summary','')} "
                                f"(conf={h.get('confidence',0):.2f}, {h.get('status','')})")

        # Action beliefs
        ab = kwargs['action_beliefs']
        if ab:
            parts.append("\nACTION KNOWLEDGE:")
            for aname, belief in ab.items():
                desc = belief.get('description', '')
                conf = belief.get('confidence', 0)
                parts.append(f"  {aname}: {desc} (conf={conf:.2f})")

        # Goal beliefs
        goals = kwargs['goal_beliefs']
        if goals:
            parts.append("\nGOAL BELIEFS:")
            for g in goals[:2]:
                parts.append(f"  {g.get('summary','')} (conf={g.get('confidence',0):.2f})")

        # Grid summary (compressed)
        grid = kwargs['grid_summary']
        if grid:
            # Only include first 10 lines to save tokens
            grid_lines = grid.split('\n')[:10]
            parts.append(f"\nGRID (first 10 rows):\n" + "\n".join(grid_lines))

        # Rolling memory: recent reasoning trail
        if self._memory:
            parts.append("\nRECENT REASONING (last few steps):")
            for m in self._memory:
                target_bits: list[str] = []
                if m.clicked_coordinate:
                    x, y = m.clicked_coordinate
                    target_bits.append(f"@({x},{y})")
                if m.target_pid:
                    target_bits.append(m.target_pid)
                if m.target_region_id:
                    target_bits.append(m.target_region_id)
                target_str = f" {'/'.join(target_bits)}" if target_bits else ""
                line = f"  Step {m.step}: {m.action}{target_str} — {m.why}"
                if m.outcome_class != "pending":
                    line += f" [OUTCOME: {m.outcome_class}]"
                if m.candidate_status not in {"unknown", ""}:
                    line += f" [STATUS: {m.candidate_status}]"
                if m.surprise != "none":
                    line += f" [SURPRISE: {m.surprise}]"
                if m.learned != "none":
                    line += f" [LEARNED: {m.learned}]"
                if m.unresolved != "none":
                    line += f" [OPEN: {m.unresolved}]"
                if m.avoid_note != "none":
                    line += f" [AVOID: {m.avoid_note}]"
                parts.append(line)

        # Working theory: cumulative understanding
        if self._working_theory:
            parts.append(f"\nWORKING THEORY: {self._working_theory}")

        return "\n".join(parts)

    @staticmethod
    def _parse_response(raw: str, available_actions: list[str]) -> BrainDecision:
        """Parse the LLM's structured response."""
        decision = BrainDecision(raw_response=raw)

        # Parse ACTION
        action_match = re.search(r'ACTION:\s*(\S+)', raw)
        if action_match:
            action = action_match.group(1).upper()
            # Normalize
            if action in available_actions:
                decision.action = action
            elif action.startswith("ACTION") and action in {
                "ACTION1", "ACTION2", "ACTION3", "ACTION4",
                "ACTION5", "ACTION6", "ACTION7", "RESET",
            }:
                decision.action = action
            else:
                decision.action = available_actions[0] if available_actions else "ACTION1"
        else:
            decision.action = available_actions[0] if available_actions else "ACTION1"

        # Parse COORDINATES for ACTION6
        coord_match = re.search(r'COORDINATES:\s*(\d+)\s*,\s*(\d+)', raw)
        if coord_match and decision.action == "ACTION6":
            x, y = int(coord_match.group(1)), int(coord_match.group(2))
            decision.action_data = {"x": x, "y": y}

        # Parse REASONING
        reason_match = re.search(r'REASONING:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if reason_match:
            decision.rationale = reason_match.group(1).strip()

        # Parse EXPECTED
        expected_match = re.search(r'EXPECTED:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if expected_match:
            decision.expected_outcome = expected_match.group(1).strip()

        # Parse DYNAMICS
        dynamics_match = re.search(r'DYNAMICS:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if dynamics_match:
            d = dynamics_match.group(1).strip()
            if d.lower() != "none":
                decision.dynamics_update = d

        # Parse GOAL
        goal_match = re.search(r'GOAL:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if goal_match:
            g = goal_match.group(1).strip()
            if g.lower() != "unknown":
                decision.goal_hypothesis = g

        # Parse MOTIFS: "navigation 0.5, threading 0.3, push-puzzle 0.2"
        motifs_match = re.search(r'MOTIFS:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if motifs_match:
            motif_str = motifs_match.group(1).strip()
            for pair in motif_str.split(","):
                pair = pair.strip()
                parts = pair.rsplit(None, 1)
                if len(parts) == 2:
                    try:
                        decision.motifs[parts[0].strip()] = float(parts[1])
                    except ValueError:
                        pass

        # Parse HYPOTHESES: "H1(0.7): description | H2(0.3): description"
        hyp_match = re.search(r'HYPOTHESES:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if hyp_match:
            hyp_str = hyp_match.group(1).strip()
            for part in hyp_str.split("|"):
                part = part.strip()
                h_match = re.match(r'(H\d+)\(([0-9.]+)\):\s*(.+)', part)
                if h_match:
                    decision.hypotheses.append({
                        "id": h_match.group(1),
                        "confidence": float(h_match.group(2)),
                        "summary": h_match.group(3).strip(),
                    })

        # Parse OBJECT_LABELS: "P_ctrl=player, P_◆9=target"
        labels_match = re.search(r'OBJECT_LABELS:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if labels_match:
            label_str = labels_match.group(1).strip()
            for pair in label_str.split(","):
                pair = pair.strip()
                if "=" in pair:
                    pid, label = pair.split("=", 1)
                    decision.object_labels[pid.strip()] = label.strip()

        # Parse SURPRISE
        surp_match = re.search(r'SURPRISE:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if surp_match:
            s = surp_match.group(1).strip()
            if s.lower() != "none":
                decision.surprise_interpretation = s

        # Parse PHASE
        phase_match = re.search(r'PHASE:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if phase_match:
            decision.phase_reasoning = phase_match.group(1).strip()

        # Parse REFERENCE
        ref_match = re.search(r'REFERENCE:\s*(.+?)(?:\n[A-Z]+:|$)', raw, re.DOTALL)
        if ref_match:
            r = ref_match.group(1).strip()
            if r.lower() != "none":
                decision.reference_interpretation = r

        return decision
