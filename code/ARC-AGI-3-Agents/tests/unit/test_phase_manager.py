"""[Mar 30] Created by SD with GPT-5.4."""

import pytest

from agents.agentic import (
    BeliefLedger,
    HypothesisEntry,
    PhaseManager,
    PhaseState,
    exploration_guidance,
)
from agents.agentic.surprise_auditor import SurpriseReport, SurpriseSeverity


def _make_ledger(confidences: list[float], n_actions: int = 0) -> BeliefLedger:
    hypotheses = [
        HypothesisEntry(
            hypothesis_id=f"h{i}",
            summary=f"test hypothesis {i}",
            confidence=confidence,
            status="active",
        )
        for i, confidence in enumerate(confidences)
    ]
    action_semantics = {f"ACTION{i+1}": ["effect"] for i in range(n_actions)}
    return BeliefLedger(
        episode_id="ep0",
        game_id="g0",
        step_index=0,
        hypotheses=hypotheses,
        action_semantics=action_semantics,
    )


def _make_surprise(severity: SurpriseSeverity) -> SurpriseReport:
    return SurpriseReport(severity=severity, summary=f"{severity.name} surprise")


@pytest.mark.unit
class TestPhaseManager:
    def test_epistemic_promotes_to_instrumental_when_confident_enough(self):
        manager = PhaseManager()
        ledger = _make_ledger([0.8, 0.75, 0.9], n_actions=4)
        surprise_history = [
            _make_surprise(SurpriseSeverity.NONE),
            _make_surprise(SurpriseSeverity.MILD),
            _make_surprise(SurpriseSeverity.NONE),
        ]

        phase = manager.evaluate_transition(
            ledger,
            surprise_history,
            step=5,
            budget_remaining=0.7,
            levels_completed=0,
        )

        assert phase == PhaseState.INSTRUMENTAL
        assert len(manager.history) == 1
        assert manager.history[0].from_phase == PhaseState.EPISTEMIC
        assert manager.history[0].to_phase == PhaseState.INSTRUMENTAL

    def test_epistemic_stays_put_with_too_few_actions_tested(self):
        manager = PhaseManager()
        ledger = _make_ledger([0.82, 0.88], n_actions=1)

        phase = manager.evaluate_transition(
            ledger,
            [_make_surprise(SurpriseSeverity.NONE)],
            step=2,
            budget_remaining=0.8,
            levels_completed=0,
        )

        assert phase == PhaseState.EPISTEMIC
        assert manager.history == []

    def test_instrumental_moves_to_recovery_on_plan_failure(self):
        manager = PhaseManager(initial_phase=PhaseState.INSTRUMENTAL)
        ledger = _make_ledger([0.8], n_actions=5)

        phase = manager.evaluate_transition(
            ledger,
            [_make_surprise(SurpriseSeverity.MILD)],
            step=11,
            budget_remaining=0.5,
            levels_completed=0,
            plan_failed=True,
        )

        assert phase == PhaseState.RECOVERY
        assert manager.history[-1].to_phase == PhaseState.RECOVERY

    def test_recovery_returns_to_epistemic_after_reobservation(self):
        manager = PhaseManager(initial_phase=PhaseState.RECOVERY)
        ledger = _make_ledger([0.3], n_actions=5)

        phase = manager.evaluate_transition(
            ledger,
            [_make_surprise(SurpriseSeverity.NONE)],
            step=12,
            budget_remaining=0.5,
            levels_completed=0,
            recovery_observation_done=True,
            old_hypothesis_demoted=True,
        )

        assert phase == PhaseState.EPISTEMIC
        assert manager.history[-1].to_phase == PhaseState.EPISTEMIC

    def test_low_budget_override_forces_instrumental(self):
        manager = PhaseManager()
        ledger = _make_ledger([0.6], n_actions=1)

        phase = manager.evaluate_transition(
            ledger,
            [_make_surprise(SurpriseSeverity.NONE)],
            step=20,
            budget_remaining=0.25,
            levels_completed=0,
        )

        assert phase == PhaseState.INSTRUMENTAL
        assert "Low budget" in manager.history[-1].reason

    def test_exploration_guidance_changes_by_phase_and_budget(self):
        assert "RECOVERY" in exploration_guidance(PhaseState.RECOVERY, 0.5)
        assert "GENEROUS" in exploration_guidance(PhaseState.EPISTEMIC, 0.8)
        assert "BALANCED" in exploration_guidance(PhaseState.INSTRUMENTAL, 0.4)
        assert "LOW" in exploration_guidance(PhaseState.INSTRUMENTAL, 0.2)
        assert "EMERGENCY" in exploration_guidance(PhaseState.INSTRUMENTAL, 0.1)
