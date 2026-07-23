"""[Mar 29] Created by SD with GPT-5.4."""

import json
from pathlib import Path

import pytest

from scripts.agentic_supervisor import (
    QueueItem,
    append_manifest,
    append_queue_item,
    build_solver_command,
    derive_followup_item,
    evaluate_bootstrap_phase,
    expand_probe_action_for_queue,
    load_queue,
    ordered_tested_actions,
    run_queue_item,
    select_next_probe,
)
from agents.agentic.bootstrap_reasoner import build_bootstrap_ledger
from agents.agentic.schemas import HypothesisEntry, ObservationSnapshot


@pytest.mark.unit
class TestAgenticSupervisor:
    def test_load_queue(self, tmp_path):
        queue_path = tmp_path / "queue.jsonl"
        queue_path.write_text(
            json.dumps(
                {
                    "queue_id": "q1",
                    "game_id": "sk48",
                    "actions": ["RESET", "ACTION1"],
                    "motif_names": ["threading"],
                    "tags": ["nightly"],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        items = load_queue(queue_path)
        assert len(items) == 1
        assert isinstance(items[0], QueueItem)
        assert items[0].game_id == "sk48"
        assert items[0].actions[-1] == "ACTION1"

    def test_append_manifest(self, tmp_path):
        manifest_path = tmp_path / "manifest.jsonl"
        append_manifest(manifest_path, {"status": "planned", "game_id": "sk48"})
        append_manifest(manifest_path, {"status": "completed", "game_id": "ls20"})

        lines = manifest_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["status"] == "planned"
        assert parsed[1]["game_id"] == "ls20"

    def test_append_queue_item(self, tmp_path):
        queue_path = tmp_path / "followup.jsonl"
        append_queue_item(queue_path, {"queue_id": "q2", "game_id": "sk48", "depth": 1})

        lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["queue_id"] == "q2"
        assert parsed["depth"] == 1

    def test_queue_item_roundtrip_preserves_solver_fields(self):
        item = QueueItem(
            game_id="sk48",
            actions=["RESET"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=["Seed solve-loop job."],
            queue_id="q-solve-001",
            runner="solve_loop",
            max_steps=128,
            llm_model="gpt-5.4-mini",
            llm_memory_window=8,
        )

        payload = item.to_dict()
        restored = QueueItem.from_dict(payload)

        assert restored.runner == "solve_loop"
        assert restored.max_steps == 128
        assert restored.llm_model == "gpt-5.4-mini"
        assert restored.llm_memory_window == 8
        assert restored.queue_id == "q-solve-001"

    def test_build_solver_command_includes_wrapper_and_result_json(self, tmp_path):
        item = QueueItem(
            game_id="sk48",
            actions=["RESET"],
            motif_names=[],
            tags=[],
            notes=[],
            runner="solve_loop",
            max_steps=77,
            llm_model="gpt-5.4-mini",
            llm_memory_window=8,
        )
        command = build_solver_command(
            python_bin="/tmp/python",
            solver_wrapper_path=Path("/tmp/run_agentic_solver_job.py"),
            item=item,
            output_root=tmp_path / "episodes",
            result_json_path=tmp_path / "solve-result.json",
        )

        assert command == [
            "/tmp/python",
            "/tmp/run_agentic_solver_job.py",
            "--game",
            "sk48",
            "--memory-root",
            str(tmp_path / "episodes"),
            "--result-json",
            str(tmp_path / "solve-result.json"),
            "--quiet",
            "--max-steps",
            "77",
            "--llm-model",
            "gpt-5.4-mini",
            "--llm-memory-window",
            "8",
        ]

    def test_run_queue_item_dry_run_for_solver_emits_planned_manifest(self, tmp_path):
        manifest_path = tmp_path / "manifest.jsonl"
        item = QueueItem(
            game_id="sk48",
            actions=["RESET"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=["Dry-run solve-loop job."],
            queue_id="q-solve-dryrun",
            runner="solve_loop",
            max_steps=64,
            expected_mode="instrumental",
        )

        result = run_queue_item(
            item=item,
            output_root=tmp_path / "episodes",
            python_bin="/tmp/python",
            harness_path=Path("/tmp/harness.py"),
            manifest_path=manifest_path,
            dry_run=True,
            solver_wrapper_path=Path("/tmp/run_agentic_solver_job.py"),
        )

        assert result["status"] == "planned"
        assert result["runner"] == "solve_loop"
        assert result["max_steps"] == 64
        assert result["episode_root"] is None
        manifest_lines = manifest_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(manifest_lines) == 1
        manifest_payload = json.loads(manifest_lines[0])
        assert manifest_payload["runner"] == "solve_loop"
        assert manifest_payload["queue_id"] == "q-solve-dryrun"

    def test_derive_followup_item(self):
        item = QueueItem(
            game_id="sk48",
            actions=["RESET"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=["Initial scene capture."],
            queue_id="q-sk48-0001",
        )

        followup = derive_followup_item(
            item=item,
            episode_id="sk48-episode-001",
            probe_action="ACTION1",
            probe_rationale="Test upward mobility.",
            expected_outcome="Clarify vertical navigation semantics.",
            mode="epistemic",
            probe_family="experiment-designer-followup",
            expected_information_gain=0.72,
        )

        assert followup.actions == ["RESET", "ACTION1"]
        assert followup.depth == 1
        assert followup.parent_episode_id == "sk48-episode-001"
        assert "followup" in followup.tags
        assert followup.goal_hint == "Clarify vertical navigation semantics."
        assert followup.probe_family == "experiment-designer-followup"
        assert followup.expected_information_gain == 0.72

    def test_expand_probe_action_for_queue_handles_sequences_and_clicks(self):
        assert expand_probe_action_for_queue("ACTION1") == ["ACTION1"]
        assert expand_probe_action_for_queue(
            {"sequence": ["ACTION1", "ACTION2"], "probe_type": "reversibility_pair"}
        ) == ["ACTION1", "ACTION2"]
        assert expand_probe_action_for_queue(
            {"action": "ACTION6", "coordinate": [10, 10]}
        ) == ["ACTION6"]

    def test_ordered_tested_actions_preserves_order_and_dedupes(self):
        ordered = ordered_tested_actions(
            ["RESET", "ACTION1", "ACTION1"],
            ["ACTION2", {"action": "ACTION6"}, "ACTION2"],
        )
        assert ordered == ["RESET", "ACTION1", "ACTION2", "ACTION6"]

    def test_select_next_probe_prefers_experiment_designer_when_available(self):
        observation = ObservationSnapshot(
            game_id="sk48",
            step_index=1,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=64,
            grid_cols=64,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION6"],
            action_history=["ACTION1"],
            diff_summary="52 cells changed",
        )
        belief = build_bootstrap_ledger(
            "sk48-episode-003",
            observation,
            seeded_names=["threading"],
        )

        probe, selector = select_next_probe(
            observation=observation,
            belief=belief,
            prior_actions=["RESET", "ACTION1"],
        )

        assert selector == "experiment_designer"
        assert probe.expected_information_gain > 0.0

    def test_evaluate_bootstrap_phase_uses_executed_prefix_not_available_actions(self):
        item = QueueItem(
            game_id="sk48",
            actions=["RESET"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=[],
            expected_mode="epistemic",
        )
        observation = ObservationSnapshot(
            game_id="sk48",
            step_index=0,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=64,
            grid_cols=64,
            available_actions=[
                "ACTION1",
                "ACTION2",
                "ACTION3",
                "ACTION4",
                "ACTION5",
                "ACTION6",
                "ACTION7",
            ],
            action_history=["RESET"],
            diff_summary="INITIAL",
        )
        belief = build_bootstrap_ledger(
            "sk48-episode-004",
            observation,
            seeded_names=["threading"],
        )
        belief.hypotheses = [
            HypothesisEntry(
                hypothesis_id="H1",
                summary="Overconfident bootstrap hypothesis",
                confidence=0.92,
                status="active",
            )
        ]

        mode, guidance, reason, budget_remaining = evaluate_bootstrap_phase(
            item=item,
            observation=observation,
            belief=belief,
            step_budget=8,
        )

        assert mode == "epistemic"
        assert "GENEROUS" in guidance
        assert "remained EPISTEMIC" in reason
        assert budget_remaining == 1.0

    def test_evaluate_bootstrap_phase_promotes_when_prefix_is_rich_enough(self):
        item = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1", "ACTION2", "ACTION3"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=[],
            expected_mode="epistemic",
        )
        observation = ObservationSnapshot(
            game_id="sk48",
            step_index=3,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=64,
            grid_cols=64,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION6"],
            action_history=["RESET", "ACTION1", "ACTION2", "ACTION3"],
            diff_summary="27 cells changed",
        )
        belief = build_bootstrap_ledger(
            "sk48-episode-005",
            observation,
            seeded_names=["threading"],
        )
        belief.hypotheses = [
            HypothesisEntry(
                hypothesis_id="H1",
                summary="Strong motif hypothesis",
                confidence=0.84,
                status="active",
            ),
            HypothesisEntry(
                hypothesis_id="H2",
                summary="Supporting hypothesis",
                confidence=0.81,
                status="active",
            ),
        ]

        mode, guidance, reason, budget_remaining = evaluate_bootstrap_phase(
            item=item,
            observation=observation,
            belief=belief,
            step_budget=8,
        )

        assert mode == "instrumental"
        assert "Confidence" in reason
        assert budget_remaining == pytest.approx(0.625)
        assert "GENEROUS" in guidance
