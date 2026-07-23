"""[Mar 31] Created by SD with GPT-5.4."""

import json

import pytest

from agents.agentic.memory import EpisodeMemoryStore, TrajectoryCurator, bootstrap_belief_ledger
from agents.agentic.schemas import ObservationSnapshot
from agents.agentic.solve_loop import WorldModel, solve_step
from agents.agentic.phase_manager import PhaseState
from agents.agentic.surprise_auditor import RevisionResult, SurpriseReport, SurpriseSeverity


class _StubPhaseManager:
    def evaluate_transition(self, **kwargs):
        return PhaseState.INSTRUMENTAL


class _StubExperimentDesigner:
    def suggest_probe(self, **kwargs):
        raise AssertionError("ExperimentDesigner should not be used in instrumental test")


class _StubAntiAnchoringGuard:
    pass


class _StubLLMBrain:
    model = "gpt-5.4-mini"

    def decide(self, **kwargs):
        class _Decision:
            action = "ACTION1"
            action_data = None
            rationale = "LLM selected ACTION1."
            expected_outcome = "Object should move."
            goal_hypothesis = ""
            dynamics_update = ""
            motifs = {}
            hypotheses = []
            object_labels = {}
            surprise_interpretation = ""
            phase_reasoning = ""
            reference_interpretation = ""

        return _Decision()


@pytest.mark.unit
def test_solve_step_exports_current_phase_mode_to_belief_and_trace(tmp_path, monkeypatch):
    def fake_run_perception(**kwargs):
        return {
            "objects": [],
            "transitions": [],
            "object_summaries": [],
            "affordances": {},
        }

    def fake_build_observation(**kwargs):
        return ObservationSnapshot(
            game_id="ar25-e3c63847",
            step_index=6,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=1,
            grid_cols=1,
            available_actions=["ACTION1"],
            diff_summary="0 cells changed",
            objects=[],
        )

    def fake_audit_step(**kwargs):
        return {
            "report": SurpriseReport(
                severity=SurpriseSeverity.NONE,
                summary="all predictions matched",
            ),
            "revision": RevisionResult(),
            "alerts": [],
        }

    monkeypatch.setattr("agents.agentic.solve_loop.run_perception", fake_run_perception)
    monkeypatch.setattr("agents.agentic.solve_loop._build_observation", fake_build_observation)
    monkeypatch.setattr("agents.agentic.solve_loop.audit_step", fake_audit_step)

    store = EpisodeMemoryStore.create(
        tmp_path,
        game_id="ar25-e3c63847",
        episode_id="ar25-regression-mode",
    )
    curator = TrajectoryCurator()
    bootstrap_obs = ObservationSnapshot(
        game_id="ar25-e3c63847",
        step_index=0,
        state="NOT_FINISHED",
        levels_completed=0,
        grid_rows=1,
        grid_cols=1,
        available_actions=["ACTION1"],
        diff_summary="INITIAL",
        objects=[],
    )
    belief = bootstrap_belief_ledger(
        store.metadata.episode_id,
        bootstrap_obs,
        motif_names=["navigation"],
        mode="epistemic",
    )

    result, _, _, _ = solve_step(
        grid=[[0]],
        prev_grid=[[0]],
        prev_objects=[],
        game_id="ar25-e3c63847",
        step_index=6,
        state_name="NOT_FINISHED",
        levels_completed=0,
        available_action_names=["ACTION1"],
        action_history=[],
        belief_state=belief,
        phase_manager=_StubPhaseManager(),
        experiment_designer=_StubExperimentDesigner(),
        world_model=WorldModel(),
        surprise_history=[],
        anti_anchoring=_StubAntiAnchoringGuard(),
        max_steps=20,
        memory=store,
        curator=curator,
    )

    belief_json = json.loads(store.step_path(6, "belief").read_text(encoding="utf-8"))
    decision_json = json.loads(store.step_path(6, "decision").read_text(encoding="utf-8"))
    trace_json = json.loads(store.trace_path.read_text(encoding="utf-8").strip())

    assert result.phase == PhaseState.INSTRUMENTAL
    assert result.belief_state.mode == "instrumental"
    assert belief_json["mode"] == "instrumental"
    assert decision_json["mode"] == "instrumental"
    assert trace_json["planning_mode"] == "instrumental"


@pytest.mark.unit
def test_solve_step_exports_llm_usage_to_trace(tmp_path, monkeypatch):
    def fake_run_perception(**kwargs):
        return {
            "objects": [],
            "transitions": [],
            "object_summaries": [],
            "affordances": {},
        }

    def fake_build_observation(**kwargs):
        return ObservationSnapshot(
            game_id="ar25-e3c63847",
            step_index=3,
            state="NOT_FINISHED",
            levels_completed=0,
            grid_rows=1,
            grid_cols=1,
            available_actions=["ACTION1", "ACTION6"],
            diff_summary="0 cells changed",
            objects=[],
        )

    def fake_audit_step(**kwargs):
        return {
            "report": SurpriseReport(
                severity=SurpriseSeverity.NONE,
                summary="all predictions matched",
            ),
            "revision": RevisionResult(),
            "alerts": [],
        }

    monkeypatch.setattr("agents.agentic.solve_loop.run_perception", fake_run_perception)
    monkeypatch.setattr("agents.agentic.solve_loop._build_observation", fake_build_observation)
    monkeypatch.setattr("agents.agentic.solve_loop.audit_step", fake_audit_step)

    store = EpisodeMemoryStore.create(
        tmp_path,
        game_id="ar25-e3c63847",
        episode_id="ar25-regression-llm",
    )
    curator = TrajectoryCurator()
    bootstrap_obs = ObservationSnapshot(
        game_id="ar25-e3c63847",
        step_index=0,
        state="NOT_FINISHED",
        levels_completed=0,
        grid_rows=1,
        grid_cols=1,
        available_actions=["ACTION1", "ACTION6"],
        diff_summary="INITIAL",
        objects=[],
    )
    belief = bootstrap_belief_ledger(
        store.metadata.episode_id,
        bootstrap_obs,
        motif_names=["navigation"],
        mode="epistemic",
    )

    result, _, _, _ = solve_step(
        grid=[[0]],
        prev_grid=[[0]],
        prev_objects=[],
        game_id="ar25-e3c63847",
        step_index=3,
        state_name="NOT_FINISHED",
        levels_completed=0,
        available_action_names=["ACTION1", "ACTION6"],
        action_history=[],
        belief_state=belief,
        phase_manager=_StubPhaseManager(),
        experiment_designer=_StubExperimentDesigner(),
        world_model=WorldModel(),
        surprise_history=[],
        anti_anchoring=_StubAntiAnchoringGuard(),
        max_steps=20,
        memory=store,
        curator=curator,
        llm_brain=_StubLLMBrain(),
    )

    trace_json = json.loads(store.trace_path.read_text(encoding="utf-8").strip())

    assert result.llm_used is True
    assert result.llm_model == "gpt-5.4-mini"
    assert trace_json["llm_used"] is True
    assert trace_json["llm_model"] == "gpt-5.4-mini"
