# [Mar 30] Created by SD with GPT-5.4.

"""Post-hoc trace enrichment for unattended ARC-AGI-3 episodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.agentic.memory import (
    load_trace_records,
    rewrite_trace_records,
    write_episode_metrics,
)
from scripts.agentic_episode_metrics import estimate_episode_epistemic_metrics_for_row


def _completed_row_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "completed":
            continue
        episode_id = row.get("episode_id")
        if isinstance(episode_id, str):
            indexed[episode_id] = row
    return indexed


def enrich_completed_manifest_rows(
    current_rows: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    completed_rows = _completed_row_index(all_rows)
    observation_cache: dict[Path, dict[str, Any]] = {}
    belief_cache: dict[Path, dict[str, Any]] = {}
    trace_cache: dict[Path, dict[str, Any]] = {}
    enriched: list[dict[str, Any]] = []

    for row in current_rows:
        if row.get("status") != "completed":
            continue

        metrics = estimate_episode_epistemic_metrics_for_row(
            row,
            completed_rows_by_episode_id=completed_rows,
            observation_cache=observation_cache,
            belief_cache=belief_cache,
            trace_cache=trace_cache,
        )

        episode_root = row.get("episode_root")
        metrics_payload = {
            "episode_id": row.get("episode_id"),
            "game_id": row.get("game_id"),
            "actual_information_gain": metrics.actual_information_gain,
            "actual_information_gain_reasons": metrics.actual_information_gain_reasons,
            "belief_revision_score": metrics.belief_revision_score,
            "belief_revision_reasons": metrics.belief_revision_reasons,
            "hypothesis_pruning_count": metrics.hypothesis_pruning_count,
            "surprise_magnitude": metrics.surprise_magnitude,
            "rule_discovery_score": metrics.rule_discovery_score,
            "rule_discovery_reasons": metrics.rule_discovery_reasons,
            "new_dynamics_rules_count": metrics.new_dynamics_rules_count,
            "new_interaction_rules_count": metrics.new_interaction_rules_count,
            "new_region_count": metrics.new_region_count,
            "reference_pattern_update_count": metrics.reference_pattern_update_count,
        }
        if isinstance(episode_root, str):
            metrics_path = write_episode_metrics(episode_root, metrics_payload)
            row["episode_metrics_path"] = str(metrics_path)

        trace_path = row.get("trace_path")
        if isinstance(trace_path, str):
            records = load_trace_records(trace_path)
            if records:
                updated = records[-1].model_copy(
                    update={
                        "actual_information_gain": metrics.actual_information_gain,
                        "actual_information_gain_reasons": metrics.actual_information_gain_reasons,
                        "belief_revision_score": metrics.belief_revision_score,
                        "belief_revision_reasons": metrics.belief_revision_reasons,
                        "hypothesis_pruning_count": metrics.hypothesis_pruning_count,
                        "surprise_magnitude": metrics.surprise_magnitude,
                    }
                )
                rewrite_trace_records(trace_path, [*records[:-1], updated])

        row["actual_information_gain"] = metrics.actual_information_gain
        row["belief_revision_score"] = metrics.belief_revision_score
        row["hypothesis_pruning_count"] = metrics.hypothesis_pruning_count
        row["surprise_magnitude"] = metrics.surprise_magnitude
        row["rule_discovery_score"] = metrics.rule_discovery_score
        row["new_dynamics_rules_count"] = metrics.new_dynamics_rules_count
        row["new_interaction_rules_count"] = metrics.new_interaction_rules_count
        row["new_region_count"] = metrics.new_region_count
        row["reference_pattern_update_count"] = metrics.reference_pattern_update_count

        enriched.append(
            {
                "episode_id": row.get("episode_id"),
                "game_id": row.get("game_id"),
                "actual_information_gain": metrics.actual_information_gain,
                "belief_revision_score": metrics.belief_revision_score,
                "hypothesis_pruning_count": metrics.hypothesis_pruning_count,
                "surprise_magnitude": metrics.surprise_magnitude,
                "rule_discovery_score": metrics.rule_discovery_score,
            }
        )

    return enriched
