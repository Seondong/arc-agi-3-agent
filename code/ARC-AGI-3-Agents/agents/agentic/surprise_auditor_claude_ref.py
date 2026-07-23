# [Mar 30] Surprise Auditor for ARC-AGI-3 agentic framework.
# Created by SD with Claude Opus 4.6.

"""Surprise Auditor: detect prediction errors, decompose their causes,
revise beliefs, and guard against anchoring bias.

Four components:
  1. SurpriseDetector   -- compare predicted vs actual changes, emit SurpriseReport.
  2. ErrorDecomposer    -- classify WHY a prediction was wrong.
  3. BeliefReviser      -- update belief ledger confidences and suggest new hypotheses.
  4. AntiAnchoringGuard -- prevent over-commitment to repeatedly wrong hypotheses.

Designed to sit between the experiment designer (which makes predictions) and
the belief ledger (which tracks hypotheses).  After each action, the agent
calls ``audit_step`` to close the predict-observe-update loop.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .perception import ObjectTransition, TransitionKind
from .schemas import BeliefLedger, HypothesisEntry, MotifBelief


# ===================================================================
# Enums
# ===================================================================

class SurpriseSeverity(Enum):
    NONE = auto()
    MILD = auto()
    MODERATE = auto()
    SEVERE = auto()


class ErrorCategory(Enum):
    OBJECT_IDENTITY_ERROR = auto()       # wrong object was affected
    ACTION_SEMANTICS_ERROR = auto()      # action did something different than expected
    HIDDEN_STATE_ERROR = auto()          # something changed that wasn't tracked
    GOAL_INTERPRETATION_ERROR = auto()   # win condition assumption was wrong
    INTERACTION_ERROR = auto()           # unknown object interaction occurred
    COLLISION_ERROR = auto()             # movement was blocked unexpectedly


# ===================================================================
# Data classes
# ===================================================================

@dataclass
class PredictedChange:
    """A single predicted change from the world model / experiment designer."""
    obj_id: str | None = None
    kind: TransitionKind | None = None
    description: str = ""


@dataclass
class SurpriseReport:
    """Output of SurpriseDetector: what was unexpected."""
    severity: SurpriseSeverity
    unexpected_changes: list[ObjectTransition] = field(default_factory=list)
    missing_changes: list[PredictedChange] = field(default_factory=list)
    matched_changes: list[ObjectTransition] = field(default_factory=list)
    summary: str = ""

    @property
    def is_surprising(self) -> bool:
        return self.severity != SurpriseSeverity.NONE


@dataclass
class ErrorDiagnosis:
    """Output of ErrorDecomposer: why the prediction was wrong."""
    category: ErrorCategory
    confidence: float  # 0..1 how sure we are about this diagnosis
    detail: str = ""
    implicated_hypothesis_ids: list[str] = field(default_factory=list)


@dataclass
class RevisionAction:
    """A single belief-revision action to apply to the ledger."""
    hypothesis_id: str
    old_confidence: float
    new_confidence: float
    old_status: str
    new_status: str
    reason: str


@dataclass
class RevisionResult:
    """Output of BeliefReviser: all revisions applied."""
    actions: list[RevisionAction] = field(default_factory=list)
    suggested_hypotheses: list[str] = field(default_factory=list)
    motif_updates: list[str] = field(default_factory=list)


@dataclass
class AnchoringAlert:
    """Output of AntiAnchoringGuard: alerts about over-committed hypotheses."""
    hypothesis_id: str
    alert_type: str  # "repeated_failure", "stale_confidence", "high_surprise_rate"
    detail: str


# ===================================================================
# 1. SurpriseDetector
# ===================================================================

class SurpriseDetector:
    """Compare predicted changes with actual changes from the ObjectTracker.

    Scoring logic:
      - Each unexpected change adds severity points.
      - Each missing (predicted but not observed) change adds severity points.
      - APPEARED/DISAPPEARED transitions weigh more than MOVED.
      - Severity thresholds: 0 = NONE, 1-2 = MILD, 3-4 = MODERATE, 5+ = SEVERE.
    """

    SEVERITY_THRESHOLDS = {0: SurpriseSeverity.NONE,
                           1: SurpriseSeverity.MILD,
                           3: SurpriseSeverity.MODERATE,
                           5: SurpriseSeverity.SEVERE}

    # Weight per transition kind for severity scoring
    KIND_WEIGHT: dict[TransitionKind, int] = {
        TransitionKind.APPEARED: 2,
        TransitionKind.DISAPPEARED: 2,
        TransitionKind.TRANSFORMED: 2,
        TransitionKind.MOVED: 1,
    }

    def _severity_from_score(self, score: int) -> SurpriseSeverity:
        if score >= 5:
            return SurpriseSeverity.SEVERE
        if score >= 3:
            return SurpriseSeverity.MODERATE
        if score >= 1:
            return SurpriseSeverity.MILD
        return SurpriseSeverity.NONE

    def detect(
        self,
        predicted_changes: list[PredictedChange],
        actual_changes: list[ObjectTransition],
    ) -> SurpriseReport:
        """Compare predictions against reality.

        Parameters
        ----------
        predicted_changes : what the world model expected to happen.
        actual_changes    : ObjectTransitions from ObjectTracker.

        Returns
        -------
        SurpriseReport with severity, unexpected/missing/matched lists.
        """
        # Build lookup of predicted object ids and kinds
        predicted_set: dict[str | None, PredictedChange] = {}
        for pc in predicted_changes:
            key = pc.obj_id
            predicted_set[key] = pc

        matched: list[ObjectTransition] = []
        unexpected: list[ObjectTransition] = []

        # Check each actual change against predictions
        for actual in actual_changes:
            pc = predicted_set.pop(actual.obj_id, None)
            if pc is not None:
                # Predicted object was affected -- check if kind matches
                if pc.kind is None or pc.kind == actual.kind:
                    matched.append(actual)
                else:
                    # Right object, wrong kind of change
                    unexpected.append(actual)
            else:
                # This change was not predicted at all
                unexpected.append(actual)

        # Remaining predictions that were not observed
        missing = list(predicted_set.values())

        # Compute severity score
        score = 0
        for u in unexpected:
            score += self.KIND_WEIGHT.get(u.kind, 1)
        for m in missing:
            score += self.KIND_WEIGHT.get(m.kind, 1) if m.kind else 1

        severity = self._severity_from_score(score)

        parts = []
        if unexpected:
            parts.append(f"{len(unexpected)} unexpected change(s)")
        if missing:
            parts.append(f"{len(missing)} missing predicted change(s)")
        if not parts:
            parts.append("all predictions matched")
        summary = "; ".join(parts)

        return SurpriseReport(
            severity=severity,
            unexpected_changes=unexpected,
            missing_changes=missing,
            matched_changes=matched,
            summary=summary,
        )


# ===================================================================
# 2. ErrorDecomposer
# ===================================================================

class ErrorDecomposer:
    """Classify WHY a prediction was wrong, mapping surprise to error categories.

    Heuristic rules (applied in priority order):
      - DISAPPEARED object that was predicted to MOVE -> COLLISION_ERROR
      - Unexpected APPEARED object -> HIDDEN_STATE_ERROR
      - Predicted object not affected but a *different* object of same value was
        -> OBJECT_IDENTITY_ERROR
      - Action produced a transition kind different from predicted
        -> ACTION_SEMANTICS_ERROR
      - Two objects interacted unexpectedly (both changed, overlapping bbox)
        -> INTERACTION_ERROR
      - Goal surface changed unexpectedly -> GOAL_INTERPRETATION_ERROR
    """

    def decompose(
        self,
        report: SurpriseReport,
        predicted_changes: list[PredictedChange],
        actual_changes: list[ObjectTransition],
        belief_ledger: BeliefLedger | None = None,
    ) -> list[ErrorDiagnosis]:
        """Produce a list of error diagnoses for a surprise report.

        Returns one or more ErrorDiagnosis, sorted by confidence (descending).
        """
        if not report.is_surprising:
            return []

        diagnoses: list[ErrorDiagnosis] = []

        # Build helpers
        predicted_obj_ids = {pc.obj_id for pc in predicted_changes if pc.obj_id}
        predicted_kinds: dict[str, TransitionKind] = {
            pc.obj_id: pc.kind
            for pc in predicted_changes
            if pc.obj_id and pc.kind
        }
        actual_by_id: dict[str, ObjectTransition] = {
            t.obj_id: t for t in actual_changes
        }
        actual_values: dict[int, list[ObjectTransition]] = defaultdict(list)
        for t in actual_changes:
            actual_values[t.value].append(t)

        # --- COLLISION_ERROR: predicted MOVED but object DISAPPEARED ---
        for pc in report.missing_changes:
            if pc.kind == TransitionKind.MOVED and pc.obj_id:
                # Check if the object disappeared or didn't move
                actual_t = actual_by_id.get(pc.obj_id)
                if actual_t is None:
                    # Object is not in any transition -> it stayed put (blocked)
                    diagnoses.append(ErrorDiagnosis(
                        category=ErrorCategory.COLLISION_ERROR,
                        confidence=0.75,
                        detail=(f"Object {pc.obj_id} was predicted to move but "
                                "did not appear in actual transitions (likely blocked)."),
                    ))
                elif actual_t.kind == TransitionKind.DISAPPEARED:
                    diagnoses.append(ErrorDiagnosis(
                        category=ErrorCategory.COLLISION_ERROR,
                        confidence=0.80,
                        detail=(f"Object {pc.obj_id} was predicted to move but "
                                "disappeared (collision or destruction)."),
                    ))

        # --- HIDDEN_STATE_ERROR: unexpected APPEARED objects ---
        for u in report.unexpected_changes:
            if u.kind == TransitionKind.APPEARED:
                diagnoses.append(ErrorDiagnosis(
                    category=ErrorCategory.HIDDEN_STATE_ERROR,
                    confidence=0.70,
                    detail=(f"Object {u.obj_id} (value={u.value}) appeared "
                            "unexpectedly -- possible hidden state revealed."),
                ))

        # --- OBJECT_IDENTITY_ERROR: wrong object of same value affected ---
        for pc in report.missing_changes:
            if not pc.obj_id:
                continue
            # Find actual transitions on same-value objects
            # Infer value from obj_id pattern "obj_{value}_{counter}"
            parts = pc.obj_id.split("_")
            if len(parts) >= 2:
                try:
                    pred_value = int(parts[1])
                except ValueError:
                    continue
                same_value_actuals = actual_values.get(pred_value, [])
                for t in same_value_actuals:
                    if t.obj_id != pc.obj_id:
                        diagnoses.append(ErrorDiagnosis(
                            category=ErrorCategory.OBJECT_IDENTITY_ERROR,
                            confidence=0.65,
                            detail=(f"Predicted change on {pc.obj_id} but "
                                    f"{t.obj_id} (same value={pred_value}) "
                                    "was affected instead."),
                        ))
                        break  # one diagnosis per missing prediction

        # --- ACTION_SEMANTICS_ERROR: right object, wrong transition kind ---
        for u in report.unexpected_changes:
            if u.obj_id in predicted_kinds:
                expected_kind = predicted_kinds[u.obj_id]
                if u.kind != expected_kind:
                    diagnoses.append(ErrorDiagnosis(
                        category=ErrorCategory.ACTION_SEMANTICS_ERROR,
                        confidence=0.70,
                        detail=(f"Object {u.obj_id}: predicted {expected_kind.name} "
                                f"but observed {u.kind.name}."),
                    ))

        # --- INTERACTION_ERROR: multiple objects changed in unexpected ways ---
        unexpected_ids = {u.obj_id for u in report.unexpected_changes}
        if len(unexpected_ids) >= 2:
            diagnoses.append(ErrorDiagnosis(
                category=ErrorCategory.INTERACTION_ERROR,
                confidence=0.55,
                detail=(f"Multiple objects changed unexpectedly "
                        f"({', '.join(sorted(unexpected_ids))}); "
                        "possible unknown interaction."),
            ))

        # --- GOAL_INTERPRETATION_ERROR: goal-related motif contradicted ---
        if belief_ledger:
            goal_motifs = {m.name for m in belief_ledger.top_motifs
                           if m.confidence > 0.5}
            # If there are unexpected changes and a high-confidence goal belief,
            # the goal interpretation may be wrong
            if report.unexpected_changes and belief_ledger.goal_beliefs:
                for gb in belief_ledger.goal_beliefs:
                    if gb.confidence > 0.5:
                        diagnoses.append(ErrorDiagnosis(
                            category=ErrorCategory.GOAL_INTERPRETATION_ERROR,
                            confidence=0.45,
                            detail=(f"Surprise occurred while goal belief "
                                    f"'{gb.summary[:60]}' has confidence "
                                    f"{gb.confidence:.2f}; goal may be misunderstood."),
                        ))

        # --- Fallback: generic action semantics error if nothing else matched ---
        if not diagnoses and report.is_surprising:
            diagnoses.append(ErrorDiagnosis(
                category=ErrorCategory.ACTION_SEMANTICS_ERROR,
                confidence=0.40,
                detail="Prediction did not match reality; action semantics may differ.",
            ))

        # Implicate hypotheses whose predictions overlap with the error
        if belief_ledger:
            self._implicate_hypotheses(diagnoses, report, belief_ledger)

        # Sort by confidence descending
        diagnoses.sort(key=lambda d: d.confidence, reverse=True)
        return diagnoses

    @staticmethod
    def _implicate_hypotheses(
        diagnoses: list[ErrorDiagnosis],
        report: SurpriseReport,
        ledger: BeliefLedger,
    ) -> None:
        """Attach hypothesis IDs to diagnoses when a hypothesis predicted
        something that turned out wrong."""
        for diag in diagnoses:
            for h in ledger.hypotheses:
                if h.status == "discarded":
                    continue
                # Check if any predicted_observation mentions affected objects
                detail_lower = diag.detail.lower()
                for pred_obs in h.predicted_observations:
                    if any(token in detail_lower
                           for token in pred_obs.lower().split()
                           if len(token) > 3):
                        diag.implicated_hypothesis_ids.append(h.hypothesis_id)
                        break


# ===================================================================
# 3. BeliefReviser
# ===================================================================

class BeliefReviser:
    """Update belief ledger confidences based on surprise analysis.

    Rules:
      - Hypotheses whose predictions matched actual -> confidence + boost.
      - Hypotheses implicated in error diagnoses -> confidence - penalty.
      - If no hypothesis explains the surprise -> suggest a new one.
      - If surprise contradicts a motif's core assumption -> update motif.
    """

    # Confidence adjustment amounts
    CORRECT_BOOST = 0.10
    WRONG_PENALTY_MILD = 0.05
    WRONG_PENALTY_MODERATE = 0.10
    WRONG_PENALTY_SEVERE = 0.20

    # Confidence floor and ceiling
    CONF_MIN = 0.01
    CONF_MAX = 0.99

    def revise(
        self,
        report: SurpriseReport,
        diagnoses: list[ErrorDiagnosis],
        belief_ledger: BeliefLedger,
    ) -> RevisionResult:
        """Apply belief revisions and return the result.

        Modifies the belief_ledger in-place (confidence and status fields)
        and returns a RevisionResult documenting what changed.
        """
        result = RevisionResult()

        if not report.is_surprising:
            # No surprise -> boost all active hypotheses slightly
            for h in belief_ledger.hypotheses:
                if h.status in ("active", "provisional"):
                    result.actions.append(self._boost(h, self.CORRECT_BOOST * 0.5,
                                                      "no surprise; mild confirmation"))
            return result

        # Determine penalty based on severity
        penalty = {
            SurpriseSeverity.MILD: self.WRONG_PENALTY_MILD,
            SurpriseSeverity.MODERATE: self.WRONG_PENALTY_MODERATE,
            SurpriseSeverity.SEVERE: self.WRONG_PENALTY_SEVERE,
        }.get(report.severity, self.WRONG_PENALTY_MILD)

        # Collect implicated hypothesis IDs across all diagnoses
        implicated_ids: set[str] = set()
        for diag in diagnoses:
            implicated_ids.update(diag.implicated_hypothesis_ids)

        for h in belief_ledger.hypotheses:
            if h.status == "discarded":
                continue

            if h.hypothesis_id in implicated_ids:
                # Penalise
                action = self._penalise(h, penalty,
                                        f"implicated in surprise ({report.severity.name})")
                result.actions.append(action)
            else:
                # Not implicated -> boost (consistent with actual result)
                action = self._boost(h, self.CORRECT_BOOST,
                                     "consistent with observed outcome")
                result.actions.append(action)

        # If no hypothesis explains the surprise, suggest a new one
        if not implicated_ids:
            suggestion = self._suggest_new_hypothesis(report, diagnoses)
            if suggestion:
                result.suggested_hypotheses.append(suggestion)

        # Check motif beliefs against surprise
        motif_updates = self._check_motif_beliefs(report, diagnoses, belief_ledger)
        result.motif_updates.extend(motif_updates)

        return result

    def _boost(self, h: HypothesisEntry, amount: float, reason: str) -> RevisionAction:
        old_conf = h.confidence
        old_status = h.status
        h.confidence = min(h.confidence + amount, self.CONF_MAX)
        # Promote provisional to active if confidence crosses 0.3
        if h.status == "provisional" and h.confidence >= 0.30:
            h.status = "active"
        return RevisionAction(
            hypothesis_id=h.hypothesis_id,
            old_confidence=old_conf,
            new_confidence=h.confidence,
            old_status=old_status,
            new_status=h.status,
            reason=reason,
        )

    def _penalise(self, h: HypothesisEntry, amount: float, reason: str) -> RevisionAction:
        old_conf = h.confidence
        old_status = h.status
        h.confidence = max(h.confidence - amount, self.CONF_MIN)
        # Demote active to provisional if confidence drops below 0.15
        if h.status == "active" and h.confidence < 0.15:
            h.status = "provisional"
        # Discard if confidence is near floor
        if h.confidence <= self.CONF_MIN + 0.01:
            h.status = "discarded"
        return RevisionAction(
            hypothesis_id=h.hypothesis_id,
            old_confidence=old_conf,
            new_confidence=h.confidence,
            old_status=old_status,
            new_status=h.status,
            reason=reason,
        )

    @staticmethod
    def _suggest_new_hypothesis(
        report: SurpriseReport,
        diagnoses: list[ErrorDiagnosis],
    ) -> str | None:
        """Generate a natural-language suggestion for a new hypothesis."""
        if not diagnoses:
            return None

        top = diagnoses[0]
        templates = {
            ErrorCategory.OBJECT_IDENTITY_ERROR:
                "A different object than expected was affected. "
                "Consider a hypothesis where object identity depends on position or context.",
            ErrorCategory.ACTION_SEMANTICS_ERROR:
                "The action produced a different effect than expected. "
                "Consider a hypothesis with alternative action semantics.",
            ErrorCategory.HIDDEN_STATE_ERROR:
                "An untracked element appeared. "
                "Consider a hypothesis involving hidden state or delayed effects.",
            ErrorCategory.GOAL_INTERPRETATION_ERROR:
                "The win condition may differ from current assumptions. "
                "Consider re-examining what constitutes task completion.",
            ErrorCategory.INTERACTION_ERROR:
                "Multiple objects interacted unexpectedly. "
                "Consider a hypothesis involving object-object interactions or rules.",
            ErrorCategory.COLLISION_ERROR:
                "Movement was blocked or an object was destroyed. "
                "Consider a hypothesis with wall/barrier mechanics or collision rules.",
        }
        return templates.get(top.category, "Unexpected outcome; consider a new hypothesis.")

    @staticmethod
    def _check_motif_beliefs(
        report: SurpriseReport,
        diagnoses: list[ErrorDiagnosis],
        ledger: BeliefLedger,
    ) -> list[str]:
        """Flag motif beliefs that may need updating due to surprise."""
        updates: list[str] = []
        category_set = {d.category for d in diagnoses}

        for motif in ledger.top_motifs:
            # Navigation motifs are contradicted by collision errors
            if (motif.name.lower() in ("navigation", "movement", "pathfinding")
                    and ErrorCategory.COLLISION_ERROR in category_set
                    and motif.confidence > 0.3):
                motif.confidence = max(motif.confidence - 0.15, 0.0)
                updates.append(
                    f"Motif '{motif.name}' confidence reduced due to collision error."
                )

            # Sorting/ordering motifs contradicted by identity errors
            if (motif.name.lower() in ("sorting", "ordering", "arrangement")
                    and ErrorCategory.OBJECT_IDENTITY_ERROR in category_set
                    and motif.confidence > 0.3):
                motif.confidence = max(motif.confidence - 0.10, 0.0)
                updates.append(
                    f"Motif '{motif.name}' confidence reduced due to identity error."
                )

            # Hidden state contradicts simple motifs
            if (ErrorCategory.HIDDEN_STATE_ERROR in category_set
                    and motif.confidence > 0.5):
                motif.confidence = max(motif.confidence - 0.05, 0.0)
                updates.append(
                    f"Motif '{motif.name}' confidence slightly reduced; "
                    "hidden state suggests more complex mechanics."
                )

        return updates


# ===================================================================
# 4. AntiAnchoringGuard
# ===================================================================

class AntiAnchoringGuard:
    """Prevent over-commitment to wrong hypotheses.

    Tracks per-hypothesis surprise history and triggers alerts when:
      - A hypothesis has been wrong 3+ times -> force demote to "provisional".
      - A motif confidence hasn't changed in 5+ steps -> flag for review.
      - A hypothesis has a high surprise frequency (> 50% of audits).
    """

    FAILURE_THRESHOLD = 3
    STALE_STEPS_THRESHOLD = 5
    HIGH_SURPRISE_RATE = 0.50

    def __init__(self) -> None:
        # hypothesis_id -> list of (step_index, was_wrong)
        self._failure_history: dict[str, list[tuple[int, bool]]] = defaultdict(list)
        # motif_name -> list of (step_index, confidence_value)
        self._motif_confidence_history: dict[str, list[tuple[int, float]]] = defaultdict(list)

    @property
    def failure_history(self) -> dict[str, list[tuple[int, bool]]]:
        return dict(self._failure_history)

    @property
    def motif_confidence_history(self) -> dict[str, list[tuple[int, float]]]:
        return dict(self._motif_confidence_history)

    def record_audit(
        self,
        step_index: int,
        implicated_ids: set[str],
        all_hypothesis_ids: set[str],
        belief_ledger: BeliefLedger,
    ) -> None:
        """Record the result of an audit step for future tracking."""
        for hid in all_hypothesis_ids:
            was_wrong = hid in implicated_ids
            self._failure_history[hid].append((step_index, was_wrong))

        for motif in belief_ledger.top_motifs:
            self._motif_confidence_history[motif.name].append(
                (step_index, motif.confidence)
            )

    def check(self, belief_ledger: BeliefLedger) -> list[AnchoringAlert]:
        """Check for anchoring issues and return alerts.

        Also applies forced demotions when thresholds are exceeded.
        """
        alerts: list[AnchoringAlert] = []

        # --- Repeated failure check ---
        for h in belief_ledger.hypotheses:
            if h.status == "discarded":
                continue
            history = self._failure_history.get(h.hypothesis_id, [])
            failure_count = sum(1 for _, was_wrong in history if was_wrong)
            total_count = len(history)

            # 3+ failures -> force demote to provisional
            if failure_count >= self.FAILURE_THRESHOLD and h.status == "active":
                h.status = "provisional"
                h.confidence = min(h.confidence, 0.20)
                alerts.append(AnchoringAlert(
                    hypothesis_id=h.hypothesis_id,
                    alert_type="repeated_failure",
                    detail=(f"Hypothesis {h.hypothesis_id} has been wrong "
                            f"{failure_count}/{total_count} times; "
                            "force-demoted to provisional."),
                ))

            # High surprise rate (> 50%)
            if (total_count >= 4
                    and failure_count / total_count > self.HIGH_SURPRISE_RATE):
                alerts.append(AnchoringAlert(
                    hypothesis_id=h.hypothesis_id,
                    alert_type="high_surprise_rate",
                    detail=(f"Hypothesis {h.hypothesis_id} surprise rate "
                            f"= {failure_count}/{total_count} "
                            f"({failure_count/total_count:.0%}); consider discarding."),
                ))

        # --- Stale motif confidence check ---
        for motif in belief_ledger.top_motifs:
            history = self._motif_confidence_history.get(motif.name, [])
            if len(history) >= self.STALE_STEPS_THRESHOLD:
                recent = history[-self.STALE_STEPS_THRESHOLD:]
                confidences = [c for _, c in recent]
                if len(set(confidences)) == 1:
                    alerts.append(AnchoringAlert(
                        hypothesis_id=f"motif:{motif.name}",
                        alert_type="stale_confidence",
                        detail=(f"Motif '{motif.name}' confidence has been "
                                f"unchanged at {confidences[0]:.2f} for "
                                f"{self.STALE_STEPS_THRESHOLD}+ steps; "
                                "flag for review."),
                    ))

        return alerts


# ===================================================================
# Convenience: full audit pipeline
# ===================================================================

def audit_step(
    predicted_changes: list[PredictedChange],
    actual_changes: list[ObjectTransition],
    belief_ledger: BeliefLedger,
    step_index: int,
    anti_anchoring_guard: AntiAnchoringGuard | None = None,
) -> dict[str, Any]:
    """Run the full surprise-audit pipeline for one step.

    Returns a dict with keys: report, diagnoses, revision, alerts.
    """
    # 1. Detect surprise
    detector = SurpriseDetector()
    report = detector.detect(predicted_changes, actual_changes)

    # 2. Decompose errors
    decomposer = ErrorDecomposer()
    diagnoses = decomposer.decompose(report, predicted_changes, actual_changes,
                                     belief_ledger)

    # 3. Revise beliefs
    reviser = BeliefReviser()
    revision = reviser.revise(report, diagnoses, belief_ledger)

    # 4. Anti-anchoring guard
    alerts: list[AnchoringAlert] = []
    if anti_anchoring_guard is not None:
        implicated_ids = set()
        for diag in diagnoses:
            implicated_ids.update(diag.implicated_hypothesis_ids)
        all_ids = {h.hypothesis_id for h in belief_ledger.hypotheses
                   if h.status != "discarded"}
        anti_anchoring_guard.record_audit(
            step_index, implicated_ids, all_ids, belief_ledger)
        alerts = anti_anchoring_guard.check(belief_ledger)

    return {
        "report": report,
        "diagnoses": diagnoses,
        "revision": revision,
        "alerts": alerts,
    }


# ===================================================================
# Tests
# ===================================================================

if __name__ == "__main__":

    def _header(title: str) -> None:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")

    # ---- Helper: build a test belief ledger ----
    def _make_ledger() -> BeliefLedger:
        return BeliefLedger(
            episode_id="test-ep",
            game_id="test-game",
            step_index=5,
            mode="epistemic",
            top_motifs=[
                MotifBelief(name="navigation", confidence=0.6,
                            evidence=["directional actions"]),
                MotifBelief(name="sorting", confidence=0.3,
                            evidence=["repeated objects"]),
            ],
            hypotheses=[
                HypothesisEntry(
                    hypothesis_id="H1",
                    summary="Player moves in a grid world.",
                    confidence=0.55,
                    status="active",
                    predicted_observations=[
                        "ACTION1 moves the player object upward.",
                        "Object obj_1_1 shifts position.",
                    ],
                    evidence=["Directional actions detected."],
                ),
                HypothesisEntry(
                    hypothesis_id="H2",
                    summary="Objects are sorted by click-swap.",
                    confidence=0.30,
                    status="provisional",
                    predicted_observations=[
                        "ACTION6 selects objects for swapping.",
                        "Objects rearrange into sorted order.",
                    ],
                    evidence=["Multiple same-size objects."],
                ),
                HypothesisEntry(
                    hypothesis_id="H3",
                    summary="Pattern matching with hidden targets.",
                    confidence=0.15,
                    status="provisional",
                    predicted_observations=[
                        "Hidden target revealed on confirmation.",
                        "ACTION5 confirms placement.",
                    ],
                    evidence=["Reference box detected."],
                ),
            ],
            goal_beliefs=[],
        )

    # =================================================================
    # Test 1: SurpriseDetector -- no surprise
    # =================================================================
    _header("Test 1: SurpriseDetector -- no surprise")
    detector = SurpriseDetector()
    predicted = [
        PredictedChange(obj_id="obj_1_1", kind=TransitionKind.MOVED,
                        description="player moves up"),
    ]
    actual = [
        ObjectTransition(kind=TransitionKind.MOVED, obj_id="obj_1_1", value=1,
                         prev_center=(5.0, 5.0), curr_center=(4.0, 5.0),
                         detail="dist=1.0"),
    ]
    report = detector.detect(predicted, actual)
    print(f"Severity: {report.severity.name}")
    print(f"Summary: {report.summary}")
    assert report.severity == SurpriseSeverity.NONE
    assert len(report.matched_changes) == 1
    assert len(report.unexpected_changes) == 0
    assert len(report.missing_changes) == 0
    print("OK")

    # =================================================================
    # Test 2: SurpriseDetector -- mild surprise (wrong kind)
    # =================================================================
    _header("Test 2: SurpriseDetector -- mild surprise")
    predicted2 = [
        PredictedChange(obj_id="obj_1_1", kind=TransitionKind.MOVED,
                        description="player moves up"),
    ]
    actual2 = [
        ObjectTransition(kind=TransitionKind.TRANSFORMED, obj_id="obj_1_1", value=1,
                         prev_center=(5.0, 5.0), curr_center=(5.0, 5.0),
                         detail="cells 3->4"),
    ]
    report2 = detector.detect(predicted2, actual2)
    print(f"Severity: {report2.severity.name}")
    print(f"Unexpected: {len(report2.unexpected_changes)}")
    assert report2.severity in (SurpriseSeverity.MILD, SurpriseSeverity.MODERATE)
    assert len(report2.unexpected_changes) == 1
    print("OK")

    # =================================================================
    # Test 3: SurpriseDetector -- severe surprise
    # =================================================================
    _header("Test 3: SurpriseDetector -- severe surprise")
    predicted3 = [
        PredictedChange(obj_id="obj_1_1", kind=TransitionKind.MOVED),
    ]
    actual3 = [
        ObjectTransition(kind=TransitionKind.DISAPPEARED, obj_id="obj_1_1", value=1,
                         prev_center=(5.0, 5.0)),
        ObjectTransition(kind=TransitionKind.APPEARED, obj_id="obj_9_1", value=9,
                         curr_center=(0.0, 0.0), detail="new"),
        ObjectTransition(kind=TransitionKind.APPEARED, obj_id="obj_8_1", value=8,
                         curr_center=(1.0, 1.0), detail="new"),
        ObjectTransition(kind=TransitionKind.TRANSFORMED, obj_id="obj_2_1", value=2,
                         prev_center=(4.0, 4.0), curr_center=(4.0, 4.0)),
    ]
    report3 = detector.detect(predicted3, actual3)
    print(f"Severity: {report3.severity.name}")
    print(f"Unexpected: {len(report3.unexpected_changes)}")
    assert report3.severity == SurpriseSeverity.SEVERE
    print("OK")

    # =================================================================
    # Test 4: ErrorDecomposer
    # =================================================================
    _header("Test 4: ErrorDecomposer")
    ledger = _make_ledger()
    decomposer = ErrorDecomposer()
    diagnoses = decomposer.decompose(report3, predicted3, actual3, ledger)
    print(f"Diagnoses: {len(diagnoses)}")
    categories_found = set()
    for d in diagnoses:
        print(f"  {d.category.name} (conf={d.confidence:.2f}): {d.detail[:80]}")
        categories_found.add(d.category)
    assert ErrorCategory.HIDDEN_STATE_ERROR in categories_found, \
        "should detect hidden state (APPEARED objects)"
    print("OK")

    # =================================================================
    # Test 5: ErrorDecomposer -- collision error
    # =================================================================
    _header("Test 5: ErrorDecomposer -- collision detection")
    pred_move = [PredictedChange(obj_id="obj_1_1", kind=TransitionKind.MOVED)]
    actual_blocked: list[ObjectTransition] = []  # object not in transitions at all
    report_blocked = detector.detect(pred_move, actual_blocked)
    diag_blocked = decomposer.decompose(report_blocked, pred_move, actual_blocked, ledger)
    print(f"Diagnoses: {len(diag_blocked)}")
    for d in diag_blocked:
        print(f"  {d.category.name}: {d.detail[:80]}")
    collision_diags = [d for d in diag_blocked
                       if d.category == ErrorCategory.COLLISION_ERROR]
    assert len(collision_diags) >= 1, "should detect collision error"
    print("OK")

    # =================================================================
    # Test 6: BeliefReviser -- no surprise
    # =================================================================
    _header("Test 6: BeliefReviser -- no surprise (gentle boost)")
    ledger6 = _make_ledger()
    reviser = BeliefReviser()
    revision6 = reviser.revise(report, [], ledger6)  # report from test 1 (no surprise)
    print(f"Revision actions: {len(revision6.actions)}")
    for ra in revision6.actions:
        print(f"  {ra.hypothesis_id}: {ra.old_confidence:.2f} -> "
              f"{ra.new_confidence:.2f} ({ra.reason})")
    # All should be boosted
    for ra in revision6.actions:
        assert ra.new_confidence >= ra.old_confidence, "no surprise = boost"
    print("OK")

    # =================================================================
    # Test 7: BeliefReviser -- severe surprise with implicated hypothesis
    # =================================================================
    _header("Test 7: BeliefReviser -- severe surprise")
    ledger7 = _make_ledger()
    revision7 = reviser.revise(report3, diagnoses, ledger7)
    print(f"Revision actions: {len(revision7.actions)}")
    for ra in revision7.actions:
        print(f"  {ra.hypothesis_id}: {ra.old_confidence:.2f} -> "
              f"{ra.new_confidence:.2f} [{ra.old_status} -> {ra.new_status}] "
              f"({ra.reason})")
    print(f"Suggested hypotheses: {revision7.suggested_hypotheses}")
    print(f"Motif updates: {revision7.motif_updates}")
    print("OK")

    # =================================================================
    # Test 8: AntiAnchoringGuard -- repeated failures
    # =================================================================
    _header("Test 8: AntiAnchoringGuard -- repeated failures")
    guard = AntiAnchoringGuard()
    ledger8 = _make_ledger()

    # Simulate H1 being wrong 4 times in a row
    for step in range(4):
        guard.record_audit(
            step_index=step,
            implicated_ids={"H1"},
            all_hypothesis_ids={"H1", "H2", "H3"},
            belief_ledger=ledger8,
        )

    alerts = guard.check(ledger8)
    print(f"Alerts: {len(alerts)}")
    for a in alerts:
        print(f"  [{a.alert_type}] {a.hypothesis_id}: {a.detail}")
    failure_alerts = [a for a in alerts if a.alert_type == "repeated_failure"]
    assert len(failure_alerts) >= 1, "should flag H1 for repeated failure"
    # H1 should be demoted
    h1 = next(h for h in ledger8.hypotheses if h.hypothesis_id == "H1")
    assert h1.status == "provisional", f"H1 should be provisional, got {h1.status}"
    print("OK")

    # =================================================================
    # Test 9: AntiAnchoringGuard -- stale motif confidence
    # =================================================================
    _header("Test 9: AntiAnchoringGuard -- stale motif confidence")
    guard9 = AntiAnchoringGuard()
    ledger9 = _make_ledger()
    # Keep motif confidence constant for 6 steps
    for step in range(6):
        guard9.record_audit(
            step_index=step,
            implicated_ids=set(),
            all_hypothesis_ids={"H1", "H2"},
            belief_ledger=ledger9,
        )
    alerts9 = guard9.check(ledger9)
    print(f"Alerts: {len(alerts9)}")
    stale_alerts = [a for a in alerts9 if a.alert_type == "stale_confidence"]
    for a in stale_alerts:
        print(f"  [{a.alert_type}] {a.hypothesis_id}: {a.detail}")
    assert len(stale_alerts) >= 1, "should flag stale motif confidence"
    print("OK")

    # =================================================================
    # Test 10: AntiAnchoringGuard -- high surprise rate
    # =================================================================
    _header("Test 10: AntiAnchoringGuard -- high surprise rate")
    guard10 = AntiAnchoringGuard()
    ledger10 = _make_ledger()
    # H2 wrong 3 out of 4 times (75% surprise rate)
    for step in range(4):
        impl = {"H2"} if step < 3 else set()
        guard10.record_audit(
            step_index=step,
            implicated_ids=impl,
            all_hypothesis_ids={"H1", "H2"},
            belief_ledger=ledger10,
        )
    alerts10 = guard10.check(ledger10)
    print(f"Alerts: {len(alerts10)}")
    rate_alerts = [a for a in alerts10 if a.alert_type == "high_surprise_rate"]
    for a in rate_alerts:
        print(f"  [{a.alert_type}] {a.hypothesis_id}: {a.detail}")
    assert len(rate_alerts) >= 1, "should flag high surprise rate for H2"
    print("OK")

    # =================================================================
    # Test 11: Full audit_step pipeline
    # =================================================================
    _header("Test 11: audit_step (full pipeline)")
    ledger11 = _make_ledger()
    guard11 = AntiAnchoringGuard()

    predicted11 = [
        PredictedChange(obj_id="obj_1_1", kind=TransitionKind.MOVED,
                        description="player moves up"),
    ]
    actual11 = [
        ObjectTransition(kind=TransitionKind.DISAPPEARED, obj_id="obj_1_1", value=1,
                         prev_center=(5.0, 5.0)),
        ObjectTransition(kind=TransitionKind.APPEARED, obj_id="obj_7_1", value=7,
                         curr_center=(2.0, 2.0), detail="new"),
    ]

    result = audit_step(
        predicted_changes=predicted11,
        actual_changes=actual11,
        belief_ledger=ledger11,
        step_index=5,
        anti_anchoring_guard=guard11,
    )

    print(f"Report severity: {result['report'].severity.name}")
    print(f"Diagnoses: {len(result['diagnoses'])}")
    for d in result["diagnoses"]:
        print(f"  {d.category.name}: {d.detail[:70]}")
    print(f"Revision actions: {len(result['revision'].actions)}")
    for ra in result["revision"].actions:
        print(f"  {ra.hypothesis_id}: {ra.old_confidence:.2f} -> {ra.new_confidence:.2f}")
    print(f"Suggested hypotheses: {result['revision'].suggested_hypotheses}")
    print(f"Alerts: {len(result['alerts'])}")

    assert result["report"].is_surprising
    assert len(result["diagnoses"]) > 0
    assert len(result["revision"].actions) > 0
    print("OK")

    # =================================================================
    # Test 12: Empty predictions and actuals
    # =================================================================
    _header("Test 12: Edge case -- empty predictions and actuals")
    report_empty = detector.detect([], [])
    assert report_empty.severity == SurpriseSeverity.NONE
    print(f"Empty -> severity={report_empty.severity.name}  OK")

    # Predictions but no actuals
    report_all_missing = detector.detect(
        [PredictedChange(obj_id="obj_1_1", kind=TransitionKind.MOVED)],
        [],
    )
    assert report_all_missing.severity != SurpriseSeverity.NONE
    print(f"Predictions only -> severity={report_all_missing.severity.name}  OK")

    # No predictions but actuals
    report_all_unexpected = detector.detect(
        [],
        [ObjectTransition(kind=TransitionKind.MOVED, obj_id="obj_1_1", value=1)],
    )
    assert report_all_unexpected.severity != SurpriseSeverity.NONE
    print(f"Actuals only -> severity={report_all_unexpected.severity.name}  OK")

    print(f"\n{'='*60}")
    print("  ALL TESTS PASSED")
    print(f"{'='*60}")
