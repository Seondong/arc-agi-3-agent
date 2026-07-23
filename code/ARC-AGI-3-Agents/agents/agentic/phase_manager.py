# [Mar 30] Phase Manager for ARC-AGI-3 agentic framework.
# Created by SD with Claude Opus 4.6.

"""Phase Manager: decide whether the agent should explore (epistemic),
solve (instrumental), or recover from failures (recovery).

The agent alternates between three phases:

  EPISTEMIC    -- probing, exploring, building mental model of the game.
  INSTRUMENTAL -- executing a plan derived from high-confidence hypotheses.
  RECOVERY     -- diagnosing what went wrong after an unexpected failure.

Transition rules, budget-aware urgency, and Skeptic budget control are all
handled here.  The Phase Manager is consulted each step to determine the
current operating mode before the agent selects an action.

References:
  - docs/agentic-framework/05-planning-and-execution.md
  - docs/agentic-framework/02-role-topology.md  (Skeptic role)
  - Claude's 08 document  (Skeptic budget per phase)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .schemas import BeliefLedger, HypothesisEntry
from .surprise_auditor import SurpriseReport, SurpriseSeverity


# ===================================================================
# Enums
# ===================================================================

class PhaseState(Enum):
    """Operating phase of the agent."""
    EPISTEMIC = auto()      # exploring, building mental model
    INSTRUMENTAL = auto()   # executing a plan
    RECOVERY = auto()       # diagnosing failure


# ===================================================================
# Data classes
# ===================================================================

@dataclass
class TransitionRecord:
    """Logs a single phase transition for auditability."""
    step: int
    from_phase: PhaseState
    to_phase: PhaseState
    reason: str


@dataclass
class PhaseContext:
    """Snapshot of inputs used to evaluate a transition."""
    avg_confidence: float
    max_confidence: float
    active_hypothesis_count: int
    actions_tested: int
    budget_remaining: float          # 0.0 .. 1.0
    levels_completed: int
    recent_severe_count: int         # SEVERE surprises in last N steps
    latest_surprise_severity: SurpriseSeverity | None
    has_plan_failure: bool           # expected level change didn't happen
    recovery_observation_done: bool  # re-observed state after failure
    old_hypothesis_demoted: bool     # bad hypothesis confidence lowered


@dataclass
class SkepticBudget:
    """Number of Skeptic attacks allowed this round."""
    attacks: int
    reason: str


# ===================================================================
# Phase Manager
# ===================================================================

class PhaseManager:
    """Decides the operating phase and manages transitions.

    Usage::

        pm = PhaseManager()
        phase = pm.evaluate_transition(
            belief_ledger=ledger,
            surprise_history=surprises,
            step=10,
            budget_remaining=0.55,
            levels_completed=1,
        )
    """

    # -- tunables ---------------------------------------------------
    CONFIDENCE_PROMOTE_THRESHOLD = 0.7   # avg to go EPISTEMIC -> INSTRUMENTAL
    CONFIDENCE_DEMOTE_THRESHOLD = 0.5    # avg to fall back INSTRUMENTAL -> EPISTEMIC
    MIN_ACTIONS_BEFORE_INSTRUMENTAL = 3  # minimum probes before solving
    SEVERE_LOOKBACK = 3                  # how many recent steps to check for SEVERE

    # Budget thresholds
    BUDGET_GENEROUS = 0.60
    BUDGET_BALANCED = 0.30
    BUDGET_LOW = 0.15

    # Skeptic attacks per phase
    SKEPTIC_ATTACKS = {
        PhaseState.EPISTEMIC: 2,
        PhaseState.INSTRUMENTAL: 1,
        PhaseState.RECOVERY: 3,
    }

    def __init__(self, initial_phase: PhaseState = PhaseState.EPISTEMIC) -> None:
        self.current_phase: PhaseState = initial_phase
        self.history: list[TransitionRecord] = []
        self._forced_phase: PhaseState | None = None

    # ---------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------

    def evaluate_transition(
        self,
        belief_ledger: BeliefLedger,
        surprise_history: list[SurpriseReport],
        step: int,
        budget_remaining: float,
        levels_completed: int,
        *,
        plan_failed: bool = False,
        recovery_observation_done: bool = False,
        old_hypothesis_demoted: bool = False,
    ) -> PhaseState:
        """Evaluate whether a phase transition should occur.

        Parameters
        ----------
        belief_ledger : current belief state.
        surprise_history : all SurpriseReports so far (most recent last).
        step : current step index.
        budget_remaining : fraction of total budget remaining (0.0 to 1.0).
        levels_completed : number of levels solved so far.
        plan_failed : True if the last instrumental action didn't achieve
                      its expected outcome (e.g. level didn't change).
        recovery_observation_done : True if we've re-observed state in RECOVERY.
        old_hypothesis_demoted : True if the failing hypothesis was demoted.

        Returns
        -------
        The new PhaseState (may be unchanged).
        """
        ctx = self._build_context(
            belief_ledger,
            surprise_history,
            step,
            budget_remaining,
            levels_completed,
            plan_failed,
            recovery_observation_done,
            old_hypothesis_demoted,
        )

        # Budget overrides first -- they can force a phase regardless of
        # normal transition logic.
        budget_override = self._check_budget_override(ctx)
        if budget_override is not None:
            return self._transition(budget_override[0], step, budget_override[1])

        # Normal transition logic based on current phase.
        if self.current_phase == PhaseState.EPISTEMIC:
            return self._from_epistemic(ctx, step)
        elif self.current_phase == PhaseState.INSTRUMENTAL:
            return self._from_instrumental(ctx, step)
        elif self.current_phase == PhaseState.RECOVERY:
            return self._from_recovery(ctx, step)

        return self.current_phase  # fallback (shouldn't happen)

    def get_skeptic_budget(self) -> SkepticBudget:
        """Return the Skeptic attack budget for the current phase."""
        attacks = self.SKEPTIC_ATTACKS[self.current_phase]
        reasons = {
            PhaseState.EPISTEMIC: "Exploring -- Skeptic gets 2 attacks to stress-test hypotheses.",
            PhaseState.INSTRUMENTAL: "Executing -- Skeptic gets 1 attack to sanity-check the plan.",
            PhaseState.RECOVERY: "Recovering -- Skeptic gets 3 attacks to find what went wrong.",
        }
        return SkepticBudget(attacks=attacks, reason=reasons[self.current_phase])

    def force_phase(self, phase: PhaseState, step: int, reason: str) -> PhaseState:
        """Force a phase transition (e.g. from external orchestrator)."""
        return self._transition(phase, step, f"FORCED: {reason}")

    # ---------------------------------------------------------------
    # Context builder
    # ---------------------------------------------------------------

    def _build_context(
        self,
        ledger: BeliefLedger,
        surprise_history: list[SurpriseReport],
        step: int,
        budget_remaining: float,
        levels_completed: int,
        plan_failed: bool,
        recovery_observation_done: bool,
        old_hypothesis_demoted: bool,
    ) -> PhaseContext:
        active = [h for h in ledger.hypotheses
                  if h.status in ("active", "provisional")]

        confidences = [h.confidence for h in active] if active else [0.0]
        avg_conf = sum(confidences) / len(confidences)
        max_conf = max(confidences) if confidences else 0.0

        # Count actions tested from action_semantics keys
        actions_tested = len(ledger.action_semantics)

        # Count SEVERE surprises in last SEVERE_LOOKBACK steps
        recent = surprise_history[-self.SEVERE_LOOKBACK:]
        recent_severe = sum(
            1 for sr in recent if sr.severity == SurpriseSeverity.SEVERE
        )

        latest_severity = (
            surprise_history[-1].severity if surprise_history else None
        )

        return PhaseContext(
            avg_confidence=avg_conf,
            max_confidence=max_conf,
            active_hypothesis_count=len(active),
            actions_tested=actions_tested,
            budget_remaining=budget_remaining,
            levels_completed=levels_completed,
            recent_severe_count=recent_severe,
            latest_surprise_severity=latest_severity,
            has_plan_failure=plan_failed,
            recovery_observation_done=recovery_observation_done,
            old_hypothesis_demoted=old_hypothesis_demoted,
        )

    # ---------------------------------------------------------------
    # Budget overrides
    # ---------------------------------------------------------------

    def _check_budget_override(
        self, ctx: PhaseContext
    ) -> tuple[PhaseState, str] | None:
        """Return a forced (phase, reason) if budget demands it, else None."""

        # Emergency: < 15% budget -- execute best guess immediately.
        if ctx.budget_remaining < self.BUDGET_LOW:
            if self.current_phase != PhaseState.INSTRUMENTAL:
                return (
                    PhaseState.INSTRUMENTAL,
                    f"EMERGENCY budget ({ctx.budget_remaining:.0%}) -- "
                    f"executing best-guess (max conf {ctx.max_confidence:.2f}).",
                )
            return None

        # Low budget: < 30% -- force instrumental if any hypothesis > 0.5.
        if ctx.budget_remaining < self.BUDGET_BALANCED:
            if (
                self.current_phase == PhaseState.EPISTEMIC
                and ctx.max_confidence > 0.5
            ):
                return (
                    PhaseState.INSTRUMENTAL,
                    f"Low budget ({ctx.budget_remaining:.0%}) -- "
                    f"forcing instrumental (max conf {ctx.max_confidence:.2f}).",
                )
            return None

        return None

    # ---------------------------------------------------------------
    # Transition logic per source phase
    # ---------------------------------------------------------------

    def _from_epistemic(self, ctx: PhaseContext, step: int) -> PhaseState:
        """EPISTEMIC -> INSTRUMENTAL when confident enough."""

        # Check for SEVERE surprise -- go to recovery
        if ctx.latest_surprise_severity == SurpriseSeverity.SEVERE:
            return self._transition(
                PhaseState.RECOVERY, step,
                "SEVERE surprise during epistemic exploration.",
            )

        # Promote to INSTRUMENTAL when:
        #   - avg confidence > threshold
        #   - enough actions tested
        #   - no SEVERE surprises recently
        if (
            ctx.avg_confidence > self.CONFIDENCE_PROMOTE_THRESHOLD
            and ctx.actions_tested >= self.MIN_ACTIONS_BEFORE_INSTRUMENTAL
            and ctx.recent_severe_count == 0
        ):
            return self._transition(
                PhaseState.INSTRUMENTAL, step,
                f"Confidence {ctx.avg_confidence:.2f} > {self.CONFIDENCE_PROMOTE_THRESHOLD}, "
                f"{ctx.actions_tested} actions tested, no recent SEVERE surprises.",
            )

        return self.current_phase  # stay epistemic

    def _from_instrumental(self, ctx: PhaseContext, step: int) -> PhaseState:
        """INSTRUMENTAL -> RECOVERY on failure, -> EPISTEMIC on lost confidence."""

        # SEVERE surprise -> RECOVERY
        if ctx.latest_surprise_severity == SurpriseSeverity.SEVERE:
            return self._transition(
                PhaseState.RECOVERY, step,
                "SEVERE surprise during plan execution.",
            )

        # Plan failure -> RECOVERY
        if ctx.has_plan_failure:
            return self._transition(
                PhaseState.RECOVERY, step,
                "Plan failed -- expected outcome did not occur.",
            )

        # Energy critically low -> RECOVERY
        if ctx.budget_remaining < self.BUDGET_LOW:
            return self._transition(
                PhaseState.RECOVERY, step,
                f"Energy critically low ({ctx.budget_remaining:.0%}).",
            )

        # Confidence dropped -> back to EPISTEMIC
        if ctx.avg_confidence < self.CONFIDENCE_DEMOTE_THRESHOLD:
            return self._transition(
                PhaseState.EPISTEMIC, step,
                f"Confidence dropped to {ctx.avg_confidence:.2f} "
                f"< {self.CONFIDENCE_DEMOTE_THRESHOLD} -- new evidence contradicts model.",
            )

        return self.current_phase  # stay instrumental

    def _from_recovery(self, ctx: PhaseContext, step: int) -> PhaseState:
        """RECOVERY -> EPISTEMIC when recovery steps are done."""

        if ctx.recovery_observation_done and ctx.old_hypothesis_demoted:
            return self._transition(
                PhaseState.EPISTEMIC, step,
                "Recovery complete: re-observed state and demoted failing hypothesis.",
            )

        return self.current_phase  # stay in recovery

    # ---------------------------------------------------------------
    # Transition helper
    # ---------------------------------------------------------------

    def _transition(
        self, to: PhaseState, step: int, reason: str
    ) -> PhaseState:
        if to == self.current_phase:
            return self.current_phase
        record = TransitionRecord(
            step=step,
            from_phase=self.current_phase,
            to_phase=to,
            reason=reason,
        )
        self.history.append(record)
        self.current_phase = to
        return to

    # ---------------------------------------------------------------
    # Inspection helpers
    # ---------------------------------------------------------------

    def summary(self) -> str:
        """Human-readable summary of phase history."""
        lines = [f"Current phase: {self.current_phase.name}"]
        for rec in self.history:
            lines.append(
                f"  step {rec.step}: {rec.from_phase.name} -> "
                f"{rec.to_phase.name} -- {rec.reason}"
            )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"PhaseManager(phase={self.current_phase.name}, "
            f"transitions={len(self.history)})"
        )


# ===================================================================
# Convenience: phase-aware exploration vs exploitation guidance
# ===================================================================

def exploration_guidance(
    phase: PhaseState, budget_remaining: float
) -> str:
    """Return a short directive the action selector can prepend to its prompt.

    This encodes the budget-aware explore/exploit balance described in
    the planning document.
    """
    if phase == PhaseState.RECOVERY:
        return (
            "RECOVERY: re-observe the current state carefully.  "
            "Identify what assumption was wrong.  Do NOT attempt to solve yet."
        )

    if budget_remaining > PhaseManager.BUDGET_GENEROUS:
        return (
            "GENEROUS BUDGET: prioritize information-rich exploratory actions.  "
            "Try untested actions and gather diverse observations."
        )
    if budget_remaining > PhaseManager.BUDGET_BALANCED:
        return (
            "BALANCED BUDGET: mix exploration with exploitation.  "
            "Test remaining uncertainties but start applying best hypotheses."
        )
    if budget_remaining > PhaseManager.BUDGET_LOW:
        return (
            "LOW BUDGET: strongly favor exploitation.  "
            "Execute the highest-confidence plan.  Only explore if stuck."
        )
    return (
        "EMERGENCY: execute the best-guess plan immediately.  "
        "No exploration -- commit to the top hypothesis."
    )


# ===================================================================
# Self-tests
# ===================================================================

if __name__ == "__main__":
    from .schemas import BeliefLedger, HypothesisEntry

    def _make_ledger(
        confidences: list[float],
        n_actions: int = 0,
    ) -> BeliefLedger:
        hyps = [
            HypothesisEntry(
                hypothesis_id=f"h{i}",
                summary=f"test hypothesis {i}",
                confidence=c,
                status="active",
            )
            for i, c in enumerate(confidences)
        ]
        action_sem = {f"action_{j}": ["effect"] for j in range(n_actions)}
        return BeliefLedger(
            episode_id="ep0",
            game_id="g0",
            step_index=0,
            hypotheses=hyps,
            action_semantics=action_sem,
        )

    def _make_surprise(severity: SurpriseSeverity) -> SurpriseReport:
        return SurpriseReport(severity=severity, summary=f"{severity.name} surprise")

    # ------- Test 1: EPISTEMIC -> INSTRUMENTAL on high confidence -------
    pm = PhaseManager()
    ledger = _make_ledger([0.8, 0.75, 0.9], n_actions=4)
    surprises: list[SurpriseReport] = [
        _make_surprise(SurpriseSeverity.NONE),
        _make_surprise(SurpriseSeverity.MILD),
        _make_surprise(SurpriseSeverity.NONE),
    ]
    phase = pm.evaluate_transition(ledger, surprises, step=5, budget_remaining=0.7, levels_completed=0)
    assert phase == PhaseState.INSTRUMENTAL, f"Expected INSTRUMENTAL, got {phase}"
    print("PASS: EPISTEMIC -> INSTRUMENTAL on high confidence")

    # ------- Test 2: Stay EPISTEMIC when too few actions -------
    pm2 = PhaseManager()
    ledger2 = _make_ledger([0.8, 0.9], n_actions=1)
    phase2 = pm2.evaluate_transition(ledger2, surprises, step=2, budget_remaining=0.8, levels_completed=0)
    assert phase2 == PhaseState.EPISTEMIC, f"Expected EPISTEMIC, got {phase2}"
    print("PASS: Stay EPISTEMIC with too few actions tested")

    # ------- Test 3: INSTRUMENTAL -> RECOVERY on SEVERE surprise -------
    pm3 = PhaseManager(initial_phase=PhaseState.INSTRUMENTAL)
    ledger3 = _make_ledger([0.8], n_actions=5)
    severe_hist = [_make_surprise(SurpriseSeverity.SEVERE)]
    phase3 = pm3.evaluate_transition(ledger3, severe_hist, step=10, budget_remaining=0.5, levels_completed=0)
    assert phase3 == PhaseState.RECOVERY, f"Expected RECOVERY, got {phase3}"
    print("PASS: INSTRUMENTAL -> RECOVERY on SEVERE surprise")

    # ------- Test 4: INSTRUMENTAL -> RECOVERY on plan failure -------
    pm4 = PhaseManager(initial_phase=PhaseState.INSTRUMENTAL)
    ledger4 = _make_ledger([0.8], n_actions=5)
    mild_hist = [_make_surprise(SurpriseSeverity.MILD)]
    phase4 = pm4.evaluate_transition(
        ledger4, mild_hist, step=11, budget_remaining=0.5,
        levels_completed=0, plan_failed=True,
    )
    assert phase4 == PhaseState.RECOVERY, f"Expected RECOVERY, got {phase4}"
    print("PASS: INSTRUMENTAL -> RECOVERY on plan failure")

    # ------- Test 5: RECOVERY -> EPISTEMIC after recovery steps -------
    pm5 = PhaseManager(initial_phase=PhaseState.RECOVERY)
    ledger5 = _make_ledger([0.3], n_actions=5)
    no_surprise = [_make_surprise(SurpriseSeverity.NONE)]
    phase5 = pm5.evaluate_transition(
        ledger5, no_surprise, step=12, budget_remaining=0.5,
        levels_completed=0,
        recovery_observation_done=True,
        old_hypothesis_demoted=True,
    )
    assert phase5 == PhaseState.EPISTEMIC, f"Expected EPISTEMIC, got {phase5}"
    print("PASS: RECOVERY -> EPISTEMIC after recovery steps")

    # ------- Test 6: INSTRUMENTAL -> EPISTEMIC on confidence drop -------
    pm6 = PhaseManager(initial_phase=PhaseState.INSTRUMENTAL)
    ledger6 = _make_ledger([0.3, 0.4], n_actions=5)
    phase6 = pm6.evaluate_transition(
        ledger6, no_surprise, step=13, budget_remaining=0.6,
        levels_completed=0,
    )
    assert phase6 == PhaseState.EPISTEMIC, f"Expected EPISTEMIC, got {phase6}"
    print("PASS: INSTRUMENTAL -> EPISTEMIC on confidence drop")

    # ------- Test 7: Budget override -- low budget forces INSTRUMENTAL -------
    pm7 = PhaseManager()
    ledger7 = _make_ledger([0.6], n_actions=1)
    phase7 = pm7.evaluate_transition(
        ledger7, no_surprise, step=20, budget_remaining=0.25,
        levels_completed=0,
    )
    assert phase7 == PhaseState.INSTRUMENTAL, f"Expected INSTRUMENTAL, got {phase7}"
    print("PASS: Low budget forces INSTRUMENTAL")

    # ------- Test 8: Budget override -- emergency forces INSTRUMENTAL -------
    pm8 = PhaseManager(initial_phase=PhaseState.RECOVERY)
    ledger8 = _make_ledger([0.2], n_actions=1)
    phase8 = pm8.evaluate_transition(
        ledger8, no_surprise, step=25, budget_remaining=0.10,
        levels_completed=0,
    )
    assert phase8 == PhaseState.INSTRUMENTAL, f"Expected INSTRUMENTAL, got {phase8}"
    print("PASS: Emergency budget forces INSTRUMENTAL")

    # ------- Test 9: Skeptic budget per phase -------
    for phase_val, expected_attacks in [
        (PhaseState.EPISTEMIC, 2),
        (PhaseState.INSTRUMENTAL, 1),
        (PhaseState.RECOVERY, 3),
    ]:
        pm_s = PhaseManager(initial_phase=phase_val)
        sb = pm_s.get_skeptic_budget()
        assert sb.attacks == expected_attacks, (
            f"Expected {expected_attacks} attacks for {phase_val.name}, got {sb.attacks}"
        )
    print("PASS: Skeptic budget correct for all phases")

    # ------- Test 10: Stay EPISTEMIC when SEVERE in recent window -------
    pm10 = PhaseManager()
    ledger10 = _make_ledger([0.8, 0.9], n_actions=4)
    mixed_hist = [
        _make_surprise(SurpriseSeverity.NONE),
        _make_surprise(SurpriseSeverity.SEVERE),  # recent SEVERE
        _make_surprise(SurpriseSeverity.NONE),
    ]
    phase10 = pm10.evaluate_transition(
        ledger10, mixed_hist, step=6, budget_remaining=0.8,
        levels_completed=0,
    )
    # Should stay EPISTEMIC because of recent SEVERE even though confidence is high
    assert phase10 == PhaseState.EPISTEMIC, f"Expected EPISTEMIC, got {phase10}"
    print("PASS: Stay EPISTEMIC with recent SEVERE surprise")

    # ------- Test 11: Transition history and summary -------
    assert len(pm.history) == 1, f"Expected 1 transition, got {len(pm.history)}"
    assert pm.history[0].from_phase == PhaseState.EPISTEMIC
    assert pm.history[0].to_phase == PhaseState.INSTRUMENTAL
    print("PASS: Transition history recorded correctly")

    # ------- Test 12: exploration_guidance -------
    g1 = exploration_guidance(PhaseState.RECOVERY, 0.5)
    assert "RECOVERY" in g1
    g2 = exploration_guidance(PhaseState.EPISTEMIC, 0.8)
    assert "GENEROUS" in g2
    g3 = exploration_guidance(PhaseState.INSTRUMENTAL, 0.4)
    assert "BALANCED" in g3
    g4 = exploration_guidance(PhaseState.INSTRUMENTAL, 0.2)
    assert "LOW" in g4
    g5 = exploration_guidance(PhaseState.INSTRUMENTAL, 0.10)
    assert "EMERGENCY" in g5
    print("PASS: exploration_guidance returns correct directives")

    print(f"\n{pm.summary()}")
    print("\nAll 12 tests passed.")
