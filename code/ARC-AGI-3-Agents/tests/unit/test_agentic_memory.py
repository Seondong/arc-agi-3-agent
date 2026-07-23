"""[Mar 29] Created by SD with GPT-5.4."""

import json

import pytest

from agents.agentic.memory import (
    EpisodeMemoryStore,
    TrajectoryCurator,
    bootstrap_belief_ledger,
)
from agents.agentic.schemas import (
    BeliefDiffSummary,
    DecisionRecord,
    DynamicsRule,
    InteractionRule,
    ObservationSnapshot,
    ReferencePatternSummary,
    Region,
)


@pytest.mark.unit
class TestAgenticMemory:
    def test_episode_store_can_use_explicit_episode_id(self, tmp_path):
        store = EpisodeMemoryStore.create(
            tmp_path,
            game_id="sk48",
            tags=["test"],
            episode_id="sk48-explicit-episode",
        )

        assert store.metadata.episode_id == "sk48-explicit-episode"
        assert store.root.name == "sk48-explicit-episode"

    def test_episode_store_writes_structured_files(self, tmp_path):
        store = EpisodeMemoryStore.create(tmp_path, game_id="sk48", tags=["test"])

        observation = ObservationSnapshot(
            game_id="sk48",
            step_index=0,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=64,
            grid_cols=64,
            available_actions=["ACTION1", "ACTION2"],
            diff_summary="INITIAL",
            value_histogram={"5": 100, "6": 10},
        )
        belief = bootstrap_belief_ledger(
            store.metadata.episode_id,
            observation,
            motif_names=["threading", "navigation"],
        )
        belief.dynamics_rules.append(
            DynamicsRule(
                rule_id="DR_1",
                action_name="ACTION1",
                effect="move controllable up ~5 cells",
                confidence=0.95,
                times_verified=6,
            )
        )
        belief.interaction_rules.append(
            InteractionRule(
                rule_id="IR_1",
                trigger_pid="P_ctrl_1",
                affected_pid="P_box_2",
                rule_type="push",
                effect="moves target one cell forward",
                confidence=0.72,
                times_observed=4,
            )
        )
        belief.regions.append(
            Region(
                region_id="REG_1",
                name="play_area",
                role="play_area",
                row_min=8,
                row_max=49,
                col_min=6,
                col_max=55,
                dominant_value=5,
                traversable=True,
            )
        )
        belief.reference_patterns.append(
            ReferencePatternSummary(
                surface_id="REF_5",
                kind="reference_box",
                row_min=8,
                row_max=16,
                col_min=32,
                col_max=40,
                pattern_rows=["5555555", "5599955"],
                pattern_description="▓(5)x43, ◆(9)x6",
                confidence=0.91,
            )
        )
        decision = DecisionRecord(
            episode_id=store.metadata.episode_id,
            game_id="sk48",
            step_index=0,
            mode="epistemic",
            chosen_action="ACTION4",
            rationale="Probe trail extension.",
            expected_outcome="Trail extends to the right.",
            belief_diff=BeliefDiffSummary(
                hypotheses_strengthened=1,
                hypotheses_weakened=1,
                hypotheses_discarded=1,
                hypotheses_suggested=1,
                motifs_updated=1,
                anchoring_alerts=1,
                max_confidence_delta=0.15,
                summary="Suggested: hidden-state mechanics",
            ),
        )

        observation_path = store.write_observation(observation)
        belief_path = store.write_belief(belief)
        decision_path = store.write_decision(decision)

        curator = TrajectoryCurator()
        trace = curator.curate(
            observation=observation,
            belief=belief,
            decision=decision,
            prediction="Trail extends by 6 cells.",
            actual_diff="52 cells changed",
            confidence_update={"H1": "0.40->0.25 (active->provisional) | contradicted"},
            belief_diff=decision.belief_diff,
            belief_revision_summary=["H1: 0.40->0.25 (provisional)"],
            suggested_hypotheses=["Consider hidden-state mechanics."],
            motif_updates=["Motif 'threading' confidence reduced."],
            anchoring_alerts=["Hypothesis H1 has been wrong 3/4 times."],
            dynamics_revision="Suggested: Consider hidden-state mechanics.",
            belief_revision_score=0.15,
            belief_revision_reasons=["implicated in surprise (MODERATE, diag_conf=0.75)"],
            hypothesis_pruning_count=1,
            llm_used=True,
            llm_model="gpt-5.4-mini",
            )
        trace_path = store.append_trace(trace)

        assert observation_path.exists()
        assert belief_path.exists()
        assert decision_path.exists()
        assert trace_path.exists()

        with observation_path.open("r", encoding="utf-8") as handle:
            observation_json = json.load(handle)
        assert observation_json["game_id"] == "sk48"
        assert observation_json["grid_rows"] == 64

        with belief_path.open("r", encoding="utf-8") as handle:
            belief_json = json.load(handle)
        assert belief_json["top_motifs"][0]["name"] == "threading"

        trace_lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(trace_lines) == 1
        trace_json = json.loads(trace_lines[0])
        assert trace_json["planning_mode"] == "epistemic"
        assert trace_json["action_taken"] == "ACTION4"
        assert trace_json["confidence_update"]["H1"].startswith("0.40->0.25")
        assert trace_json["belief_diff"]["hypotheses_strengthened"] == 1
        assert trace_json["belief_diff"]["hypotheses_discarded"] == 1
        assert trace_json["belief_diff"]["summary"] == "Suggested: hidden-state mechanics"
        assert trace_json["belief_revision_summary"] == ["H1: 0.40->0.25 (provisional)"]
        assert trace_json["suggested_hypotheses"] == ["Consider hidden-state mechanics."]
        assert trace_json["anchoring_alerts"] == ["Hypothesis H1 has been wrong 3/4 times."]
        assert trace_json["dynamics_rule_summary"] == [
            "ACTION1->move controllable up ~5 cells (c0.95,v6)"
        ]
        assert len(trace_json["interaction_rule_summary"]) == 1
        assert trace_json["interaction_rule_summary"][0].startswith("P_ctrl_1 push P_box_2:")
        assert trace_json["interaction_rule_summary"][0].endswith("(c0.72)")
        assert trace_json["region_summary"] == [
            "play_area[r8-49,c6-55,trv=1,v5]"
        ]
        assert trace_json["reference_pattern_summary"] == "REF_5:reference_box 2x7 5555555/5599955"
        assert trace_json["actual_information_gain"] is None
        assert trace_json["belief_revision_score"] == 0.15
        assert trace_json["hypothesis_pruning_count"] == 1
        assert trace_json["llm_used"] is True
        assert trace_json["llm_model"] == "gpt-5.4-mini"
