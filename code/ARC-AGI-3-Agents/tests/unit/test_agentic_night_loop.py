"""[Mar 30] Created by SD with GPT-5.4."""

import json

import pytest

from scripts.agentic_night_loop import build_supervisor_command, write_queue
from scripts.agentic_queue_policy import (
    build_game_histories,
    queue_signature,
    select_policy_batch,
)
from scripts.agentic_supervisor import QueueItem


@pytest.mark.unit
class TestAgenticNightLoop:
    def test_queue_signature_ignores_metadata(self):
        item_a = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=["first"],
            queue_id="q1",
        )
        item_b = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1"],
            motif_names=["navigation"],
            tags=["followup"],
            notes=["second"],
            queue_id="q2",
        )

        assert queue_signature(item_a) == queue_signature(item_b)

    def test_queue_signature_distinguishes_runner_max_steps_llm_model_and_memory_window(self):
        bootstrap_item = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=[],
            runner="bootstrap",
        )
        solve_item_short = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=[],
            runner="solve_loop",
            max_steps=32,
            llm_model="gpt-5.4-mini",
            llm_memory_window=4,
        )
        solve_item_long = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=[],
            runner="solve_loop",
            max_steps=64,
            llm_model="gpt-5.4-mini",
            llm_memory_window=4,
        )
        solve_item_other_model = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=[],
            runner="solve_loop",
            max_steps=32,
            llm_model="gpt-5.4",
            llm_memory_window=4,
        )
        solve_item_other_window = QueueItem(
            game_id="sk48",
            actions=["RESET", "ACTION1"],
            motif_names=["threading"],
            tags=["nightly"],
            notes=[],
            runner="solve_loop",
            max_steps=32,
            llm_model="gpt-5.4-mini",
            llm_memory_window=8,
        )

        assert queue_signature(bootstrap_item) != queue_signature(solve_item_short)
        assert queue_signature(solve_item_short) != queue_signature(solve_item_long)
        assert queue_signature(solve_item_short) != queue_signature(solve_item_other_model)
        assert queue_signature(solve_item_short) != queue_signature(solve_item_other_window)

    def test_build_supervisor_command_forwards_solver_wrapper(self, tmp_path):
        command = build_supervisor_command(
            python_bin="/tmp/python",
            supervisor_path=tmp_path / "agentic_supervisor.py",
            queue_path=tmp_path / "queue.jsonl",
            round_root=tmp_path / "round_000",
            harness_path=tmp_path / "harness.py",
            solver_wrapper_path=tmp_path / "run_agentic_solver_job.py",
            max_followup_depth=2,
            dry_run=False,
        )

        assert command == [
            "/tmp/python",
            str(tmp_path / "agentic_supervisor.py"),
            "--queue",
            str(tmp_path / "queue.jsonl"),
            "--output-root",
            str(tmp_path / "round_000" / "episodes"),
            "--manifest",
            str(tmp_path / "round_000" / "manifest.jsonl"),
            "--followup-queue",
            str(tmp_path / "round_000" / "followups.jsonl"),
            "--max-followup-depth",
            "2",
            "--python-bin",
            "/tmp/python",
            "--harness-path",
            str(tmp_path / "harness.py"),
            "--solver-wrapper-path",
            str(tmp_path / "run_agentic_solver_job.py"),
        ]

    def test_select_policy_batch_dedupes_seen_and_local_duplicates(self):
        pending = [
            QueueItem("sk48", ["RESET"], ["threading"], ["nightly"], [], queue_id="q1"),
            QueueItem("sk48", ["RESET"], ["threading"], ["nightly"], [], queue_id="q2"),
            QueueItem("sk48", ["RESET", "ACTION1"], ["threading"], ["nightly"], []),
            QueueItem("re86", ["RESET"], ["click-semantics"], ["nightly"], []),
        ]
        seen = {
            queue_signature(
                QueueItem("re86", ["RESET"], ["click-semantics"], ["nightly"], [])
            )
        }

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=seen,
            histories={},
            batch_size=1,
        )

        assert len(batch) == 1
        assert batch[0].game_id == "sk48"
        assert len(remainder) == 1
        assert {
            tuple(item.actions) for item in [*batch, *remainder]
        } == {("RESET",), ("RESET", "ACTION1")}
        assert any(
            "Duplicate action prefix inside pending queue." in reason
            for assessment in assessments
            for reason in assessment.reasons
        )

    def test_policy_prefers_fresh_game_over_stagnant_followup(self, tmp_path):
        observation_path = tmp_path / "observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 0,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "diff_summary": "INITIAL",
                }
            ),
            encoding="utf-8",
        )
        manifest_rows = [
            {
                "status": "completed",
                "game_id": "sk48",
                "observation_path": str(observation_path),
                "probe_family": "bootstrap-followup",
                "goal_hint": "Clarify the semantics of ACTION1.",
            },
            {
                "status": "completed",
                "game_id": "sk48",
                "observation_path": str(observation_path),
                "probe_family": "bootstrap-followup",
                "goal_hint": "Clarify the semantics of ACTION1.",
            },
        ]
        histories = build_game_histories(manifest_rows)
        pending = [
            QueueItem(
                "sk48",
                ["RESET", "ACTION2"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="bootstrap-followup",
                goal_hint="Clarify the semantics of ACTION2.",
                expected_information_gain=0.18,
                depth=1,
            ),
            QueueItem(
                "re86",
                ["RESET"],
                ["click-semantics"],
                ["nightly"],
                [],
                expected_mode="epistemic",
                probe_family="bootstrap-followup",
                goal_hint="Clarify the semantics of ACTION1.",
                expected_information_gain=0.42,
                depth=0,
            ),
        ]

        batch, remainder, _ = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=1,
            stagnation_threshold=2,
        )

        assert len(batch) == 1
        assert batch[0].game_id == "re86"
        assert len(remainder) == 1
        assert remainder[0].game_id == "sk48"

    def test_policy_prefers_experiment_designer_followup_under_stagnation(self, tmp_path):
        observation_path = tmp_path / "observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 0,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "diff_summary": "INITIAL",
                }
            ),
            encoding="utf-8",
        )
        manifest_rows = [
            {
                "status": "completed",
                "game_id": "sk48",
                "observation_path": str(observation_path),
                "probe_family": "bootstrap-followup",
                "goal_hint": "Clarify ACTION1.",
                "next_probe_selector": "bootstrap_reasoner_fallback",
            },
            {
                "status": "completed",
                "game_id": "sk48",
                "observation_path": str(observation_path),
                "probe_family": "bootstrap-followup",
                "goal_hint": "Clarify ACTION1.",
                "next_probe_selector": "bootstrap_reasoner_fallback",
            },
        ]
        histories = build_game_histories(manifest_rows)
        pending = [
            QueueItem(
                "sk48",
                ["RESET", "ACTION1"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="bootstrap-followup",
                goal_hint="Clarify ACTION1.",
                expected_information_gain=0.18,
                depth=1,
            ),
            QueueItem(
                "sk48",
                ["RESET", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Reveal ACTION6 semantics.",
                expected_information_gain=0.81,
                depth=1,
            ),
        ]

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=1,
            max_items_per_game=1,
            stagnation_threshold=2,
        )

        assert len(batch) == 1
        assert batch[0].actions == ["RESET", "ACTION6"]
        assert len(remainder) == 1
        assert remainder[0].actions == ["RESET", "ACTION1"]

        scores = {tuple(a.item.actions): a.score for a in assessments if a.keep}
        assert scores[("RESET", "ACTION6")] > scores[("RESET", "ACTION1")]

    def test_policy_prefers_higher_expected_information_gain_within_same_family(self):
        pending = [
            QueueItem(
                "g50t",
                ["RESET", "ACTION1"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Test horizontal motion.",
                expected_information_gain=0.22,
                depth=1,
            ),
            QueueItem(
                "g50t",
                ["RESET", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Test click semantics.",
                expected_information_gain=0.84,
                depth=1,
            ),
        ]

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories={},
            batch_size=1,
            max_items_per_game=1,
        )

        assert len(batch) == 1
        assert batch[0].actions == ["RESET", "ACTION6"]
        assert len(remainder) == 1
        assert remainder[0].actions == ["RESET", "ACTION1"]

        scores = {tuple(a.item.actions): a.score for a in assessments if a.keep}
        assert scores[("RESET", "ACTION6")] > scores[("RESET", "ACTION1")]

    def test_policy_uses_recent_actual_information_gain_baseline(self, tmp_path):
        parent_observation_path = tmp_path / "parent.observation.json"
        child_observation_path = tmp_path / "child.observation.json"

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
                    "available_actions": ["ACTION1", "ACTION6"],
                    "diff_summary": "NO CHANGE",
                    "value_histogram": {"1": 10},
                    "objects": [{"value": 1}, {"value": 2}],
                }
            ),
            encoding="utf-8",
        )

        manifest_rows = [
            {
                "status": "completed",
                "episode_id": "parent-episode",
                "game_id": "sk48",
                "observation_path": str(parent_observation_path),
            },
            {
                "status": "completed",
                "episode_id": "child-episode",
                "game_id": "sk48",
                "observation_path": str(child_observation_path),
                "parent_episode_id": "parent-episode",
                "probe_family": "experiment-designer-followup",
                "next_probe_selector": "experiment_designer",
            },
        ]
        histories = build_game_histories(manifest_rows)

        pending = [
            QueueItem(
                "sk48",
                ["RESET", "ACTION1", "ACTION2"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Test alternate movement.",
                expected_information_gain=0.05,
                depth=2,
            ),
            QueueItem(
                "sk48",
                ["RESET", "ACTION1", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Test click semantics.",
                expected_information_gain=0.72,
                depth=2,
            ),
        ]

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=1,
            max_items_per_game=1,
        )

        assert len(batch) == 1
        assert batch[0].actions == ["RESET", "ACTION1", "ACTION6"]
        assert len(remainder) == 1
        assert histories["sk48"].recent_actual_information_gains == [0.0]

        reasons_by_action = {
            tuple(assessment.item.actions): assessment.reasons
            for assessment in assessments
            if assessment.keep
        }
        assert any(
            "recent actual-gain baseline" in reason
            for reason in reasons_by_action[("RESET", "ACTION1", "ACTION6")]
        )

    def test_policy_prefers_epistemic_probe_when_recent_rule_discovery_is_high(self, tmp_path):
        observation_path = tmp_path / "observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "ls20",
                    "step_index": 1,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "diff_summary": "18 cells changed",
                }
            ),
            encoding="utf-8",
        )
        manifest_rows = [
            {
                "status": "completed",
                "game_id": "ls20",
                "observation_path": str(observation_path),
                "probe_family": "experiment-designer-followup",
                "next_probe_selector": "experiment_designer",
                "rule_discovery_score": 0.74,
                "new_dynamics_rules_count": 1,
                "new_interaction_rules_count": 1,
                "new_region_count": 1,
                "reference_pattern_update_count": 1,
            }
        ]
        histories = build_game_histories(manifest_rows)
        pending = [
            QueueItem(
                "ls20",
                ["RESET", "ACTION6"],
                ["navigation"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Clarify the reference box semantics.",
                expected_information_gain=0.51,
                depth=1,
            ),
            QueueItem(
                "ls20",
                ["RESET", "ACTION1"],
                ["navigation"],
                ["followup"],
                [],
                expected_mode="instrumental",
                probe_family="experiment-designer-followup",
                goal_hint="Push directly toward the target.",
                expected_information_gain=0.54,
                depth=1,
            ),
        ]

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=1,
            max_items_per_game=1,
        )

        assert len(batch) == 1
        assert batch[0].expected_mode == "epistemic"
        assert len(remainder) == 1
        assert remainder[0].expected_mode == "instrumental"

        reasons_by_mode = {
            assessment.item.expected_mode: assessment.reasons
            for assessment in assessments
            if assessment.keep
        }
        assert any(
            "world-model structure" in reason for reason in reasons_by_mode["epistemic"]
        )

    def test_policy_prefers_epistemic_reprobe_after_recovery(self, tmp_path):
        observation_path = tmp_path / "recovery.observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 2,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "diff_summary": "NO CHANGE",
                }
            ),
            encoding="utf-8",
        )
        histories = build_game_histories(
            [
                {
                    "status": "completed",
                    "game_id": "sk48",
                    "observation_path": str(observation_path),
                    "resolved_mode": "recovery",
                    "phase_transition_reason": "Plan failed -- expected outcome did not occur.",
                }
            ]
        )
        pending = [
            QueueItem(
                "sk48",
                ["RESET", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Re-probe click semantics after failure.",
                expected_information_gain=0.45,
                depth=1,
            ),
            QueueItem(
                "sk48",
                ["RESET", "ACTION5"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="instrumental",
                probe_family="experiment-designer-followup",
                goal_hint="Commit to a solve attempt.",
                expected_information_gain=0.65,
                depth=1,
            ),
        ]

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=1,
            max_items_per_game=1,
            stagnation_threshold=1,
        )

        assert len(batch) == 1
        assert batch[0].expected_mode == "epistemic"
        assert len(remainder) == 1
        assert remainder[0].expected_mode == "instrumental"
        epistemic_assessment = next(
            assessment
            for assessment in assessments
            if assessment.keep and assessment.item.expected_mode == "epistemic"
        )
        assert any(
            "Recent recovery suggests re-probing before another solve attempt."
            in reason
            for reason in epistemic_assessment.reasons
        )

    def test_recovery_cooling_off_defers_instrumental_items_for_one_round(self, tmp_path):
        observation_path = tmp_path / "recovery-cooloff.observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 2,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "diff_summary": "NO CHANGE",
                }
            ),
            encoding="utf-8",
        )
        histories = build_game_histories(
            [
                {
                    "status": "completed",
                    "game_id": "sk48",
                    "observation_path": str(observation_path),
                    "resolved_mode": "recovery",
                }
            ]
        )
        pending = [
            QueueItem(
                "sk48",
                ["RESET", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Re-probe after failure.",
                expected_information_gain=0.4,
                depth=1,
            ),
            QueueItem(
                "sk48",
                ["RESET", "ACTION5"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="instrumental",
                probe_family="experiment-designer-followup",
                goal_hint="Resume solving.",
                expected_information_gain=0.7,
                depth=1,
            ),
        ]

        batch, remainder, _ = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=2,
            max_items_per_game=2,
            stagnation_threshold=1,
        )

        assert [item.expected_mode for item in batch] == ["epistemic"]
        assert [item.expected_mode for item in remainder] == ["instrumental"]

    def test_policy_prefers_instrumental_followup_after_progress(self, tmp_path):
        observation_path = tmp_path / "progress.observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "g50t",
                    "step_index": 3,
                    "state": "NOT_FINISHED",
                    "levels_completed": 1,
                    "diff_summary": "34 cells changed",
                }
            ),
            encoding="utf-8",
        )
        histories = build_game_histories(
            [
                {
                    "status": "completed",
                    "game_id": "g50t",
                    "observation_path": str(observation_path),
                    "resolved_mode": "instrumental",
                    "phase_transition_reason": "Confidence 0.81 > 0.7, 4 actions tested, no recent SEVERE surprises.",
                }
            ]
        )
        pending = [
            QueueItem(
                "g50t",
                ["RESET", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Collect one more probe.",
                expected_information_gain=0.52,
                depth=1,
            ),
            QueueItem(
                "g50t",
                ["RESET", "ACTION5"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="instrumental",
                probe_family="experiment-designer-followup",
                goal_hint="Exploit the current solve theory.",
                expected_information_gain=0.52,
                depth=1,
            ),
        ]

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=1,
            max_items_per_game=1,
        )

        assert len(batch) == 1
        assert batch[0].expected_mode == "instrumental"
        assert len(remainder) == 1
        assert remainder[0].expected_mode == "epistemic"
        instrumental_assessment = next(
            assessment
            for assessment in assessments
            if assessment.keep and assessment.item.expected_mode == "instrumental"
        )
        assert any(
            "Prior progress supports another instrumental attempt." in reason
            for reason in instrumental_assessment.reasons
        )

    def test_progress_history_can_expand_per_game_batch_cap(self, tmp_path):
        observation_path = tmp_path / "progress-cap.observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "g50t",
                    "step_index": 4,
                    "state": "NOT_FINISHED",
                    "levels_completed": 1,
                    "diff_summary": "18 cells changed",
                }
            ),
            encoding="utf-8",
        )
        histories = build_game_histories(
            [
                {
                    "status": "completed",
                    "game_id": "g50t",
                    "observation_path": str(observation_path),
                    "resolved_mode": "instrumental",
                    "phase_transition_reason": "Confidence was strong enough to solve.",
                }
            ]
        )
        pending = [
            QueueItem(
                "g50t",
                ["RESET", "ACTION5"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="instrumental",
                probe_family="experiment-designer-followup",
                goal_hint="Press the solve action again.",
                expected_information_gain=0.61,
                depth=1,
            ),
            QueueItem(
                "g50t",
                ["RESET", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="instrumental",
                probe_family="experiment-designer-followup",
                goal_hint="Try alternate solve branch.",
                expected_information_gain=0.58,
                depth=1,
            ),
        ]

        batch, remainder, _ = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=2,
            max_items_per_game=1,
        )

        assert len(batch) == 2
        assert all(item.game_id == "g50t" for item in batch)
        assert remainder == []

    def test_policy_prefers_epistemic_probe_when_belief_revision_is_still_hot(self, tmp_path):
        observation_path = tmp_path / "belief-revision.observation.json"
        observation_path.write_text(
            json.dumps(
                {
                    "game_id": "sk48",
                    "step_index": 4,
                    "state": "NOT_FINISHED",
                    "levels_completed": 0,
                    "diff_summary": "12 cells changed",
                }
            ),
            encoding="utf-8",
        )
        histories = build_game_histories(
            [
                {
                    "status": "completed",
                    "game_id": "sk48",
                    "observation_path": str(observation_path),
                    "resolved_mode": "epistemic",
                    "belief_revision_score": 0.42,
                    "hypothesis_pruning_count": 2,
                }
            ]
        )
        pending = [
            QueueItem(
                "sk48",
                ["RESET", "ACTION6"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="epistemic",
                probe_family="experiment-designer-followup",
                goal_hint="Clarify click semantics after a large belief update.",
                expected_information_gain=0.36,
                depth=1,
            ),
            QueueItem(
                "sk48",
                ["RESET", "ACTION5"],
                ["threading"],
                ["followup"],
                [],
                expected_mode="instrumental",
                probe_family="experiment-designer-followup",
                goal_hint="Push the current solve theory immediately.",
                expected_information_gain=0.60,
                depth=1,
            ),
        ]

        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures=set(),
            histories=histories,
            batch_size=1,
            max_items_per_game=1,
        )

        assert len(batch) == 1
        assert batch[0].expected_mode == "epistemic"
        assert len(remainder) == 1
        assert remainder[0].expected_mode == "instrumental"

        reasons_by_mode = {
            assessment.item.expected_mode: assessment.reasons
            for assessment in assessments
            if assessment.keep
        }
        assert any(
            "Recent belief revisions are substantial" in reason
            for reason in reasons_by_mode["epistemic"]
        )
        assert any(
            "Recent probes pruned hypotheses" in reason
            for reason in reasons_by_mode["epistemic"]
        )
        assert any(
            "Beliefs are still moving quickly without level progress" in reason
            for reason in reasons_by_mode["instrumental"]
        )

    def test_write_queue_serializes_jsonl(self, tmp_path):
        queue_path = tmp_path / "queue.jsonl"
        items = [
            QueueItem(
                game_id="sk48",
                actions=["RESET", "ACTION1"],
                motif_names=["threading"],
                tags=["nightly"],
                notes=["probe"],
                queue_id="q1",
            )
        ]

        write_queue(queue_path, items)

        lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["game_id"] == "sk48"
        assert payload["actions"] == ["RESET", "ACTION1"]
