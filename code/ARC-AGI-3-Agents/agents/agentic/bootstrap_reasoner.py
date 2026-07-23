# [Mar 29] Created by SD with GPT-5.4.

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .schemas import (
    BeliefLedger,
    GoalBelief,
    HypothesisEntry,
    MotifBelief,
    ObservationSnapshot,
)


@dataclass
class ProbeSuggestion:
    action: Any
    rationale: str
    expected_information_gain: float
    expected_outcome: str


def _object_width(obj: Any) -> int:
    return obj.col_max - obj.col_min + 1


def _object_height(obj: Any) -> int:
    return obj.row_max - obj.row_min + 1


def infer_bootstrap_motifs(
    observation: ObservationSnapshot,
    seeded_names: list[str] | None = None,
) -> list[MotifBelief]:
    seeded_names = seeded_names or []
    scores: dict[str, float] = {name: 0.15 for name in seeded_names}
    evidence: dict[str, list[str]] = {name: ["seeded by queue"] for name in seeded_names}

    def bump(name: str, score: float, reason: str) -> None:
        scores[name] = scores.get(name, 0.0) + score
        evidence.setdefault(name, []).append(reason)

    available = set(observation.available_actions)
    objects = observation.objects
    object_count = len(objects)
    same_size_counter = Counter(obj.cell_count for obj in objects)
    repeated_sizes = sum(1 for _, count in same_size_counter.items() if count >= 3)

    if {"ACTION1", "ACTION2", "ACTION3", "ACTION4"}.issubset(available):
        bump("navigation", 0.22, "Four directional actions are available.")

    if "ACTION5" in available:
        bump("confirm-semantics", 0.10, "ACTION5 may be a confirm/use action.")

    if "ACTION6" in available:
        # Bootstrap uses a mild prior only; the availability of ACTION6 alone is
        # not evidence of click-semantics (e.g., sk48 has ACTION6 but is a
        # threading/movement puzzle). Effect-based reassessment in solve_step
        # will boost/demote this after a few probes.
        bump("click-semantics", 0.18, "ACTION6 available — weak prior, pending probes.")
        bump("coordinate-selection", 0.10, "Pointer-like semantics possible, pending probes.")

    if "ACTION7" in available:
        bump("reversible-manipulation", 0.08, "Undo action implies stateful planning.")

    if object_count >= 6 and repeated_sizes >= 1:
        bump("sorting", 0.20, "Many repeated object sizes suggest arrangement pressure.")
        bump("pattern-matching", 0.12, "Repeated object families may map to reference targets.")

    if any(_object_width(obj) >= 12 and _object_height(obj) <= 3 for obj in objects):
        bump("track-building", 0.12, "Long thin objects suggest rails, trails, or bars.")

    if any(_object_height(obj) >= 12 and _object_width(obj) <= 3 for obj in objects):
        bump("vertical-navigation", 0.10, "Tall thin structures suggest rails or columns.")

    if any(obj.row_min <= observation.grid_rows // 5 for obj in objects) and any(
        obj.row_max >= int(observation.grid_rows * 0.8) for obj in objects
    ):
        bump("reference-matching", 0.15, "Scene contains both upper and lower salient structures.")

    if object_count <= 4:
        bump("direct-manipulation", 0.08, "Sparse object scene may revolve around a few actors.")

    motifs = [
        MotifBelief(
            name=name,
            confidence=min(0.95, round(score, 3)),
            evidence=evidence.get(name, []),
        )
        for name, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]
    return motifs[:5]


