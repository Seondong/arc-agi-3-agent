"""[Mar 31] Created by SD with GPT-5.4."""

import pytest

from scripts.convert_episodes_to_sft import build_compact_state, _rank_objects


@pytest.mark.unit
class TestConvertEpisodesToSFT:
    def test_rank_objects_keeps_role_salient_object(self):
        objects = [
            {
                "value": 7,
                "cell_count": 3,
                "row_min": 10,
                "row_max": 10,
                "col_min": 12,
                "col_max": 14,
                "persistent_id": "track-ctrl-1",
                "controllable_score": 0.91,
                "goal_score": 0.0,
                "blocker_score": 0.0,
                "click_score": 0.0,
            },
            {
                "value": 2,
                "cell_count": 80,
                "row_min": 0,
                "row_max": 20,
                "col_min": 0,
                "col_max": 20,
                "persistent_id": "track-large-1",
                "controllable_score": 0.0,
                "goal_score": 0.0,
                "blocker_score": 0.0,
                "click_score": 0.0,
            },
        ]

        ranked = _rank_objects(objects)

        assert ranked[0]["persistent_id"] == "track-ctrl-1"
        assert {obj["persistent_id"] for obj in ranked[:2]} == {
            "track-ctrl-1",
            "track-large-1",
        }

    def test_build_compact_state_includes_persistent_ids_and_role_candidates(self):
        obs = {
            "game_id": "sk48",
            "state": "NOT_FINISHED",
            "levels_completed": 0,
            "step_index": 7,
            "grid_rows": 64,
            "grid_cols": 64,
            "available_actions": ["ACTION1", "ACTION6"],
            "diff_summary": "48 cells changed",
            "action_history": ["RESET", "ACTION1", "ACTION6"],
            "objects": [
                {
                    "value": 7,
                    "cell_count": 3,
                    "row_min": 10,
                    "row_max": 10,
                    "col_min": 12,
                    "col_max": 14,
                    "persistent_id": "track-ctrl-1",
                    "controllable_score": 0.91,
                    "goal_score": 0.0,
                    "blocker_score": 0.0,
                    "click_score": 0.55,
                },
                {
                    "value": 9,
                    "cell_count": 2,
                    "row_min": 40,
                    "row_max": 40,
                    "col_min": 50,
                    "col_max": 51,
                    "persistent_id": "track-goal-2",
                    "controllable_score": 0.0,
                    "goal_score": 0.82,
                    "blocker_score": 0.0,
                    "click_score": 0.0,
                },
                {
                    "value": 4,
                    "cell_count": 5,
                    "row_min": 30,
                    "row_max": 32,
                    "col_min": 20,
                    "col_max": 21,
                    "persistent_id": "track-block-3",
                    "controllable_score": 0.0,
                    "goal_score": 0.0,
                    "blocker_score": 0.73,
                    "click_score": 0.0,
                },
            ],
        }
        belief = {
            "mode": "instrumental",
            "top_motifs": [
                {"name": "threading", "confidence": 0.88},
                {"name": "navigation", "confidence": 0.54},
            ],
        }

        state = build_compact_state(obs, belief, trace_row=None, prev_obs=None)

        assert "Role candidates:" in state
        assert "track-ct" in state
        assert "ctrl=track-ct(v7,0.91)" in state
        assert "goal=track-go(v9,0.82)" in state
        assert "block=track-bl(v4,0.73)" in state
        assert "[ctrl0.91,click0.55]" in state

    def test_build_compact_state_includes_belief_shifts_and_hypothesis_updates(self):
        obs = {
            "game_id": "sp80",
            "state": "NOT_FINISHED",
            "levels_completed": 0,
            "step_index": 11,
            "grid_rows": 64,
            "grid_cols": 64,
            "available_actions": ["ACTION1", "ACTION6"],
            "diff_summary": "12 cells changed",
            "objects": [],
        }
        belief = {"mode": "epistemic"}
        decision = {
            "belief_revision_summary": [
                "H1: 0.72->0.52 (active)",
                "H2: 0.31->0.11 (discarded)",
            ],
            "suggested_hypotheses": [
                "Consider hidden-state mechanics.",
            ],
        }

        state = build_compact_state(
            obs,
            belief,
            trace_row=None,
            prev_obs=None,
            decision=decision,
        )

        assert "Belief shifts: H1: 0.72->0.52 (active) | H2: 0.31->0.11 (discarded)" in state
        assert "Hypothesis updates: Consider hidden-state mechanics." in state

    def test_build_compact_state_includes_belief_diff_summary(self):
        obs = {
            "game_id": "sk48",
            "state": "NOT_FINISHED",
            "levels_completed": 0,
            "step_index": 14,
            "grid_rows": 64,
            "grid_cols": 64,
            "available_actions": ["ACTION1", "ACTION6"],
            "diff_summary": "24 cells changed",
            "objects": [],
        }
        belief = {"mode": "recovery"}
        decision = {
            "belief_diff": {
                "hypotheses_strengthened": 1,
                "hypotheses_weakened": 2,
                "hypotheses_discarded": 1,
                "hypotheses_suggested": 1,
                "motifs_updated": 2,
                "anchoring_alerts": 1,
                "max_confidence_delta": 0.42,
                "summary": "Suggested: hidden-state mechanics | Motifs: navigation down",
            }
        }

        state = build_compact_state(
            obs,
            belief,
            trace_row=None,
            prev_obs=None,
            decision=decision,
        )

        assert "Belief diff:" in state
        assert "hyp(up=1, down=2, x=1, new=1)" in state
        assert "motifs=2" in state
        assert "alerts=1" in state
        assert "max_d=0.42" in state

    def test_build_compact_state_includes_world_model_summaries(self):
        obs = {
            "game_id": "ls20",
            "state": "NOT_FINISHED",
            "levels_completed": 0,
            "step_index": 9,
            "grid_rows": 64,
            "grid_cols": 64,
            "available_actions": ["ACTION1", "ACTION3", "ACTION6"],
            "diff_summary": "18 cells changed",
            "objects": [],
        }
        belief = {
            "mode": "epistemic",
            "dynamics_rules": [
                {
                    "action_name": "ACTION1",
                    "effect": "move controllable up ~5 cells",
                    "confidence": 0.95,
                    "times_verified": 6,
                }
            ],
            "interaction_rules": [
                {
                    "trigger_pid": "P_ctrl_1",
                    "affected_pid": "P_box_2",
                    "rule_type": "push",
                    "effect": "moves target one cell forward",
                    "confidence": 0.72,
                    "times_observed": 4,
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
                }
            ],
            "reference_patterns": [
                {
                    "surface_id": "REF_5",
                    "kind": "reference_box",
                    "pattern_rows": ["5555555", "5599955"],
                    "pattern_description": "▓(5)x43, ◆(9)x6",
                    "confidence": 0.91,
                }
            ],
        }

        state = build_compact_state(obs, belief, trace_row=None, prev_obs=None)

        assert "Dynamics: ACTION1->move controllable up ~5 cells (c0.95,v6)" in state
        assert "Interactions: P_ctrl_1 push P_box_2:" in state
        assert "(c0.72)" in state
        assert "Regions: play_area[r8-49,c6-55,trv=1,v5]" in state
        assert "Reference pattern: REF_5:reference_box 2x7 5555555/5599955 | ▓(5)x43, ◆(9)x6" in state
