"""[Mar 30] Created by SD with GPT-5.4."""

import json

import pytest

from scripts.agentic_episode_metrics import (
    estimate_belief_revision,
    estimate_episode_epistemic_metrics_for_row,
    estimate_actual_information_gain_for_row,
    estimate_rule_discovery,
    parse_changed_cells,
)


@pytest.mark.unit
class TestAgenticEpisodeMetrics:
    def test_parse_changed_cells(self):
        assert parse_changed_cells("52 cells changed") == 52
        assert parse_changed_cells("NO CHANGE") is None

    def test_estimate_actual_information_gain_for_row_uses_parent_comparison(self, tmp_path):
        parent_observation_path = tmp_path / "parent.observation.json"
        child_observation_path = tmp_path / "child.observation.json"
        child_trace_path = tmp_path / "child.trace.jsonl"

        parent_observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 0,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "available_actions": ["ACTION1", "ACTION6"],
                    "diff_summary": "INITIAL",
                    "value_histogram": {"1": 10, "2": 8},
                    "objects": [{"value": 1}, {"value": 2}],
                }
            ),
            encoding="utf-8",
        )
        child_observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 1,
                    "state": "NOT_FINISHED",
                    "levels_completed": 1,
                    "available_actions": ["ACTION1", "ACTION5", "ACTION6"],
                    "diff_summary": "48 cells changed",
                    "value_histogram": {"1": 5, "2": 3, "4": 10},
                    "objects": [{"value": 1}, {"value": 2}, {"value": 4}],
                }
            ),
            encoding="utf-8",
        )
        child_trace_path.write_text(
            json.dumps(
                {
                    "surprise": "Probe outcome invalidated the current navigation hypothesis.",
                    "dynamics_revision": "Object interaction model updated after click probe.",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        parent_row = {
            "episode_id": "parent-episode",
            "status": "completed",
            "observation_path": str(parent_observation_path),
        }
        child_row = {
            "episode_id": "child-episode",
            "status": "completed",
            "observation_path": str(child_observation_path),
            "trace_path": str(child_trace_path),
            "parent_episode_id": "parent-episode",
        }

        estimate = estimate_actual_information_gain_for_row(
            child_row,
            completed_rows_by_episode_id={"parent-episode": parent_row},
        )

        assert estimate.value is not None
        assert estimate.value > 0.7
        assert any("Levels completed increased" in reason for reason in estimate.reasons)
        assert any("cells changed" in reason for reason in estimate.reasons)

    def test_estimate_belief_revision_detects_pruning_and_gain_gap(self):
        parent_belief = {
            "top_motifs": [
                {"name": "threading", "confidence": 0.2},
                {"name": "navigation", "confidence": 0.3},
            ],
            "hypotheses": [
                {"hypothesis_id": "H1", "confidence": 0.4, "status": "provisional"},
                {"hypothesis_id": "H2", "confidence": 0.3, "status": "active"},
            ],
            "goal_beliefs": [
                {"summary": "Reach the target.", "confidence": 0.4},
            ],
        }
        current_belief = {
            "top_motifs": [
                {"name": "threading", "confidence": 0.45},
                {"name": "navigation", "confidence": 0.1},
            ],
            "hypotheses": [
                {"hypothesis_id": "H1", "confidence": 0.65, "status": "confirmed"},
                {"hypothesis_id": "H2", "confidence": 0.05, "status": "discarded"},
            ],
            "goal_beliefs": [
                {"summary": "Reach the target.", "confidence": 0.75},
            ],
        }

        estimate = estimate_belief_revision(
            current_belief=current_belief,
            parent_belief=parent_belief,
            expected_information_gain=0.8,
            actual_information_gain=0.1,
            trace_tail={"surprise": "Observed outcome contradicted the current plan."},
        )

        assert estimate.belief_revision_score is not None
        assert estimate.belief_revision_score > 0.2
        assert estimate.hypothesis_pruning_count == 1
        assert estimate.surprise_magnitude is not None
        assert estimate.surprise_magnitude >= 0.6
        assert any("pruned" in reason for reason in estimate.reasons)

    def test_estimate_belief_revision_can_fallback_to_trace_signals_without_ledgers(self):
        estimate = estimate_belief_revision(
            current_belief=None,
            parent_belief=None,
            trace_tail={
                "belief_revision_score": 0.61,
                "hypothesis_pruning_count": 2,
                "surprise_magnitude": 0.74,
                "belief_revision_summary": [
                    "Action semantics for ACTION6 were revised.",
                ],
                "suggested_hypotheses": [
                    "ACTION6 may activate a local switch.",
                ],
                "motif_updates": [
                    "Navigation motif confidence dropped; switch-activation motif rose.",
                ],
                "anchoring_alerts": [
                    "Original navigation anchor is no longer reliable.",
                ],
            },
        )

        assert estimate.belief_revision_score == 0.61
        assert estimate.hypothesis_pruning_count == 2
        assert estimate.surprise_magnitude == 0.74
        assert any(
            "Current belief ledger is unavailable." in reason
            for reason in estimate.reasons
        )
        assert any(
            "Action semantics for ACTION6 were revised." in reason
            for reason in estimate.reasons
        )
        assert any(
            "Suggested hypotheses:" in reason
            for reason in estimate.reasons
        )
        assert any(
            "Anchoring alerts:" in reason
            for reason in estimate.reasons
        )

    def test_estimate_episode_epistemic_metrics_for_row_combines_actual_and_belief_signals(
        self, tmp_path
    ):
        parent_observation_path = tmp_path / "parent.observation.json"
        child_observation_path = tmp_path / "child.observation.json"
        parent_belief_path = tmp_path / "parent.belief.json"
        child_belief_path = tmp_path / "child.belief.json"
        child_trace_path = tmp_path / "child.trace.jsonl"

        parent_observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 0,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "available_actions": ["ACTION1", "ACTION6"],
                    "diff_summary": "INITIAL",
                    "value_histogram": {"1": 10},
                    "objects": [{"value": 1}, {"value": 2}],
                }
            ),
            encoding="utf-8",
        )
        child_observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 1,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "available_actions": ["ACTION1", "ACTION5", "ACTION6"],
                    "diff_summary": "32 cells changed",
                    "value_histogram": {"1": 6, "4": 8},
                    "objects": [{"value": 1}, {"value": 2}, {"value": 4}],
                }
            ),
            encoding="utf-8",
        )
        parent_belief_path.write_text(
            json.dumps(
                {
                    "top_motifs": [
                        {"name": "threading", "confidence": 0.2},
                        {"name": "navigation", "confidence": 0.35},
                    ],
                    "hypotheses": [
                        {"hypothesis_id": "H1", "confidence": 0.4, "status": "provisional"},
                        {"hypothesis_id": "H2", "confidence": 0.25, "status": "active"},
                    ],
                    "goal_beliefs": [
                        {"summary": "Reach the target.", "confidence": 0.3},
                    ],
                }
            ),
            encoding="utf-8",
        )
        child_belief_path.write_text(
            json.dumps(
                {
                    "top_motifs": [
                        {"name": "threading", "confidence": 0.45},
                        {"name": "navigation", "confidence": 0.1},
                    ],
                    "hypotheses": [
                        {"hypothesis_id": "H1", "confidence": 0.55, "status": "confirmed"},
                        {"hypothesis_id": "H2", "confidence": 0.05, "status": "discarded"},
                    ],
                    "goal_beliefs": [
                        {"summary": "Reach the target.", "confidence": 0.7},
                    ],
                }
            ),
            encoding="utf-8",
        )
        child_trace_path.write_text(
            json.dumps({"surprise": "Outcome contradicted the previous click model."}) + "\n",
            encoding="utf-8",
        )

        parent_row = {
            "episode_id": "parent-episode",
            "status": "completed",
            "observation_path": str(parent_observation_path),
            "belief_path": str(parent_belief_path),
        }
        child_row = {
            "episode_id": "child-episode",
            "status": "completed",
            "parent_episode_id": "parent-episode",
            "observation_path": str(child_observation_path),
            "belief_path": str(child_belief_path),
            "trace_path": str(child_trace_path),
            "expected_information_gain": 0.75,
        }

        metrics = estimate_episode_epistemic_metrics_for_row(
            child_row,
            completed_rows_by_episode_id={"parent-episode": parent_row},
        )

        assert metrics.actual_information_gain is not None
        assert metrics.actual_information_gain > 0.2
        assert metrics.belief_revision_score is not None
        assert metrics.belief_revision_score > 0.2
        assert metrics.hypothesis_pruning_count == 1
        assert metrics.surprise_magnitude is not None
        assert metrics.surprise_magnitude >= 0.6

    def test_estimate_rule_discovery_detects_new_world_model_structures(self):
        parent_belief = {
            "dynamics_rules": [
                {"action_name": "ACTION1", "condition": "always", "effect": "move up"}
            ],
            "interaction_rules": [],
            "regions": [
                {
                    "region_id": "REG_1",
                    "name": "play_area",
                    "role": "play_area",
                    "row_min": 8,
                    "row_max": 49,
                    "col_min": 6,
                    "col_max": 55,
                    "dominant_value": 5,
                    "traversable": True,
                }
            ],
            "reference_patterns": [],
        }
        current_belief = {
            "dynamics_rules": [
                {"action_name": "ACTION1", "condition": "always", "effect": "move up"},
                {"action_name": "ACTION6", "condition": "click on switch", "effect": "toggle door"},
            ],
            "interaction_rules": [
                {
                    "trigger_pid": "P_ctrl_1",
                    "affected_pid": "P_box_2",
                    "trigger_action": "ACTION1",
                    "rule_type": "push",
                    "effect": "move box forward",
                }
            ],
            "regions": [
                {
                    "region_id": "REG_1",
                    "name": "play_area",
                    "role": "play_area",
                    "row_min": 8,
                    "row_max": 49,
                    "col_min": 6,
                    "col_max": 55,
                    "dominant_value": 5,
                    "traversable": True,
                },
                {
                    "region_id": "REG_2",
                    "name": "wall_v5",
                    "role": "barrier",
                    "row_min": 8,
                    "row_max": 49,
                    "col_min": 20,
                    "col_max": 21,
                    "dominant_value": 5,
                    "traversable": False,
                },
            ],
            "reference_patterns": [
                {
                    "surface_id": "REF_5",
                    "kind": "reference_box",
                    "pattern_rows": ["5555555", "5599955"],
                    "pattern_description": "▓(5)x43, ◆(9)x6",
                }
            ],
        }

        (
            score,
            reasons,
            new_dynamics,
            new_interactions,
            new_regions,
            new_patterns,
        ) = estimate_rule_discovery(current_belief, parent_belief)

        assert score is not None
        assert score > 0.4
        assert new_dynamics == 1
        assert new_interactions == 1
        assert new_regions == 1
        assert new_patterns == 1
        assert any("new dynamics rule" in reason for reason in reasons)

    def test_estimate_episode_epistemic_metrics_includes_rule_discovery_bonus(self, tmp_path):
        parent_observation_path = tmp_path / "parent.observation.json"
        child_observation_path = tmp_path / "child.observation.json"
        parent_belief_path = tmp_path / "parent.belief.json"
        child_belief_path = tmp_path / "child.belief.json"

        parent_observation_path.write_text(
            json.dumps(
                {
                    "game_id": "ls20",
                    "step_index": 0,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "available_actions": ["ACTION1", "ACTION6"],
                    "diff_summary": "INITIAL",
                    "value_histogram": {"5": 40},
                    "objects": [{"value": 5}],
                }
            ),
            encoding="utf-8",
        )
        child_observation_path.write_text(
            json.dumps(
                {
                    "game_id": "ls20",
                    "step_index": 1,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "available_actions": ["ACTION1", "ACTION6"],
                    "diff_summary": "NO CHANGE",
                    "value_histogram": {"5": 40},
                    "objects": [{"value": 5}],
                }
            ),
            encoding="utf-8",
        )
        parent_belief_path.write_text(
            json.dumps(
                {
                    "top_motifs": [{"name": "navigation", "confidence": 0.2}],
                    "hypotheses": [],
                    "goal_beliefs": [],
                    "dynamics_rules": [],
                    "interaction_rules": [],
                    "regions": [],
                    "reference_patterns": [],
                }
            ),
            encoding="utf-8",
        )
        child_belief_path.write_text(
            json.dumps(
                {
                    "top_motifs": [{"name": "navigation", "confidence": 0.2}],
                    "hypotheses": [],
                    "goal_beliefs": [],
                    "dynamics_rules": [
                        {"action_name": "ACTION1", "condition": "always", "effect": "move up"}
                    ],
                    "interaction_rules": [],
                    "regions": [
                        {
                            "region_id": "REG_1",
                            "name": "play_area",
                            "role": "play_area",
                            "row_min": 8,
                            "row_max": 49,
                            "col_min": 6,
                            "col_max": 55,
                            "dominant_value": 5,
                            "traversable": True,
                        }
                    ],
                    "reference_patterns": [
                        {
                            "surface_id": "REF_5",
                            "kind": "reference_box",
                            "pattern_rows": ["5555555", "5599955"],
                            "pattern_description": "▓(5)x43, ◆(9)x6",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        parent_row = {
            "episode_id": "parent-episode",
            "status": "completed",
            "observation_path": str(parent_observation_path),
            "belief_path": str(parent_belief_path),
        }
        child_row = {
            "episode_id": "child-episode",
            "status": "completed",
            "parent_episode_id": "parent-episode",
            "observation_path": str(child_observation_path),
            "belief_path": str(child_belief_path),
        }

        metrics = estimate_episode_epistemic_metrics_for_row(
            child_row,
            completed_rows_by_episode_id={"parent-episode": parent_row},
        )

        assert metrics.rule_discovery_score is not None
        assert metrics.rule_discovery_score > 0.2
        assert metrics.new_dynamics_rules_count == 1
        assert metrics.new_region_count == 1
        assert metrics.reference_pattern_update_count == 1
        assert metrics.actual_information_gain is not None
        assert metrics.actual_information_gain > 0.0