def infer_bootstrap_goal_beliefs(observation: ObservationSnapshot) -> list[GoalBelief]:
    beliefs: list[GoalBelief] = []
    top_objects = [obj for obj in observation.objects if obj.row_min <= observation.grid_rows // 5]
    bottom_objects = [
        obj for obj in observation.objects if obj.row_max >= int(observation.grid_rows * 0.8)
    ]

    if top_objects and bottom_objects:
        beliefs.append(
            GoalBelief(
                summary="A reference-like region may need to be matched or reached.",
                confidence=0.45,
                evidence=["Salient objects exist in both top and bottom bands."],
            )
        )

    if {"ACTION1", "ACTION2", "ACTION3", "ACTION4"}.issubset(set(observation.available_actions)):
        beliefs.append(
            GoalBelief(
                summary="Progress may require navigating a controllable object through space.",
                confidence=0.35,
                evidence=["Directional actions are available."],
            )
        )

    if "ACTION6" in observation.available_actions:
        beliefs.append(
            GoalBelief(
                summary="Progress may depend on selecting coordinates or targeted regions.",
                confidence=0.40,
                evidence=["ACTION6 is available."],
            )
        )

    return beliefs[:3]


def infer_action_semantics(observation: ObservationSnapshot) -> dict[str, list[str]]:
    semantics: dict[str, list[str]] = {}
    available = set(observation.available_actions)

    if "ACTION1" in available:
        semantics["ACTION1"] = ["Possible upward move", "May test vertical mobility"]
    if "ACTION2" in available:
        semantics["ACTION2"] = ["Possible downward move", "May test vertical symmetry"]
    if "ACTION3" in available:
        semantics["ACTION3"] = ["Possible leftward move", "May retract or reverse state"]
    if "ACTION4" in available:
        semantics["ACTION4"] = ["Possible rightward move", "May extend or advance state"]
    if "ACTION5" in available:
        semantics["ACTION5"] = ["Possible confirm/use/submit action"]
    if "ACTION6" in available:
        semantics["ACTION6"] = ["Coordinate action", "May select an object or region"]
    if "ACTION7" in available:
        semantics["ACTION7"] = ["Undo or backtrack action"]

    return semantics


def build_bootstrap_hypotheses(
    motifs: list[MotifBelief],
) -> list[HypothesisEntry]:
    hypotheses: list[HypothesisEntry] = []
    for index, motif in enumerate(motifs[:3], start=1):
        hypotheses.append(
            HypothesisEntry(
                hypothesis_id=f"H{index}",
                summary=f"Scene may follow a {motif.name} motif.",
                confidence=max(0.05, round(motif.confidence * 0.8, 3)),
                status="provisional",
                predicted_observations=[
                    f"Further probes should produce evidence consistent with {motif.name}."
                ],
                evidence=motif.evidence,
            )
        )

    if not hypotheses:
        hypotheses.append(
            HypothesisEntry(
                hypothesis_id="H1",
                summary="Scene requires additional probing before a motif can be trusted.",
                confidence=0.2,
                status="provisional",
                predicted_observations=["Simple action probes should reveal the first stable mechanic."],
                evidence=["No high-confidence motif evidence yet."],
            )
        )

    return hypotheses


def build_bootstrap_ledger(
    episode_id: str,
    observation: ObservationSnapshot,
    seeded_names: list[str] | None = None,
) -> BeliefLedger:
    motifs = infer_bootstrap_motifs(observation, seeded_names=seeded_names)
    hypotheses = build_bootstrap_hypotheses(motifs)
    goals = infer_bootstrap_goal_beliefs(observation)
    action_semantics = infer_action_semantics(observation)
    notes = [
        "Bootstrap ledger enriched by heuristic Theorist/Skeptic pass.",
        f"Observation contains {len(observation.objects)} foreground objects.",
    ]
    return BeliefLedger(
        episode_id=episode_id,
        game_id=observation.game_id,
        step_index=observation.step_index,
        mode="epistemic",
        top_motifs=motifs,
        hypotheses=hypotheses,
        goal_beliefs=goals,
        action_semantics=action_semantics,
        notes=notes,
    )


def reassess_motifs_from_effects(
    belief_state: BeliefLedger,
    min_total_uses: int = 5,
) -> list[str]:
    """Reweight top_motifs from observed action effects.

    Returns a list of human-readable change notes (for logging/trace).

    Signals used:
      - ACTION1-4 marked `is_directional` (avg_cells_changed > 5) -> navigation
      - ACTION6 being noop or producing <2 cells avg -> demote click-semantics
      - No directional actions but some actions produce small effects -> track/toggle

    Called periodically from solve_step. Idempotent beyond confidence bounds.
    """
    total_uses = sum(ab.times_used for ab in belief_state.action_beliefs.values())
    if total_uses < min_total_uses:
        return []

    notes: list[str] = []

    directional = [
        ab for ab in belief_state.action_beliefs.values()
        if ab.is_directional and ab.times_used >= 1
    ]
    a6 = belief_state.action_beliefs.get("ACTION6")
    a6_dead = a6 is not None and a6.times_used >= 2 and a6.avg_cells_changed < 2.0

    for motif in belief_state.top_motifs:
        if motif.name == "navigation" and len(directional) >= 2:
            if motif.confidence < 0.80:
                old = motif.confidence
                motif.confidence = min(0.80, motif.confidence + 0.15)
                motif.evidence.append(
                    f"reassessment: {len(directional)} directional actions observed"
                )
                notes.append(f"navigation {old:.2f}->{motif.confidence:.2f} (directional evidence)")

        elif motif.name in ("click-semantics", "coordinate-selection") and a6_dead:
            if motif.confidence > 0.10:
                old = motif.confidence
                motif.confidence = max(0.05, motif.confidence - 0.30)
                motif.evidence.append(
                    f"reassessment: ACTION6 produced <2 cells over {a6.times_used} uses"
                )
                notes.append(f"{motif.name} {old:.2f}->{motif.confidence:.2f} (ACTION6 inert)")

        elif motif.name in ("track-building", "pattern-matching", "sorting"):
            # Boost if we see localized effects (not huge directional moves)
            localized = [
                ab for ab in belief_state.action_beliefs.values()
                if not ab.is_directional and not ab.is_noop and 1 < ab.avg_cells_changed < 20
            ]
            if len(localized) >= 1 and motif.confidence < 0.55:
                old = motif.confidence
                motif.confidence = min(0.55, motif.confidence + 0.08)
                motif.evidence.append(
                    f"reassessment: {len(localized)} action(s) with small localized effects"
                )
                notes.append(f"{motif.name} {old:.2f}->{motif.confidence:.2f} (localized effects)")

    return notes


def suggest_next_probe(
    observation: ObservationSnapshot,
    ledger: BeliefLedger,
) -> ProbeSuggestion:
    tried_actions = {
        action["action"] if isinstance(action, dict) and "action" in action else action
        for action in observation.action_history
    }
    available = observation.available_actions

    for action in ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6", "ACTION7"]:
        if action in available and action not in tried_actions:
            return ProbeSuggestion(
                action=action,
                rationale=f"{action} has not been tested yet in this episode bootstrap.",
                expected_information_gain=0.75,
                expected_outcome=f"Clarify the semantics of {action}.",
            )

    if "ACTION2" in available and "ACTION1" in tried_actions:
        return ProbeSuggestion(
            action="ACTION2",
            rationale="ACTION2 can test whether vertical motion is symmetric with ACTION1.",
            expected_information_gain=0.62,
            expected_outcome="Reveal whether downward motion or an inverse mechanic exists.",
        )

    if "ACTION4" in available and "ACTION3" in tried_actions:
        return ProbeSuggestion(
            action="ACTION4",
            rationale="ACTION4 can test whether horizontal motion is symmetric with ACTION3.",
            expected_information_gain=0.62,
            expected_outcome="Reveal whether rightward motion or an advance mechanic exists.",
        )

    top_motif = ledger.top_motifs[0].name if ledger.top_motifs else "exploration"
    fallback = available[0] if available else "RESET"
    return ProbeSuggestion(
        action=fallback,
        rationale=f"Fallback epistemic probe while {top_motif} remains uncertain.",
        expected_information_gain=0.3,
        expected_outcome="Collect one more observation for belief refinement.",
    )

