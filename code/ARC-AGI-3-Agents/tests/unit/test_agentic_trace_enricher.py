"""[Mar 30] Created by SD with GPT-5.4."""

import json

import pytest

from agents.agentic.schemas import TrajectoryRecord
from scripts.agentic_trace_enricher import enrich_completed_manifest_rows


@pytest.mark.unit
class TestAgenticTraceEnricher:
    def test_enrich_completed_manifest_rows_updates_trace_and_metrics_file(self, tmp_path):
        parent_root = tmp_path / "parent-episode"
        child_root = tmp_path / "child-episode"
        parent_root.mkdir()
        child_root.mkdir()

        parent_observation_path = parent_root / "step_0000.observation.json"
        child_observation_path = child_root / "step_0001.observation.json"
        parent_belief_path = parent_root / "step_0000.belief.json"
        child_belief_path = child_root / "step_0001.belief.json"
        child_trace_path = child_root / "episode_trace.jsonl"

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
                    "diff_summary": "24 cells changed",
                    "value_histogram": {"1": 5, "4": 8},
                    "objects": [{"value": 1}, {"value": 2}, {"value": 4}],
                }
            ),
            encoding="utf-8",
        )
        parent_belief_path.write_text(
            json.dumps(
                {
                    "top_motifs": [{"name": "threading", "confidence": 0.2}],
                    "hypotheses": [
                        {"hypothesis_id": "H1", "confidence": 0.4, "status": "provisional"},
                        {"hypothesis_id": "H2", "confidence": 0.3, "status": "active"},
                    ],
                    "goal_beliefs": [{"summary": "Reach the target.", "confidence": 0.3}],
                }
            ),
            encoding="utf-8",
        )
        child_belief_path.write_text(
            json.dumps(
                {
                    "top_motifs": [{"name": "threading", "confidence": 0.45}],
                    "hypotheses": [
                        {"hypothesis_id": "H1", "confidence": 0.6, "status": "confirmed"},
                        {"hypothesis_id": "H2", "confidence": 0.05, "status": "discarded"},
                    ],
                    "goal_beliefs": [{"summary": "Reach the target.", "confidence": 0.7}],
                }
            ),
            encoding="utf-8",
        )

        trace_record = TrajectoryRecord(
            episode_id="child-episode",
            game_id="sk48",
            step_index=1,
            state_summary="NOT_FINISHED | L0 | 3 objects",
            motif_beliefs={"threading": 0.45},
            active_hypotheses=["H1", "H2"],
            action_taken="ACTION6",
            prediction="Click probe should clarify semantics.",
            actual_diff="24 cells changed",
            planning_mode="epistemic",
        )
        child_trace_path.write_text(trace_record.model_dump_json() + "\n", encoding="utf-8")

        all_rows = [
            {
                "status": "completed",
                "episode_id": "parent-episode",
                "game_id": "sk48",
                "episode_root": str(parent_root),
                "observation_path": str(parent_observation_path),
                "belief_path": str(parent_belief_path),
            },
            {
                "status": "completed",
                "episode_id": "child-episode",
                "game_id": "sk48",
                "episode_root": str(child_root),
                "observation_path": str(child_observation_path),
                "belief_path": str(child_belief_path),
                "trace_path": str(child_trace_path),
                "parent_episode_id": "parent-episode",
                "expected_information_gain": 0.8,
            },
        ]

        enriched = enrich_completed_manifest_rows([all_rows[1]], all_rows)

        assert len(enriched) == 1
        assert enriched[0]["actual_information_gain"] is not None
        assert enriched[0]["belief_revision_score"] is not None
        assert enriched[0]["hypothesis_pruning_count"] == 1
        assert enriched[0]["rule_discovery_score"] == 0.0

        metrics_path = child_root / "episode_metrics.json"
        assert metrics_path.exists()
        metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        assert metrics_payload["hypothesis_pruning_count"] == 1
        assert metrics_payload["rule_discovery_score"] == 0.0

        trace_payload = json.loads(child_trace_path.read_text(encoding="utf-8").strip())
        assert trace_payload["actual_information_gain"] is not None
        assert trace_payload["belief_revision_score"] is not None
        assert trace_payload["hypothesis_pruning_count"] == 1
