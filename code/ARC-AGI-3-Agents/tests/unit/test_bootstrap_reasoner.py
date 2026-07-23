"""[Mar 30] Created by SD with GPT-5.4."""

import pytest

from agents.agentic.bootstrap_reasoner import (
    build_bootstrap_ledger,
    suggest_next_probe,
)
from agents.agentic.schemas import ObjectSummary, ObservationSnapshot


@pytest.mark.unit
class TestBootstrapReasoner:
    def test_build_bootstrap_ledger_infers_motifs_and_hypotheses(self):
        observation = ObservationSnapshot(
            game_id="sk48",
            step_index=0,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=64,
            grid_cols=64,
            available_actions=["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION6"],
            diff_summary="INITIAL",
            objects=[
                ObjectSummary(
                    value=6,
                    char="A",
                    cell_count=4,
                    row_min=2,
                    row_max=3,
                    col_min=2,
                    col_max=3,
                ),
                ObjectSummary(
                    value=7,
                    char="B",
                    cell_count=4,
                    row_min=52,
                    row_max=53,
                    col_min=50,
                    col_max=51,
                ),
                ObjectSummary(
                    value=8,
                    char="C",
                    cell_count=4,
                    row_min=30,
                    row_max=31,
                    col_min=28,
                    col_max=29,
                ),
            ],
        )

        ledger = build_bootstrap_ledger(
            "sk48-episode-001",
            observation,
            seeded_names=["threading"],
        )

        assert ledger.episode_id == "sk48-episode-001"
        assert ledger.top_motifs
        assert ledger.hypotheses
        assert "ACTION6" in ledger.action_semantics
        assert any(note.startswith("Bootstrap ledger enriched") for note in ledger.notes)

    def test_suggest_next_probe_prefers_untried_action(self):
        observation = ObservationSnapshot(
            game_id="sk48",
            step_index=0,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=64,
            grid_cols=64,
            available_actions=["ACTION1", "ACTION2", "ACTION6"],
            action_history=["ACTION1"],
            diff_summary="INITIAL",
        )
        ledger = build_bootstrap_ledger("sk48-episode-002", observation)

        probe = suggest_next_probe(observation, ledger)

        assert probe.action == "ACTION2"
        assert probe.expected_information_gain > 0.0
        assert "ACTION2" in probe.rationale
