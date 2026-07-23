# [Mar 30] Created by SD with GPT-5.4.

"""Episode-level metrics for unattended ARC-AGI-3 loops."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_CHANGED_CELLS_RE = re.compile(r"(\d+)\s+cells?\s+changed", re.IGNORECASE)


@dataclass
class ActualInformationGainEstimate:
    value: float | None
    reasons: list[str] = field(default_factory=list)


@dataclass
class BeliefRevisionEstimate:
    belief_revision_score: float | None
    hypothesis_pruning_count: int = 0
    surprise_magnitude: float | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class EpisodeEpistemicMetrics:
    actual_information_gain: float | None = None
    actual_information_gain_reasons: list[str] = field(default_factory=list)
    belief_revision_score: float | None = None
    hypothesis_pruning_count: int = 0
    surprise_magnitude: float | None = None
    belief_revision_reasons: list[str] = field(default_factory=list)
    rule_discovery_score: float | None = None
    rule_discovery_reasons: list[str] = field(default_factory=list)
    new_dynamics_rules_count: int = 0
    new_interaction_rules_count: int = 0
    new_region_count: int = 0
    reference_pattern_update_count: int = 0


def _trace_belief_revision_signals(
    trace_tail: dict[str, Any] | None,
) -> BeliefRevisionEstimate | None:
    if not trace_tail:
        return None

    trace_score = (
        float(trace_tail.get("belief_revision_score"))
        if isinstance(trace_tail.get("belief_revision_score"), (int, float))
        else None
    )
    trace_pruning = (
        int(trace_tail.get("hypothesis_pruning_count"))
        if isinstance(trace_tail.get("hypothesis_pruning_count"), (int, float))
        else 0
    )
    trace_surprise = (
        float(trace_tail.get("surprise_magnitude"))
        if isinstance(trace_tail.get("surprise_magnitude"), (int, float))
        else None
    )

    reasons: list[str] = []
    summary_items = trace_tail.get("belief_revision_summary")
    if isinstance(summary_items, list):
        reasons.extend(str(item) for item in summary_items[:3])
    revision_reasons = trace_tail.get("belief_revision_reasons")
    if isinstance(revision_reasons, list):
        reasons.extend(str(item) for item in revision_reasons[:3])
    suggested_hypotheses = trace_tail.get("suggested_hypotheses")
    if isinstance(suggested_hypotheses, list) and suggested_hypotheses:
        reasons.append(
            "Suggested hypotheses: " + " | ".join(str(item) for item in suggested_hypotheses[:2])
        )
    motif_updates = trace_tail.get("motif_updates")
    if isinstance(motif_updates, list) and motif_updates:
        reasons.append(
            "Motif updates: " + " | ".join(str(item) for item in motif_updates[:2])
        )
    anchoring_alerts = trace_tail.get("anchoring_alerts")
    if isinstance(anchoring_alerts, list) and anchoring_alerts:
        reasons.append(
            "Anchoring alerts: " + " | ".join(str(item) for item in anchoring_alerts[:2])
        )

    if trace_score is None and trace_pruning == 0 and trace_surprise is None and not reasons:
        return None

    if trace_score is None:
        trace_score = min(1.0, 0.12 * trace_pruning + (trace_surprise or 0.0) * 0.5)
    if trace_pruning:
        reasons.append(f"Trace reported {trace_pruning} pruned hypotheses.")
    if trace_surprise is not None:
        reasons.append(f"Trace surprise magnitude={trace_surprise:.3f}.")

    return BeliefRevisionEstimate(
        belief_revision_score=round(min(1.0, max(0.0, trace_score)), 3),
        hypothesis_pruning_count=trace_pruning,
        surprise_magnitude=(
            round(min(1.0, max(0.0, trace_surprise)), 3)
            if trace_surprise is not None
            else None
        ),
        reasons=reasons,
    )


def _load_json(path: Path, cache: dict[Path, dict[str, Any]]) -> dict[str, Any] | None:
    if path in cache:
        return cache[path]
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    cache[path] = payload
    return payload


def load_observation_payload(
    observation_path: str | None,
    cache: dict[Path, dict[str, Any]],
) -> dict[str, Any] | None:
    if not observation_path:
        return None
    return _load_json(Path(observation_path), cache)


def load_trace_tail(
    trace_path: str | None,
    cache: dict[Path, dict[str, Any]],
) -> dict[str, Any] | None:
    if not trace_path:
        return None
    path = Path(trace_path)
    if path in cache:
        return cache[path]
    if not path.exists():
        return None
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        return None
    payload = json.loads(lines[-1])
    cache[path] = payload
    return payload


def load_belief_payload(
    belief_path: str | None,
    cache: dict[Path, dict[str, Any]],
) -> dict[str, Any] | None:
    if not belief_path:
        return None
    return _load_json(Path(belief_path), cache)


def parse_changed_cells(diff_summary: str | None) -> int | None:
    if not diff_summary:
        return None
    match = _CHANGED_CELLS_RE.search(diff_summary)
    if not match:
        return None
    return int(match.group(1))


def _confidence_map(
    entries: list[dict[str, Any]],
    *,
    key_candidates: tuple[str, ...],
) -> dict[str, float]:
    mapped: dict[str, float] = {}
    for entry in entries:
        key = None
        for candidate in key_candidates:
            value = entry.get(candidate)
            if isinstance(value, str) and value:
                key = value
                break
        if not key:
            continue
        mapped[key] = float(entry.get("confidence", 0.0))
    return mapped


def _hypothesis_map(hypotheses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for hypothesis in hypotheses:
        key = hypothesis.get("hypothesis_id") or hypothesis.get("summary")
        if isinstance(key, str) and key:
            mapped[key] = hypothesis
    return mapped


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).lower()


def _dynamics_rule_signature(rule: dict[str, Any]) -> str:
    return "|".join(
        [
            _normalized_text(rule.get("action_name")),
            _normalized_text(rule.get("condition")),
            _normalized_text(rule.get("effect")),
        ]
    )


def _interaction_rule_signature(rule: dict[str, Any]) -> str:
    return "|".join(
        [
            _normalized_text(rule.get("trigger_pid")),
            _normalized_text(rule.get("affected_pid")),
            _normalized_text(rule.get("trigger_action")),
            _normalized_text(rule.get("rule_type")),
            _normalized_text(rule.get("effect")),
        ]
    )


def _region_signature(region: dict[str, Any]) -> str:
    return "|".join(
        [
            _normalized_text(region.get("region_id")),
            _normalized_text(region.get("name")),
            _normalized_text(region.get("role")),
            str(int(region.get("row_min", 0) or 0)),
            str(int(region.get("row_max", 0) or 0)),
            str(int(region.get("col_min", 0) or 0)),
            str(int(region.get("col_max", 0) or 0)),
            str(int(region.get("dominant_value", -1) or -1)),
            "1" if region.get("traversable", True) else "0",
        ]
    )


def _reference_pattern_signature(pattern: dict[str, Any]) -> str:
    return "|".join(
        [
            _normalized_text(pattern.get("surface_id")),
            _normalized_text(pattern.get("kind")),
            "/".join(str(row) for row in pattern.get("pattern_rows", []) if isinstance(row, str)),
            _normalized_text(pattern.get("pattern_description")),
        ]
    )


def estimate_rule_discovery(
    current_belief: dict[str, Any] | None,
    parent_belief: dict[str, Any] | None,
) -> tuple[float | None, list[str], int, int, int, int]:
    if current_belief is None or parent_belief is None:
        return None, [], 0, 0, 0, 0

    current_dynamics = {
        _dynamics_rule_signature(rule)
        for rule in current_belief.get("dynamics_rules", [])
        if isinstance(rule, dict)
    }
    parent_dynamics = {
        _dynamics_rule_signature(rule)
        for rule in parent_belief.get("dynamics_rules", [])
        if isinstance(rule, dict)
    }
    new_dynamics = {
        signature for signature in current_dynamics - parent_dynamics if signature.strip("|")
    }

    current_interactions = {
        _interaction_rule_signature(rule)
        for rule in current_belief.get("interaction_rules", [])
        if isinstance(rule, dict)
    }
    parent_interactions = {
        _interaction_rule_signature(rule)
        for rule in parent_belief.get("interaction_rules", [])
        if isinstance(rule, dict)
    }
    new_interactions = {
        signature
        for signature in current_interactions - parent_interactions
        if signature.strip("|")
    }

    current_regions = {
        _region_signature(region)
        for region in current_belief.get("regions", [])
        if isinstance(region, dict)
    }
    parent_regions = {
        _region_signature(region)
        for region in parent_belief.get("regions", [])
        if isinstance(region, dict)
    }
    new_regions = {
        signature for signature in current_regions - parent_regions if signature.strip("|")
    }

    current_patterns = {
        _reference_pattern_signature(pattern)
        for pattern in current_belief.get("reference_patterns", [])
        if isinstance(pattern, dict)
    }
    parent_patterns = {
        _reference_pattern_signature(pattern)
        for pattern in parent_belief.get("reference_patterns", [])
        if isinstance(pattern, dict)
    }
    new_patterns = {
        signature for signature in current_patterns - parent_patterns if signature.strip("|")
    }

    reasons: list[str] = []
    if new_dynamics:
        reasons.append(f"Discovered {len(new_dynamics)} new dynamics rule(s).")
    if new_interactions:
        reasons.append(f"Discovered {len(new_interactions)} new interaction rule(s).")
    if new_regions:
        reasons.append(f"Mapped {len(new_regions)} new region(s).")
    if new_patterns:
        reasons.append(f"Updated {len(new_patterns)} reference pattern(s).")

    if not reasons:
        return 0.0, ["No new rules or regions were discovered."], 0, 0, 0, 0

    score = min(
        1.0,
        0.18 * len(new_dynamics)
        + 0.15 * len(new_interactions)
        + 0.08 * len(new_regions)
        + 0.12 * len(new_patterns),
    )
    return (
        round(score, 3),
        reasons,
        len(new_dynamics),
        len(new_interactions),
        len(new_regions),
        len(new_patterns),
    )


def estimate_actual_information_gain(
    current_observation: dict[str, Any] | None,
    parent_observation: dict[str, Any] | None,
    trace_tail: dict[str, Any] | None = None,
) -> ActualInformationGainEstimate:
    if current_observation is None:
        return ActualInformationGainEstimate(
            value=None,
            reasons=["Current observation is unavailable."],
        )
    if parent_observation is None:
        return ActualInformationGainEstimate(
            value=None,
            reasons=["Parent observation is unavailable for comparison."],
        )

    score = 0.0
    reasons: list[str] = []

    parent_levels = int(parent_observation.get("levels_completed", 0))
    current_levels = int(current_observation.get("levels_completed", 0))
    if current_levels > parent_levels:
        delta = current_levels - parent_levels
        level_bonus = min(0.45, 0.25 + 0.1 * delta)
        score += level_bonus
        reasons.append(f"Levels completed increased by {delta}.")

    parent_state = str(parent_observation.get("state", "UNKNOWN"))
    current_state = str(current_observation.get("state", "UNKNOWN"))
    if current_state != parent_state:
        state_bonus = 0.28 if current_state == "WON" else 0.14
        score += state_bonus
        reasons.append(f"State changed from {parent_state} to {current_state}.")

    diff_summary = str(current_observation.get("diff_summary", ""))
    changed_cells = parse_changed_cells(diff_summary)
    if changed_cells is not None:
        diff_bonus = min(0.32, changed_cells / 160.0)
        score += diff_bonus
        reasons.append(f"{changed_cells} cells changed after the probe.")
    elif diff_summary and diff_summary.upper() not in {"INITIAL", "NO CHANGE"}:
        score += 0.12
        reasons.append(f"Diff summary reported non-trivial change: {diff_summary}.")

    parent_actions = set(parent_observation.get("available_actions", []))
    current_actions = set(current_observation.get("available_actions", []))
    if current_actions != parent_actions:
        union = parent_actions | current_actions
        novelty = len(current_actions ^ parent_actions) / max(1, len(union))
        action_bonus = min(0.18, 0.08 + 0.2 * novelty)
        score += action_bonus
        reasons.append("Available action set changed.")

    parent_objects = parent_observation.get("objects", [])
    current_objects = current_observation.get("objects", [])
    object_delta = abs(len(current_objects) - len(parent_objects))
    if object_delta:
        object_bonus = min(0.12, 0.04 * object_delta)
        score += object_bonus
        reasons.append(f"Object count changed by {object_delta}.")

    parent_hist = {
        str(key): int(value)
        for key, value in parent_observation.get("value_histogram", {}).items()
    }
    current_hist = {
        str(key): int(value)
        for key, value in current_observation.get("value_histogram", {}).items()
    }
    if parent_hist or current_hist:
        keys = set(parent_hist) | set(current_hist)
        total = max(1, sum(current_hist.values()), sum(parent_hist.values()))
        l1 = sum(abs(current_hist.get(key, 0) - parent_hist.get(key, 0)) for key in keys)
        histogram_shift = l1 / total
        if histogram_shift > 0:
            hist_bonus = min(0.16, histogram_shift * 0.5)
            score += hist_bonus
            reasons.append(
                f"Value histogram shifted by {histogram_shift:.3f} (L1-normalised)."
            )

    if trace_tail:
        surprise = trace_tail.get("surprise")
        dynamics_revision = str(trace_tail.get("dynamics_revision", "")).strip()
        if surprise:
            score += 0.12
            reasons.append("Trace recorded surprise, indicating belief mismatch.")
        if dynamics_revision and dynamics_revision != "Bootstrap heuristics only":
            score += 0.08
            reasons.append("Dynamics revision indicates the model had to adapt.")

    bounded = round(min(1.0, max(0.0, score)), 3)
    if not reasons:
        reasons.append("No measurable scene change relative to the parent episode.")
    return ActualInformationGainEstimate(value=bounded, reasons=reasons)


def estimate_belief_revision(
    current_belief: dict[str, Any] | None,
    parent_belief: dict[str, Any] | None,
    *,
    expected_information_gain: float | None = None,
    actual_information_gain: float | None = None,
    trace_tail: dict[str, Any] | None = None,
) -> BeliefRevisionEstimate:
    trace_estimate = _trace_belief_revision_signals(trace_tail)

    if current_belief is None:
        if trace_estimate is not None:
            if "Current belief ledger is unavailable." not in trace_estimate.reasons:
                trace_estimate.reasons.insert(0, "Current belief ledger is unavailable.")
            return trace_estimate
        return BeliefRevisionEstimate(
            belief_revision_score=None,
            reasons=["Current belief ledger is unavailable."],
        )
    if parent_belief is None:
        if trace_estimate is not None:
            if "Parent belief ledger is unavailable for comparison." not in trace_estimate.reasons:
                trace_estimate.reasons.insert(0, "Parent belief ledger is unavailable for comparison.")
            return trace_estimate
        return BeliefRevisionEstimate(
            belief_revision_score=None,
            reasons=["Parent belief ledger is unavailable for comparison."],
        )

    score = 0.0
    reasons: list[str] = []

    parent_motifs = _confidence_map(
        parent_belief.get("top_motifs", []),
        key_candidates=("name", "summary"),
    )
    current_motifs = _confidence_map(
        current_belief.get("top_motifs", []),
        key_candidates=("name", "summary"),
    )
    motif_keys = set(parent_motifs) | set(current_motifs)
    if motif_keys:
        motif_shift = sum(
            abs(current_motifs.get(key, 0.0) - parent_motifs.get(key, 0.0))
            for key in motif_keys
        ) / len(motif_keys)
        if motif_shift > 0:
            motif_component = min(0.22, motif_shift * 0.8)
            score += motif_component
            reasons.append(f"Motif confidence shift={motif_shift:.3f}.")

    parent_hypotheses = _hypothesis_map(parent_belief.get("hypotheses", []))
    current_hypotheses = _hypothesis_map(current_belief.get("hypotheses", []))
    pruning_count = 0
    status_flips = 0
    confidence_shift = 0.0
    for key in set(parent_hypotheses) | set(current_hypotheses):
        parent = parent_hypotheses.get(key)
        current = current_hypotheses.get(key)
        parent_status = str(parent.get("status")) if parent else None
        current_status = str(current.get("status")) if current else None
        parent_conf = float(parent.get("confidence", 0.0)) if parent else 0.0
        current_conf = float(current.get("confidence", 0.0)) if current else 0.0
        confidence_shift += abs(current_conf - parent_conf)
        if parent and current and parent_status != current_status:
            status_flips += 1
        if parent and parent_status in {"active", "provisional", "confirmed"}:
            if current is None or current_status == "discarded":
                pruning_count += 1

    if parent_hypotheses or current_hypotheses:
        normaliser = max(1, len(set(parent_hypotheses) | set(current_hypotheses)))
        hypothesis_shift = confidence_shift / normaliser
        hypothesis_component = min(
            0.35,
            hypothesis_shift * 0.8 + 0.08 * status_flips + 0.12 * pruning_count,
        )
        score += hypothesis_component
        if hypothesis_shift > 0:
            reasons.append(f"Hypothesis confidence shift={hypothesis_shift:.3f}.")
        if status_flips:
            reasons.append(f"{status_flips} hypothesis status flips observed.")
        if pruning_count:
            reasons.append(f"{pruning_count} hypotheses were pruned or discarded.")

    parent_goals = _confidence_map(
        parent_belief.get("goal_beliefs", []),
        key_candidates=("summary", "name"),
    )
    current_goals = _confidence_map(
        current_belief.get("goal_beliefs", []),
        key_candidates=("summary", "name"),
    )
    goal_keys = set(parent_goals) | set(current_goals)
    if goal_keys:
        goal_shift = sum(
            abs(current_goals.get(key, 0.0) - parent_goals.get(key, 0.0))
            for key in goal_keys
        ) / len(goal_keys)
        if goal_shift > 0:
            goal_component = min(0.18, goal_shift * 0.7)
            score += goal_component
            reasons.append(f"Goal confidence shift={goal_shift:.3f}.")

    surprise_score = 0.0
    if expected_information_gain is not None and actual_information_gain is not None:
        gap = abs(float(expected_information_gain) - float(actual_information_gain))
        surprise_score = max(surprise_score, min(1.0, gap))
        if gap > 0:
            reasons.append(f"Expected/actual information-gain gap={gap:.3f}.")
    if trace_tail and trace_tail.get("surprise"):
        surprise_score = max(surprise_score, 0.6)
        reasons.append("Trace recorded an explicit surprise event.")
    if pruning_count:
        surprise_score = min(1.0, surprise_score + min(0.2, 0.08 * pruning_count))

    if trace_estimate is not None:
        if trace_estimate.belief_revision_score is not None:
            bounded_trace_score = min(1.0, max(0.0, trace_estimate.belief_revision_score))
            if bounded_trace_score > score:
                reasons.append(
                    f"Trace belief revision score {bounded_trace_score:.3f} exceeded ledger-only estimate."
                )
            score = max(score, bounded_trace_score)
        pruning_count = max(pruning_count, trace_estimate.hypothesis_pruning_count)
        if trace_estimate.surprise_magnitude is not None:
            surprise_score = max(surprise_score, trace_estimate.surprise_magnitude)
        reasons.extend(
            reason
            for reason in trace_estimate.reasons
            if reason not in reasons
        )

    bounded_score = round(min(1.0, max(0.0, score)), 3)
    bounded_surprise = round(min(1.0, max(0.0, surprise_score)), 3)
    if not reasons:
        reasons.append("Belief ledger remained effectively stable relative to the parent.")

    return BeliefRevisionEstimate(
        belief_revision_score=bounded_score,
        hypothesis_pruning_count=pruning_count,
        surprise_magnitude=bounded_surprise,
        reasons=reasons,
    )


def estimate_actual_information_gain_for_row(
    row: dict[str, Any],
    completed_rows_by_episode_id: dict[str, dict[str, Any]],
    observation_cache: dict[Path, dict[str, Any]] | None = None,
    trace_cache: dict[Path, dict[str, Any]] | None = None,
) -> ActualInformationGainEstimate:
    if observation_cache is None:
        observation_cache = {}
    if trace_cache is None:
        trace_cache = {}

    current_observation = load_observation_payload(
        row.get("observation_path") if isinstance(row.get("observation_path"), str) else None,
        observation_cache,
    )
    trace_tail = load_trace_tail(
        row.get("trace_path") if isinstance(row.get("trace_path"), str) else None,
        trace_cache,
    )

    parent_observation = None
    parent_episode_id = row.get("parent_episode_id")
    if isinstance(parent_episode_id, str):
        parent_row = completed_rows_by_episode_id.get(parent_episode_id)
        if parent_row is not None:
            parent_observation = load_observation_payload(
                parent_row.get("observation_path")
                if isinstance(parent_row.get("observation_path"), str)
                else None,
                observation_cache,
            )

    return estimate_actual_information_gain(
        current_observation=current_observation,
        parent_observation=parent_observation,
        trace_tail=trace_tail,
    )


def estimate_episode_epistemic_metrics_for_row(
    row: dict[str, Any],
    completed_rows_by_episode_id: dict[str, dict[str, Any]],
    observation_cache: dict[Path, dict[str, Any]] | None = None,
    belief_cache: dict[Path, dict[str, Any]] | None = None,
    trace_cache: dict[Path, dict[str, Any]] | None = None,
) -> EpisodeEpistemicMetrics:
    if observation_cache is None:
        observation_cache = {}
    if belief_cache is None:
        belief_cache = {}
    if trace_cache is None:
        trace_cache = {}

    actual_estimate = estimate_actual_information_gain_for_row(
        row,
        completed_rows_by_episode_id=completed_rows_by_episode_id,
        observation_cache=observation_cache,
        trace_cache=trace_cache,
    )

    current_belief = load_belief_payload(
        row.get("belief_path") if isinstance(row.get("belief_path"), str) else None,
        belief_cache,
    )
    trace_tail = load_trace_tail(
        row.get("trace_path") if isinstance(row.get("trace_path"), str) else None,
        trace_cache,
    )

    parent_belief = None
    parent_episode_id = row.get("parent_episode_id")
    if isinstance(parent_episode_id, str):
        parent_row = completed_rows_by_episode_id.get(parent_episode_id)
        if parent_row is not None:
            parent_belief = load_belief_payload(
                parent_row.get("belief_path")
                if isinstance(parent_row.get("belief_path"), str)
                else None,
                belief_cache,
            )

    expected_information_gain = (
        float(row.get("expected_information_gain"))
        if isinstance(row.get("expected_information_gain"), (int, float))
        else None
    )
    belief_estimate = estimate_belief_revision(
        current_belief=current_belief,
        parent_belief=parent_belief,
        expected_information_gain=expected_information_gain,
        actual_information_gain=actual_estimate.value,
        trace_tail=trace_tail,
    )
    (
        rule_discovery_score,
        rule_discovery_reasons,
        new_dynamics_rules_count,
        new_interaction_rules_count,
        new_region_count,
        reference_pattern_update_count,
    ) = estimate_rule_discovery(
        current_belief=current_belief,
        parent_belief=parent_belief,
    )

    combined_actual_gain = actual_estimate.value
    combined_actual_reasons = list(actual_estimate.reasons)
    if rule_discovery_score is not None and rule_discovery_score > 0:
        gain_bonus = min(0.24, 0.3 * rule_discovery_score)
        combined_actual_gain = round(
            min(1.0, (combined_actual_gain or 0.0) + gain_bonus),
            3,
        )
        combined_actual_reasons.extend(rule_discovery_reasons)

    return EpisodeEpistemicMetrics(
        actual_information_gain=combined_actual_gain,
        actual_information_gain_reasons=combined_actual_reasons,
        belief_revision_score=belief_estimate.belief_revision_score,
        hypothesis_pruning_count=belief_estimate.hypothesis_pruning_count,
        surprise_magnitude=belief_estimate.surprise_magnitude,
        belief_revision_reasons=belief_estimate.reasons,
        rule_discovery_score=rule_discovery_score,
        rule_discovery_reasons=rule_discovery_reasons,
        new_dynamics_rules_count=new_dynamics_rules_count,
        new_interaction_rules_count=new_interaction_rules_count,
        new_region_count=new_region_count,
        reference_pattern_update_count=reference_pattern_update_count,
    )
