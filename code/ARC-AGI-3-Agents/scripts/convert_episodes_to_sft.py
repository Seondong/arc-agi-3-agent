# [Mar 31] SFT Data Converter for ARC-AGI-3.
# Created by SD with Claude Opus 4.6.
# [Mar 31] Updated by SD with GPT-5.4.
"""Convert agentic solve_loop episode data into SFT training format for Qwen.

Reads the structured per-step outputs under dynamics/{game}/{episode_id}/steps/
and produces a JSONL file where each line is a chat-style training example
suitable for Qwen 4B (or 0.8B) fine-tuning.

Usage:
    uv run python scripts/convert_episodes_to_sft.py \
        --input-dir dynamics/ \
        --output artifacts/sft_from_episodes.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are playing an ARC-AGI-3 game. "
    "Based on the observation, choose the best action."
)

MAX_OBJECTS_IN_SUMMARY = 5
MAX_MOTIFS_IN_SUMMARY = 2
MAX_ROLE_OBJECTS_IN_SUMMARY = 2
ROLE_SCORE_THRESHOLD = 0.45
MAX_DYNAMICS_RULES_IN_SUMMARY = 2
MAX_INTERACTION_RULES_IN_SUMMARY = 2
MAX_REGIONS_IN_SUMMARY = 3
MAX_REFERENCE_PATTERNS_IN_SUMMARY = 1


# ---------------------------------------------------------------------------
# Reading helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None if it does not exist or is invalid."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_trace(path: Path) -> list[dict[str, Any]]:
    """Load an episode_trace.jsonl file into a list of dicts."""
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


# ---------------------------------------------------------------------------
# Compact state summary  (target: < 500 tokens for Qwen 0.8B)
# ---------------------------------------------------------------------------

def _format_object(obj: dict[str, Any]) -> str:
    """One-line object summary: v<val> n<count> @r<rmin>-<rmax> c<cmin>-<cmax>."""
    val = obj.get("value", "?")
    count = obj.get("cell_count", obj.get("count", 0))
    r_min = obj.get("row_min", obj.get("r_min", "?"))
    r_max = obj.get("row_max", obj.get("r_max", "?"))
    c_min = obj.get("col_min", obj.get("c_min", "?"))
    c_max = obj.get("col_max", obj.get("c_max", "?"))
    pid = _short_persistent_id(obj.get("persistent_id"))
    role_tags = _format_role_tags(obj)
    prefix = f"{pid}/" if pid else ""
    suffix = f"[{role_tags}]" if role_tags else ""
    return f"{prefix}v{val}:n{count}@r{r_min}-{r_max}c{c_min}-{c_max}{suffix}"


def _short_persistent_id(pid: Any) -> str | None:
    if not isinstance(pid, str) or not pid:
        return None
    return pid if len(pid) <= 8 else pid[:8]


def _object_role_pairs(obj: dict[str, Any]) -> list[tuple[str, float]]:
    return [
        ("ctrl", float(obj.get("controllable_score", 0.0) or 0.0)),
        ("goal", float(obj.get("goal_score", 0.0) or 0.0)),
        ("block", float(obj.get("blocker_score", 0.0) or 0.0)),
        ("click", float(obj.get("click_score", 0.0) or 0.0)),
    ]


def _role_priority(obj: dict[str, Any]) -> float:
    return max((score for _, score in _object_role_pairs(obj)), default=0.0)


def _format_role_tags(obj: dict[str, Any]) -> str:
    tags = [
        f"{name}{score:.2f}"
        for name, score in _object_role_pairs(obj)
        if score >= ROLE_SCORE_THRESHOLD
    ]
    return ",".join(tags)


def _rank_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mix role-salient objects with large objects for compact summaries."""
    selected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def object_key(obj: dict[str, Any]) -> str:
        pid = obj.get("persistent_id")
        if isinstance(pid, str) and pid:
            return f"pid:{pid}"
        return json.dumps(
            {
                "value": obj.get("value"),
                "row_min": obj.get("row_min", obj.get("r_min")),
                "row_max": obj.get("row_max", obj.get("r_max")),
                "col_min": obj.get("col_min", obj.get("c_min")),
                "col_max": obj.get("col_max", obj.get("c_max")),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    role_ranked = sorted(
        objects,
        key=lambda o: (-_role_priority(o), -(o.get("cell_count", o.get("count", 0)))),
    )
    for obj in role_ranked:
        if _role_priority(obj) < ROLE_SCORE_THRESHOLD:
            break
        key = object_key(obj)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selected.append(obj)
        if len(selected) >= MAX_ROLE_OBJECTS_IN_SUMMARY:
            break

    size_ranked = sorted(
        objects,
        key=lambda o: (
            -(o.get("cell_count", o.get("count", 0))),
            -_role_priority(o),
        ),
    )
    for obj in size_ranked:
        key = object_key(obj)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selected.append(obj)

    return selected


def _format_role_candidate(
    role_name: str,
    objects: list[dict[str, Any]],
    score_key: str,
) -> str | None:
    ranked = sorted(
        objects,
        key=lambda o: (
            -float(o.get(score_key, 0.0) or 0.0),
            -(o.get("cell_count", o.get("count", 0))),
        ),
    )
    if not ranked:
        return None
    top = ranked[0]
    score = float(top.get(score_key, 0.0) or 0.0)
    if score < ROLE_SCORE_THRESHOLD:
        return None
    pid = _short_persistent_id(top.get("persistent_id")) or "anon"
    val = top.get("value", "?")
    return f"{role_name}={pid}(v{val},{score:.2f})"


def _build_role_candidate_summary(objects: list[dict[str, Any]]) -> str | None:
    candidates = [
        _format_role_candidate("ctrl", objects, "controllable_score"),
        _format_role_candidate("goal", objects, "goal_score"),
        _format_role_candidate("block", objects, "blocker_score"),
        _format_role_candidate("click", objects, "click_score"),
    ]
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        return None
    return " | ".join(candidates)


def _truncate_label(label: str, limit: int = 18) -> str:
    return label if len(label) <= limit else label[: limit - 3] + "..."


def _truncate_text(text: str | None, limit: int = 32) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def _format_belief_diff(diff_payload: dict[str, Any] | None) -> str | None:
    if not isinstance(diff_payload, dict):
        return None

    parts: list[str] = []
    parts.append(
        "hyp("
        f"up={int(diff_payload.get('hypotheses_strengthened', 0) or 0)}, "
        f"down={int(diff_payload.get('hypotheses_weakened', 0) or 0)}, "
        f"x={int(diff_payload.get('hypotheses_discarded', 0) or 0)}, "
        f"new={int(diff_payload.get('hypotheses_suggested', 0) or 0)})"
    )

    motifs_updated = int(diff_payload.get("motifs_updated", 0) or 0)
    anchoring_alerts = int(diff_payload.get("anchoring_alerts", 0) or 0)
    max_delta = float(diff_payload.get("max_confidence_delta", 0.0) or 0.0)
    if motifs_updated:
        parts.append(f"motifs={motifs_updated}")
    if anchoring_alerts:
        parts.append(f"alerts={anchoring_alerts}")
    if max_delta > 0:
        parts.append(f"max_d={max_delta:.2f}")

    summary = diff_payload.get("summary")
    if isinstance(summary, str) and summary and summary != "No explicit belief revision summary.":
        parts.append(_truncate_label(summary, limit=36))

    return " | ".join(parts) if parts else None


def _format_dynamics_rule(rule: dict[str, Any]) -> str:
    action_name = _truncate_text(str(rule.get("action_name") or "passive"), 12)
    effect = _truncate_text(str(rule.get("effect") or "unknown"), 40)
    confidence = float(rule.get("confidence", 0.0) or 0.0)
    times_verified = int(rule.get("times_verified", 0) or 0)
    return f"{action_name}->{effect} (c{confidence:.2f},v{times_verified})"


def _format_interaction_rule(rule: dict[str, Any]) -> str:
    trigger_pid = _short_persistent_id(rule.get("trigger_pid")) or "anon"
    affected_pid = _short_persistent_id(rule.get("affected_pid")) or "anon"
    rule_type = _truncate_text(str(rule.get("rule_type") or "unknown"), 12)
    confidence = float(rule.get("confidence", 0.0) or 0.0)
    effect = _truncate_text(str(rule.get("effect") or ""), 20)
    summary = f"{trigger_pid} {rule_type} {affected_pid}"
    if effect and effect.lower() not in rule_type.lower():
        summary = f"{summary}:{effect}"
    return f"{summary} (c{confidence:.2f})"


def _format_region(region: dict[str, Any]) -> str:
    label = (
        _truncate_text(str(region.get("name") or ""), 14)
        or _truncate_text(str(region.get("role") or ""), 14)
        or _truncate_text(str(region.get("region_id") or ""), 14)
    )
    bbox = (
        f"r{region.get('row_min', 0)}-{region.get('row_max', 0)},"
        f"c{region.get('col_min', 0)}-{region.get('col_max', 0)}"
    )
    extras = [f"trv={1 if region.get('traversable', True) else 0}"]
    if region.get("dominant_value") is not None:
        extras.append(f"v{region['dominant_value']}")
    return f"{label}[{bbox},{','.join(extras)}]"


def _format_reference_pattern(pattern: dict[str, Any]) -> str:
    surface_id = _truncate_text(str(pattern.get("surface_id") or "surface"), 12)
    kind = _truncate_text(str(pattern.get("kind") or "unknown"), 14)
    pattern_rows = [str(row) for row in pattern.get("pattern_rows", []) if isinstance(row, str)]
    if pattern_rows:
        row_count = len(pattern_rows)
        col_count = max((len(row) for row in pattern_rows), default=0)
        preview = "/".join(pattern_rows[:4])
        if len(pattern_rows) > 4:
            preview += "/..."
        description = _truncate_text(str(pattern.get("pattern_description") or ""), 28)
        if description:
            return f"{surface_id}:{kind} {row_count}x{col_count} {preview} | {description}"
        return f"{surface_id}:{kind} {row_count}x{col_count} {preview}"

    description = _truncate_text(str(pattern.get("pattern_description") or ""), 40)
    return f"{surface_id}:{kind} {description}" if description else f"{surface_id}:{kind}"


def _build_world_model_summary(
    belief: dict[str, Any] | None,
    trace_row: dict[str, Any] | None,
) -> list[str]:
    parts: list[str] = []
    belief = belief or {}
    trace_row = trace_row or {}

    raw_dynamics = belief.get("dynamics_rules") if isinstance(belief.get("dynamics_rules"), list) else []
    if raw_dynamics:
        ranked_dynamics = sorted(
            raw_dynamics,
            key=lambda rule: (
                -float(rule.get("confidence", 0.0) or 0.0),
                -int(rule.get("times_verified", 0) or 0),
            ),
        )[:MAX_DYNAMICS_RULES_IN_SUMMARY]
        parts.append("Dynamics: " + " | ".join(_format_dynamics_rule(rule) for rule in ranked_dynamics))
    elif isinstance(trace_row.get("dynamics_rule_summary"), list) and trace_row["dynamics_rule_summary"]:
        parts.append("Dynamics: " + " | ".join(str(item) for item in trace_row["dynamics_rule_summary"][:MAX_DYNAMICS_RULES_IN_SUMMARY]))

    raw_interactions = belief.get("interaction_rules") if isinstance(belief.get("interaction_rules"), list) else []
    if raw_interactions:
        ranked_interactions = sorted(
            raw_interactions,
            key=lambda rule: (
                -float(rule.get("confidence", 0.0) or 0.0),
                -int(rule.get("times_observed", 0) or 0),
            ),
        )[:MAX_INTERACTION_RULES_IN_SUMMARY]
        parts.append(
            "Interactions: " + " | ".join(_format_interaction_rule(rule) for rule in ranked_interactions)
        )
    elif isinstance(trace_row.get("interaction_rule_summary"), list) and trace_row["interaction_rule_summary"]:
        parts.append(
            "Interactions: "
            + " | ".join(str(item) for item in trace_row["interaction_rule_summary"][:MAX_INTERACTION_RULES_IN_SUMMARY])
        )

    raw_regions = belief.get("regions") if isinstance(belief.get("regions"), list) else []
    if raw_regions:
        role_rank = {
            "reference": 4,
            "play_area": 3,
            "barrier": 2,
            "corridor": 1,
            "energy_display": 1,
            "status_display": 1,
        }
        ranked_regions = sorted(
            raw_regions,
            key=lambda region: (
                -role_rank.get(str(region.get("role", "unknown")), 0),
                -abs(int(region.get("row_max", 0)) - int(region.get("row_min", 0)) + 1)
                * abs(int(region.get("col_max", 0)) - int(region.get("col_min", 0)) + 1),
            ),
        )[:MAX_REGIONS_IN_SUMMARY]
        parts.append("Regions: " + " | ".join(_format_region(region) for region in ranked_regions))
    elif isinstance(trace_row.get("region_summary"), list) and trace_row["region_summary"]:
        parts.append("Regions: " + " | ".join(str(item) for item in trace_row["region_summary"][:MAX_REGIONS_IN_SUMMARY]))

    raw_patterns = (
        belief.get("reference_patterns")
        if isinstance(belief.get("reference_patterns"), list)
        else []
    )
    if raw_patterns:
        ranked_patterns = sorted(
            raw_patterns,
            key=lambda pattern: (-float(pattern.get("confidence", 0.0) or 0.0), str(pattern.get("surface_id", ""))),
        )[:MAX_REFERENCE_PATTERNS_IN_SUMMARY]
        parts.append(
            "Reference pattern: "
            + " | ".join(_format_reference_pattern(pattern) for pattern in ranked_patterns)
        )
    elif trace_row.get("reference_pattern_summary"):
        parts.append(f"Reference pattern: {trace_row['reference_pattern_summary']}")

    return parts


def build_compact_state(
    obs: dict[str, Any],
    belief: dict[str, Any] | None,
    trace_row: dict[str, Any] | None,
    prev_obs: dict[str, Any] | None,
    decision: dict[str, Any] | None = None,
) -> str:
    """Build a compact state summary string under ~500 tokens."""
    parts: list[str] = []

    # -- game state --
    game_id = obs.get("game_id", "unknown")
    state = obs.get("state", "NOT_FINISHED")
    levels = obs.get("levels_completed", 0)
    step = obs.get("step_index", 0)
    rows = obs.get("grid_rows", "?")
    cols = obs.get("grid_cols", "?")
    parts.append(f"Game: {game_id} | State: {state} | Level: {levels} | Step: {step} | Grid: {rows}x{cols}")

    # -- available actions --
    actions = obs.get("available_actions", [])
    if actions:
        parts.append(f"Available actions: {', '.join(str(a) for a in actions)}")

    # -- top 5 objects --
    objects = obs.get("objects", [])
    ranked = _rank_objects(objects)[:MAX_OBJECTS_IN_SUMMARY]
    if ranked:
        obj_strs = [_format_object(o) for o in ranked]
        parts.append(f"Top objects: {'; '.join(obj_strs)}")
    role_summary = _build_role_candidate_summary(objects)
    if role_summary:
        parts.append(f"Role candidates: {role_summary}")

    # -- phase --
    phase = "unknown"
    if belief:
        phase = belief.get("mode", "unknown")
    elif trace_row:
        phase = trace_row.get("planning_mode", "unknown")
    parts.append(f"Phase: {phase}")

    # -- top motif beliefs --
    if belief and belief.get("top_motifs"):
        motifs = belief["top_motifs"][:MAX_MOTIFS_IN_SUMMARY]
        motif_parts = [
            f"{m.get('name', '?')}({m.get('confidence', 0):.2f})"
            for m in motifs
        ]
        parts.append(f"Motif beliefs: {', '.join(motif_parts)}")
    elif trace_row and trace_row.get("motif_beliefs"):
        mb = trace_row["motif_beliefs"]
        sorted_motifs = sorted(mb.items(), key=lambda kv: -kv[1])[:MAX_MOTIFS_IN_SUMMARY]
        motif_parts = [f"{name}({conf:.2f})" for name, conf in sorted_motifs]
        parts.append(f"Motif beliefs: {', '.join(motif_parts)}")

    # -- recent belief shifts --
    belief_shifts: list[str] = []
    if decision and decision.get("belief_revision_summary"):
        belief_shifts = [
            str(item) for item in decision["belief_revision_summary"][:2]
        ]
    elif trace_row and trace_row.get("belief_revision_summary"):
        belief_shifts = [
            str(item) for item in trace_row["belief_revision_summary"][:2]
        ]
    elif trace_row and trace_row.get("belief_revision_reasons"):
        belief_shifts = [
            str(item) for item in trace_row["belief_revision_reasons"][:2]
        ]
    if belief_shifts:
        parts.append(f"Belief shifts: {' | '.join(belief_shifts)}")

    belief_diff = None
    if decision and isinstance(decision.get("belief_diff"), dict):
        belief_diff = decision["belief_diff"]
    elif trace_row and isinstance(trace_row.get("belief_diff"), dict):
        belief_diff = trace_row["belief_diff"]
    belief_diff_str = _format_belief_diff(belief_diff)
    if belief_diff_str:
        parts.append(f"Belief diff: {belief_diff_str}")

    # -- suggested hypotheses from recent surprise/revision --
    suggested_hypotheses: list[str] = []
    if decision and decision.get("suggested_hypotheses"):
        suggested_hypotheses = [
            str(item) for item in decision["suggested_hypotheses"][:2]
        ]
    elif trace_row and trace_row.get("suggested_hypotheses"):
        suggested_hypotheses = [
            str(item) for item in trace_row["suggested_hypotheses"][:2]
        ]
    if suggested_hypotheses:
        parts.append(f"Hypothesis updates: {' | '.join(suggested_hypotheses)}")

    parts.extend(_build_world_model_summary(belief, trace_row))

    # -- diff from previous step --
    diff = obs.get("diff_summary", "")
    if diff:
        parts.append(f"Diff: {diff}")
    elif prev_obs:
        prev_levels = prev_obs.get("levels_completed", 0)
        cur_levels = obs.get("levels_completed", 0)
        if cur_levels > prev_levels:
            parts.append(f"Diff: Level advanced {prev_levels}->{cur_levels}")
        else:
            parts.append("Diff: no level change")

    # -- action history (last 4) --
    history = obs.get("action_history", [])
    if history:
        recent = history[-4:]
        parts.append(f"Recent actions: {', '.join(str(a) for a in recent)}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Action + reasoning formatter
# ---------------------------------------------------------------------------

def _build_six_stage_reasoning(trace_row: dict[str, Any]) -> str | None:
    """Compose the 6-stage reasoning chain for the assistant response.

    Returns a multi-line string when at least one stage is populated,
    else None (caller falls back to legacy single-line reasoning).
    """
    stages = [
        ("OBSERVE", trace_row.get("observe_text")),
        ("INTERPRET", trace_row.get("interpret_text")),
        ("RESULT", trace_row.get("result_text")),
        ("REVISE", trace_row.get("revise_text")),
        ("HYPOTHESIZE", trace_row.get("hypothesize_text")),
        ("PREDICT", trace_row.get("predict_text")),
    ]
    populated = [(tag, text.strip()) for tag, text in stages if text and text.strip()]
    if not populated:
        return None
    return "\n".join(f"[{tag}] {text}" for tag, text in populated)


def build_action_response(
    decision: dict[str, Any] | None,
    trace_row: dict[str, Any] | None,
) -> str | None:
    """Format the assistant response: action + reasoning chain.

    Prefers the structured 6-stage chain (OBSERVE/INTERPRET/RESULT/REVISE/
    HYPOTHESIZE/PREDICT) when the trace row carries it; falls back to the
    legacy single-line reasoning otherwise. Returns None if no action.
    """
    action = None
    reasoning = ""

    if decision:
        action = (
            decision.get("chosen_action")
            or decision.get("action")
            or decision.get("action_taken")
        )
        reasoning = (
            decision.get("rationale", "")
            or decision.get("reasoning", "")
            or decision.get("expected_outcome", "")
        )
        action_args = decision.get("action_args", {}) or {}
    elif trace_row:
        action = trace_row.get("action_taken")
        reasoning = trace_row.get("prediction", "") or ""
        action_args = {}
    else:
        return None

    if not action:
        return None

    # Format the action string
    action_str = str(action)
    if action_args:
        x = action_args.get("x", action_args.get("row"))
        y = action_args.get("y", action_args.get("col"))
        if x is not None and y is not None:
            action_str = f"{action} {x} {y}"

    # Prefer the rich 6-stage reasoning chain when available.
    chain = _build_six_stage_reasoning(trace_row) if trace_row else None
    if chain:
        return f"{chain}\n\nACTION: {action_str}"

    # Legacy fallback: single-line reasoning truncated to 200 chars.
    if reasoning:
        reasoning = reasoning.strip()
        if len(reasoning) > 200:
            reasoning = reasoning[:197] + "..."
        return f"{action_str}\nReasoning: {reasoning}"
    return action_str


# ---------------------------------------------------------------------------
# Quality filtering
# ---------------------------------------------------------------------------

def _is_fallback_step(
    decision: dict[str, Any] | None,
    trace_row: dict[str, Any] | None,
) -> bool:
    """Return True if this step was just a fallback with no real decision."""
    if decision:
        if decision.get("is_fallback", False):
            return True
        reasoning = (decision.get("reasoning", "") or "").lower()
        if "fallback" in reasoning and "random" in reasoning:
            return True
    if trace_row:
        action = trace_row.get("action_taken")
        if action is None:
            return True
    return False


def compute_priority(
    obs: dict[str, Any],
    prev_obs: dict[str, Any] | None,
    trace_row: dict[str, Any] | None,
) -> float:
    """Compute a priority score for this training example.

    Higher = more valuable for training.
    - Level completion: +3.0
    - Surprise (unexpected change): +1.5
    - Non-trivial diff: +0.5
    - Epistemic phase: +0.3 (exploration is instructive)
    """
    priority = 1.0

    cur_levels = obs.get("levels_completed", 0)
    prev_levels = prev_obs.get("levels_completed", 0) if prev_obs else 0
    if cur_levels > prev_levels:
        priority += 3.0

    if trace_row:
        surprise = trace_row.get("surprise")
        if surprise is not None and surprise:
            # surprise can be a float or a truthy value
            if isinstance(surprise, (int, float)) and surprise > 0:
                priority += min(1.5, surprise)
            elif surprise:
                priority += 1.5

        mode = trace_row.get("planning_mode", "")
        if mode == "epistemic":
            priority += 0.3

    diff = obs.get("diff_summary", "")
    if diff and diff != "INITIAL" and diff != "no change":
        priority += 0.5

    return round(priority, 3)


def should_include(
    obs: dict[str, Any],
    decision: dict[str, Any] | None,
    trace_row: dict[str, Any] | None,
) -> bool:
    """Return True if this step should be included in training data."""
    if _is_fallback_step(decision, trace_row):
        return False
    return True


# ---------------------------------------------------------------------------
# Episode discovery and processing
# ---------------------------------------------------------------------------

def discover_episodes(input_dir: Path) -> list[Path]:
    """Find all episode directories.

    Supports both layouts:
      - nested:  {input_dir}/{game}/{episode_id}/steps/  (phase0 style)
      - flat:    {input_dir}/{episode_id}/steps/         (solve_loop style)
    """
    episodes: list[Path] = []
    if not input_dir.is_dir():
        return episodes

    for child in sorted(input_dir.iterdir()):
        if not child.is_dir():
            continue
        # Flat layout: {input_dir}/{episode_id}/steps/
        if (child / "steps").is_dir():
            episodes.append(child)
            continue
        # Nested layout: {input_dir}/{game}/{episode_id}/steps/
        for grandchild in sorted(child.iterdir()):
            if grandchild.is_dir() and (grandchild / "steps").is_dir():
                episodes.append(grandchild)
    return episodes


def _find_step_indices(steps_dir: Path) -> list[int]:
    """Discover all step indices from observation files."""
    indices: set[int] = set()
    for f in steps_dir.iterdir():
        if f.name.endswith(".observation.json"):
            # step_NNNN.observation.json
            try:
                idx = int(f.name.split("_")[1].split(".")[0])
                indices.add(idx)
            except (IndexError, ValueError):
                continue
    return sorted(indices)


def process_episode(
    ep_dir: Path,
) -> list[dict[str, Any]]:
    """Process a single episode directory and return training examples."""
    steps_dir = ep_dir / "steps"
    episode_meta = _load_json(ep_dir / "episode.json") or {}
    trace_rows = _load_trace(ep_dir / "episode_trace.jsonl")

    # Index trace rows by step_index for fast lookup
    trace_by_step: dict[int, dict[str, Any]] = {}
    for row in trace_rows:
        si = row.get("step_index")
        if si is not None:
            trace_by_step[int(si)] = row

    game_id = episode_meta.get("game_id", ep_dir.parent.name)
    episode_id = episode_meta.get("episode_id", ep_dir.name)

    step_indices = _find_step_indices(steps_dir)
    examples: list[dict[str, Any]] = []
    prev_obs: dict[str, Any] | None = None

    for step_idx in step_indices:
        prefix = steps_dir / f"step_{step_idx:04d}"
        obs = _load_json(Path(f"{prefix}.observation.json"))
        belief = _load_json(Path(f"{prefix}.belief.json"))
        decision = _load_json(Path(f"{prefix}.decision.json"))
        trace_row = trace_by_step.get(step_idx)

        if obs is None:
            continue

        # Quality filtering
        if not should_include(obs, decision, trace_row):
            prev_obs = obs
            continue

        # Build the action response
        action_response = build_action_response(decision, trace_row)
        if action_response is None:
            # No action taken at this step -- still useful if it is the
            # initial observation and we want the model to learn to plan.
            # For now, skip steps without actions.
            prev_obs = obs
            continue

        # Build compact state
        state_summary = build_compact_state(obs, belief, trace_row, prev_obs, decision)

        # Determine phase
        phase = "unknown"
        if belief:
            phase = belief.get("mode", "unknown")
        elif trace_row:
            phase = trace_row.get("planning_mode", "unknown")

        levels = obs.get("levels_completed", 0)
        priority = compute_priority(obs, prev_obs, trace_row)

        # Was this step useful?  (non-fallback + produced change)
        diff = obs.get("diff_summary", "")
        was_useful = bool(diff and diff not in ("INITIAL", "no change", ""))

        example: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": state_summary},
                {"role": "assistant", "content": action_response},
            ],
            "metadata": {
                "game_id": game_id,
                "episode_id": episode_id,
                "step": step_idx,
                "phase": phase,
                "levels_completed": levels,
                "was_useful": was_useful,
                "priority": priority,
            },
        }

        examples.append(example)
        prev_obs = obs

    return examples


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_statistics(examples: list[dict[str, Any]]) -> None:
    """Print summary statistics about the generated dataset."""
    n = len(examples)
    print(f"\n{'='*60}")
    print(f"SFT Dataset Statistics")
    print(f"{'='*60}")
    print(f"Total examples: {n}")

    if n == 0:
        print("(no examples generated)")
        return

    # Phase distribution
    phase_counter: Counter[str] = Counter()
    for ex in examples:
        phase_counter[ex["metadata"]["phase"]] += 1
    print(f"\nPhase distribution:")
    for phase, count in phase_counter.most_common():
        print(f"  {phase}: {count} ({100*count/n:.1f}%)")

    # Game distribution
    game_counter: Counter[str] = Counter()
    for ex in examples:
        game_counter[ex["metadata"]["game_id"]] += 1
    print(f"\nGame distribution:")
    for game, count in game_counter.most_common():
        print(f"  {game}: {count} ({100*count/n:.1f}%)")

    # Priority stats
    priorities = [ex["metadata"]["priority"] for ex in examples]
    avg_pri = sum(priorities) / len(priorities)
    max_pri = max(priorities)
    min_pri = min(priorities)
    print(f"\nPriority: min={min_pri:.2f} avg={avg_pri:.2f} max={max_pri:.2f}")

    # Useful steps
    useful = sum(1 for ex in examples if ex["metadata"]["was_useful"])
    print(f"Useful steps: {useful}/{n} ({100*useful/n:.1f}%)")

    # Level completions
    level_steps = sum(
        1 for ex in examples if ex["metadata"]["levels_completed"] > 0
    )
    print(f"Steps with levels_completed > 0: {level_steps}")

    # Average user message length (proxy for token count)
    user_lens = [
        len(ex["messages"][1]["content"])
        for ex in examples
    ]
    avg_len = sum(user_lens) / len(user_lens)
    max_len = max(user_lens)
    print(f"\nUser message chars: avg={avg_len:.0f} max={max_len}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert agentic episode data to SFT training format for Qwen."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("dynamics"),
        help="Root dynamics directory containing game sub-directories.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/sft_from_episodes.jsonl"),
        help="Output JSONL file path.",
    )
    parser.add_argument(
        "--min-priority",
        type=float,
        default=0.0,
        help="Minimum priority score to include an example (default: 0.0 = include all).",
    )
    args = parser.parse_args()

    episodes = discover_episodes(args.input_dir)
    if not episodes:
        print(f"No episode directories found under {args.input_dir}")
        print("Expected structure: {input_dir}/{game}/{episode_id}/steps/step_NNNN.observation.json")
        raise SystemExit(1)

    print(f"Found {len(episodes)} episode(s) across {args.input_dir}")

    all_examples: list[dict[str, Any]] = []
    for ep_dir in episodes:
        examples = process_episode(ep_dir)
        all_examples.extend(examples)
        if examples:
            print(f"  {ep_dir.relative_to(args.input_dir)}: {len(examples)} examples")
        else:
            print(f"  {ep_dir.relative_to(args.input_dir)}: 0 examples (no actionable steps)")

    # Apply priority filter
    if args.min_priority > 0:
        before = len(all_examples)
        all_examples = [
            ex for ex in all_examples
            if ex["metadata"]["priority"] >= args.min_priority
        ]
        print(f"\nPriority filter (>= {args.min_priority}): {before} -> {len(all_examples)}")

    # Sort by (game, episode, step) for reproducibility
    all_examples.sort(
        key=lambda ex: (
            ex["metadata"]["game_id"],
            ex["metadata"]["episode_id"],
            ex["metadata"]["step"],
        )
    )

    # Write output
    write_jsonl(args.output, all_examples)
    print(f"\nWrote {len(all_examples)} examples to {args.output}")

    # Print statistics
    print_statistics(all_examples)


if __name__ == "__main__":
    main()
