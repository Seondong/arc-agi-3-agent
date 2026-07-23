"""[Mar 31] Created by SD with GPT-5.4."""

import pytest

from agents.agentic.llm_brain import BrainDecision, LLMBrain


def _make_brain(memory_window: int = 4) -> LLMBrain:
    brain = object.__new__(LLMBrain)
    brain.model = "gpt-5.4-mini"
    brain.max_tokens = 512
    brain.temperature = 0.3
    brain.memory_window = memory_window
    brain.client = None
    brain._total_input_tokens = 0
    brain._total_output_tokens = 0
    brain._call_count = 0
    brain._memory = []
    brain._working_theory = ""
    return brain


@pytest.mark.unit
def test_append_memory_from_action6_records_target_context():
    brain = _make_brain()
    decision = BrainDecision(
        action="ACTION6",
        action_data={"x": 5, "y": 2},
        rationale="Probe the highlighted target candidate.",
        phase_reasoning="The clicked target is still unresolved.",
    )
    objects = [
        {
            "persistent_id": "P_target",
            "value": 9,
            "char": "◆",
            "row_min": 1,
            "row_max": 3,
            "col_min": 4,
            "col_max": 6,
            "cell_count": 9,
            "controllable_score": 0.0,
            "goal_score": 0.8,
            "blocker_score": 0.0,
            "click_score": 0.9,
        }
    ]
    regions = [
        {
            "region_id": "R_play",
            "role": "play_area",
            "row_min": 0,
            "row_max": 9,
            "col_min": 0,
            "col_max": 9,
        },
        {
            "region_id": "R_ref",
            "role": "reference",
            "row_min": 0,
            "row_max": 4,
            "col_min": 0,
            "col_max": 8,
        },
    ]

    brain._append_memory_from_decision(
        decision=decision,
        step_index=5,
        objects=objects,
        regions=regions,
        levels_completed=0,
    )

    entry = brain._memory[0]
    assert entry.clicked_coordinate == (5, 2)
    assert entry.target_pid == "P_target"
    assert entry.target_region_id == "R_ref"
    assert entry.candidate_status == "probing_candidate"
    assert entry.outcome_class == "pending"
    assert entry.unresolved == "The clicked target is still unresolved."


@pytest.mark.unit
def test_backfill_previous_outcome_marks_click_target_inert_and_visible_in_prompt():
    brain = _make_brain()
    decision = BrainDecision(
        action="ACTION6",
        action_data={"x": 5, "y": 2},
        rationale="Test the left reference candidate.",
        phase_reasoning="Need to determine whether this candidate is inert.",
    )
    objects = [
        {
            "persistent_id": "P_target",
            "value": 9,
            "char": "◆",
            "row_min": 1,
            "row_max": 3,
            "col_min": 4,
            "col_max": 6,
            "cell_count": 9,
            "controllable_score": 0.0,
            "goal_score": 0.8,
            "blocker_score": 0.0,
            "click_score": 0.9,
        }
    ]
    regions = [
        {
            "region_id": "R_ref",
            "role": "reference",
            "row_min": 0,
            "row_max": 4,
            "col_min": 0,
            "col_max": 8,
        }
    ]

    brain._append_memory_from_decision(
        decision=decision,
        step_index=5,
        objects=objects,
        regions=regions,
        levels_completed=0,
    )
    brain._backfill_previous_outcome(
        diff_summary="NO CHANGE",
        last_surprise="Target did nothing.",
        levels_completed=0,
    )

    entry = brain._memory[0]
    assert entry.outcome_class == "no_change"
    assert entry.candidate_status == "confirmed_inert"
    assert "P_target" in entry.avoid_note
    assert entry.surprise == "Target did nothing."

    prompt = brain._build_prompt(
        grid_summary="000\n000",
        objects=objects,
        diff_summary="NO CHANGE",
        dynamics_rules=[],
        interaction_rules=[],
        regions=regions,
        reference_patterns=[],
        hypotheses=[],
        action_beliefs={},
        goal_beliefs=[],
        available_actions=["ACTION6"],
        action_history=["RESET", "ACTION6"],
        phase="epistemic",
        step_index=6,
        levels_completed=0,
        energy_fraction=0.8,
        last_surprise="Target did nothing.",
    )

    assert "P_target" in prompt
    assert "R_ref" in prompt
    assert "OUTCOME: no_change" in prompt
    assert "STATUS: confirmed_inert" in prompt
    assert "AVOID: avoid retrying" in prompt
    assert "OPEN: Need to determine whether this candidate is inert." in prompt


@pytest.mark.unit
def test_memory_window_zero_discards_entries():
    brain = _make_brain(memory_window=0)

    brain._append_memory_from_decision(
        decision=BrainDecision(action="ACTION1", rationale="Try moving."),
        step_index=1,
        objects=[],
        regions=[],
        levels_completed=0,
    )

    assert brain._memory == []
