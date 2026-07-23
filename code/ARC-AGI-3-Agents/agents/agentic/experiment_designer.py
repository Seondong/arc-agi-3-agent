# [Mar 29] Experiment Designer for ARC-AGI-3 agentic framework.
# Created by SD with Claude Opus 4.6.

"""Experiment Designer: epistemic probe selection that maximises information
gain across competing hypotheses.

Responsibilities:
  1. Epistemic probe selection — choose actions that maximally discriminate
     between competing hypotheses.
  2. Action semantics discovery — systematic plan for testing untested actions.
  3. Reversibility checking — suggest paired probes (X then X, or X then undo)
     to discover safe exploration actions.
  4. Probe family management — avoid repeating similar probes by tracking
     families (movement, click, toggle, boundary, reversibility).
  5. Budget-aware selection — skip low-info probes when budget is tight;
     thorough exploration when generous.

Uses ProbeSuggestion from bootstrap_reasoner (not modified).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .bootstrap_reasoner import ProbeSuggestion
from .schemas import BeliefLedger, HypothesisEntry


# ===================================================================
# Probe families
# ===================================================================

class ProbeFamily(Enum):
    MOVEMENT = auto()       # ACTION1-4 directional tests
    CLICK = auto()          # ACTION6 coordinate tests
    TOGGLE = auto()         # ACTION5 confirm / use
    UNDO = auto()           # ACTION7 undo / backtrack
    BOUNDARY = auto()       # edge / wall collision tests
    REVERSIBILITY = auto()  # paired probes to test undo-ability
    HYPOTHESIS_DISCRIMINATOR = auto()  # explicitly designed to split hypotheses


# Map actions to their natural probe family
_ACTION_FAMILY: dict[str, ProbeFamily] = {
    "ACTION1": ProbeFamily.MOVEMENT,
    "ACTION2": ProbeFamily.MOVEMENT,
    "ACTION3": ProbeFamily.MOVEMENT,
    "ACTION4": ProbeFamily.MOVEMENT,
    "ACTION5": ProbeFamily.TOGGLE,
    "ACTION6": ProbeFamily.CLICK,
    "ACTION7": ProbeFamily.UNDO,
}

# Opposite direction pairs for reversibility tests
_REVERSE_PAIRS: dict[str, str] = {
    "ACTION1": "ACTION2",
    "ACTION2": "ACTION1",
    "ACTION3": "ACTION4",
    "ACTION4": "ACTION3",
}


# ===================================================================
# Probe history tracker
# ===================================================================

@dataclass
class ProbeRecord:
    """Record of a probe that was executed."""
    action: Any
    family: ProbeFamily
    step_index: int
    information_gained: float = 0.0


@dataclass
class ProbeHistory:
    """Tracks which probes have been executed and their families."""
    records: list[ProbeRecord] = field(default_factory=list)

    @property
    def tested_actions(self) -> set[str]:
        return {
            r.action if isinstance(r.action, str) else str(r.action)
            for r in self.records
        }

    @property
    def family_counts(self) -> dict[ProbeFamily, int]:
        counts: dict[ProbeFamily, int] = defaultdict(int)
        for r in self.records:
            counts[r.family] += 1
        return dict(counts)

    def family_count(self, family: ProbeFamily) -> int:
        return sum(1 for r in self.records if r.family == family)

    def record(self, action: Any, family: ProbeFamily, step_index: int,
               information_gained: float = 0.0) -> None:
        self.records.append(ProbeRecord(
            action=action, family=family, step_index=step_index,
            information_gained=information_gained,
        ))


# ===================================================================
# Information gain estimation
# ===================================================================

def _prediction_overlap(h1: HypothesisEntry, h2: HypothesisEntry) -> float:
    """Estimate how similar two hypotheses' predictions are (0=identical, 1=disjoint).

    Uses a simple token-overlap Jaccard distance on predicted_observations.
    When predictions are empty we assume maximum uncertainty (overlap = 0.5).
    """
    preds_a = set()
    for p in h1.predicted_observations:
        preds_a.update(p.lower().split())
    preds_b = set()
    for p in h2.predicted_observations:
        preds_b.update(p.lower().split())

    if not preds_a and not preds_b:
        return 0.5  # unknown — moderate discrimination assumed
    if not preds_a or not preds_b:
        return 0.7  # one is vague, some discrimination likely

    intersection = preds_a & preds_b
    union = preds_a | preds_b
    jaccard = len(intersection) / len(union)
    return 1.0 - jaccard  # higher = more different = more discriminating


def _entropy(confidences: list[float]) -> float:
    """Shannon entropy of a discrete distribution (normalised to probabilities)."""
    total = sum(confidences)
    if total <= 0:
        return 0.0
    probs = [c / total for c in confidences if c > 0]
    return -sum(p * math.log2(p) for p in probs if p > 0)


# ===================================================================
# ExperimentDesigner
# ===================================================================

class ExperimentDesigner:
    """Select the next epistemic probe to maximise information gain.

    Usage::

        designer = ExperimentDesigner()
        probe = designer.suggest_probe(
            belief_ledger=ledger,
            available_actions=["ACTION1", ..., "ACTION7"],
            step_budget=50,
            tested_actions={"ACTION1", "ACTION2"},
        )
    """

    # Budget thresholds (fraction of total budget remaining)
    BUDGET_TIGHT = 0.20      # below 20% remaining -> skip low-info probes
    BUDGET_GENEROUS = 0.60   # above 60% remaining -> thorough exploration

    # Minimum info gain to justify a probe under tight budget
    MIN_INFO_GAIN_TIGHT = 0.45

    # Family diversity: penalise families that already have >= this many probes
    FAMILY_SATURATION = 3

    # Maximum click coordinates to suggest per round
    MAX_CLICK_SUGGESTIONS = 3

    def __init__(self, probe_history: ProbeHistory | None = None):
        self.probe_history = probe_history or ProbeHistory()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def suggest_probe(
        self,
        belief_ledger: BeliefLedger,
        available_actions: list[str],
        step_budget: int,
        tested_actions: set[str] | None = None,
        affordance_scores: dict[str, float] | None = None,
        grid_rows: int = 30,
        grid_cols: int = 30,
        current_step: int = 0,
    ) -> ProbeSuggestion:
        """Return the single best probe to run next."""
        ranked = self.rank_probes(
            belief_ledger=belief_ledger,
            available_actions=available_actions,
            step_budget=step_budget,
            tested_actions=tested_actions,
            affordance_scores=affordance_scores,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            current_step=current_step,
        )
        if ranked:
            return ranked[0]

        # Ultimate fallback
        fallback_action = available_actions[0] if available_actions else "RESET"
        return ProbeSuggestion(
            action=fallback_action,
            rationale="No discriminating probe found; fallback exploration.",
            expected_information_gain=0.1,
            expected_outcome="Collect an observation for belief refinement.",
        )

    def rank_probes(
        self,
        belief_ledger: BeliefLedger,
        available_actions: list[str],
        step_budget: int,
        tested_actions: set[str] | None = None,
        affordance_scores: dict[str, float] | None = None,
        grid_rows: int = 30,
        grid_cols: int = 30,
        current_step: int = 0,
    ) -> list[ProbeSuggestion]:
        """Return all candidate probes ranked by expected information gain."""
        tested = tested_actions or self.probe_history.tested_actions
        hypotheses = [h for h in belief_ledger.hypotheses if h.status == "active"
                      or h.status == "provisional"]
        budget_fraction = (step_budget - current_step) / max(step_budget, 1)
        is_tight = budget_fraction < self.BUDGET_TIGHT
        is_generous = budget_fraction > self.BUDGET_GENEROUS

        candidates: list[ProbeSuggestion] = []

        # --- 1. Untested action discovery (highest priority early on) ---
        for action in available_actions:
            if action in tested:
                continue
            family = _ACTION_FAMILY.get(action, ProbeFamily.MOVEMENT)
            base_gain = self._untested_action_gain(action, hypotheses)

            # Diversity penalty
            base_gain = self._apply_family_penalty(base_gain, family)

            # Click actions need coordinate suggestions
            if action == "ACTION6" and affordance_scores:
                click_probes = self._suggest_click_coordinates(
                    affordance_scores, base_gain, grid_rows, grid_cols,
                )
                candidates.extend(click_probes)
            else:
                candidates.append(ProbeSuggestion(
                    action=action,
                    rationale=f"{action} has not been tested; discovery probe.",
                    expected_information_gain=round(base_gain, 3),
                    expected_outcome=f"Reveal the semantics of {action}.",
                ))

        # --- 2. Hypothesis-discriminating probes ---
        if len(hypotheses) >= 2:
            disc_probes = self._hypothesis_discriminators(
                hypotheses, available_actions, tested, belief_ledger,
            )
            candidates.extend(disc_probes)

        # --- 3. Reversibility probes ---
        if is_generous:
            rev_probes = self._reversibility_probes(available_actions, tested)
            candidates.extend(rev_probes)

        # --- 4. Boundary probes (test walls / edges) ---
        if is_generous and not is_tight:
            boundary_probes = self._boundary_probes(
                available_actions, tested, belief_ledger,
            )
            candidates.extend(boundary_probes)

        # --- 5. B2-4: Revision-aware adjustments ---
        candidates = self._apply_revision_adjustments(candidates, belief_ledger)

        # --- Budget filtering ---
        if is_tight:
            candidates = [c for c in candidates
                          if c.expected_information_gain >= self.MIN_INFO_GAIN_TIGHT]

        # --- Sort by expected information gain (descending) ---
        candidates.sort(key=lambda p: p.expected_information_gain, reverse=True)

        return candidates

    def _apply_revision_adjustments(
        self,
        candidates: list[ProbeSuggestion],
        belief_ledger: BeliefLedger,
    ) -> list[ProbeSuggestion]:
        """B2-4: Adjust probe scores based on recent belief revisions.

        - Boost probes for actions with weakened semantics (need re-verification)
        - Penalize probes that only test recently-discarded hypotheses
        - Boost probes for actions that haven't been tried since a surprise
        """
        # Identify weakened action semantics
        weakened_actions: set[str] = set()
        for action_name, ab in belief_ledger.action_beliefs.items():
            if ab.consistent_streak == 0 and ab.times_used >= 2:
                weakened_actions.add(action_name)

        # Identify recently discarded hypotheses
        discarded_ids = {
            h.hypothesis_id for h in belief_ledger.hypotheses
            if h.status == "discarded"
        }

        for probe in candidates:
            action_str = probe.action if isinstance(probe.action, str) else str(probe.action)

            # Boost weakened semantics re-verification
            if action_str in weakened_actions:
                probe.expected_information_gain = round(
                    probe.expected_information_gain * 1.3, 3
                )
                probe.rationale += " [B2-4: weakened semantics, re-verify]"

            # Penalize probes whose rationale only mentions discarded hypotheses
            if discarded_ids and "discriminat" in probe.rationale.lower():
                # If the probe was designed to discriminate hypotheses that are
                # now all discarded, reduce its value
                probe.expected_information_gain = round(
                    probe.expected_information_gain * 0.7, 3
                )

        return candidates

    def estimate_information_gain(
        self,
        action: Any,
        hypotheses: list[HypothesisEntry],
    ) -> float:
        """Estimate information gain of an action against a set of hypotheses.

        Computed as:
          gain = discrimination_score * remaining_entropy_fraction

        The discrimination score measures how differently the hypotheses
        predict the outcome of this action.  The entropy fraction ensures
        we value probes more when uncertainty is higher.
        """
        if not hypotheses:
            return 0.3  # some value for pure exploration

        # Pairwise discrimination across all hypothesis pairs
        n = len(hypotheses)
        if n < 2:
            return 0.4  # single hypothesis — any probe has moderate value

        total_discrimination = 0.0
        pair_count = 0
        for i in range(n):
            for j in range(i + 1, n):
                total_discrimination += _prediction_overlap(
                    hypotheses[i], hypotheses[j],
                )
                pair_count += 1

        avg_discrimination = total_discrimination / pair_count if pair_count else 0.0

        # Weight by current entropy (more uncertain = more valuable to probe)
        confidences = [h.confidence for h in hypotheses]
        current_entropy = _entropy(confidences)
        max_entropy = math.log2(n) if n > 1 else 1.0
        entropy_fraction = current_entropy / max_entropy if max_entropy > 0 else 0.5

        # Combine: high discrimination + high entropy = high gain
        gain = 0.5 * avg_discrimination + 0.5 * entropy_fraction

        # Action-specific bonus: untested actions have intrinsic discovery value
        action_str = action if isinstance(action, str) else str(action)
        if action_str not in self.probe_history.tested_actions:
            gain += 0.15

        return min(round(gain, 3), 1.0)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _untested_action_gain(
        self, action: str, hypotheses: list[HypothesisEntry],
    ) -> float:
        """Score an untested action.  Untested actions have high intrinsic
        value because they reveal entirely new semantics."""
        base = 0.70  # high base for discovery

        # Bonus if action is relevant to action_semantics expectations
        # (hypotheses that mention the action imply it is meaningful)
        mention_count = sum(
            1 for h in hypotheses
            for p in h.predicted_observations
            if action.lower() in p.lower()
        )
        base += min(mention_count * 0.05, 0.15)

        # Higher gain for click actions (they reveal coordinate semantics)
        if action == "ACTION6":
            base += 0.05
        # Moderate gain for undo (reveals reversibility globally)
        if action == "ACTION7":
            base += 0.03

        return min(base, 1.0)

    def _apply_family_penalty(self, gain: float, family: ProbeFamily) -> float:
        """Reduce gain for families that are already well-explored."""
        count = self.probe_history.family_count(family)
        if count >= self.FAMILY_SATURATION:
            penalty = 0.10 * (count - self.FAMILY_SATURATION + 1)
            gain = max(gain - penalty, 0.05)
        return gain

    def _suggest_click_coordinates(
        self,
        affordance_scores: dict[str, float],
        base_gain: float,
        grid_rows: int,
        grid_cols: int,
    ) -> list[ProbeSuggestion]:
        """For ACTION6 (click), suggest coordinates based on affordance scores.

        Returns up to MAX_CLICK_SUGGESTIONS probes targeting:
          1. Highest-affordance object center.
          2. Grid center (neutral baseline).
          3. Second-highest-affordance object (if available).
        """
        probes: list[ProbeSuggestion] = []

        # Sort objects by affordance score
        sorted_objects = sorted(
            affordance_scores.items(), key=lambda x: x[1], reverse=True,
        )

        # Top affordance target
        if sorted_objects:
            top_obj_id, top_score = sorted_objects[0]
            probes.append(ProbeSuggestion(
                action={"action": "ACTION6", "target": top_obj_id,
                        "rationale": "highest affordance object"},
                rationale=(f"Click on {top_obj_id} (affordance={top_score:.2f}), "
                           "the most interactable object."),
                expected_information_gain=round(base_gain + top_score * 0.15, 3),
                expected_outcome="Discover if clicking high-affordance objects triggers state change.",
            ))

        # Grid center as baseline
        center_r, center_c = grid_rows // 2, grid_cols // 2
        probes.append(ProbeSuggestion(
            action={"action": "ACTION6", "coordinate": [center_r, center_c]},
            rationale="Click grid center as a neutral baseline probe.",
            expected_information_gain=round(base_gain * 0.8, 3),
            expected_outcome="Reveal whether clicking empty space has any effect.",
        ))

        # Second-best affordance target
        if len(sorted_objects) >= 2:
            second_obj_id, second_score = sorted_objects[1]
            probes.append(ProbeSuggestion(
                action={"action": "ACTION6", "target": second_obj_id,
                        "rationale": "second highest affordance object"},
                rationale=(f"Click on {second_obj_id} (affordance={second_score:.2f}), "
                           "second-most interactable object."),
                expected_information_gain=round(base_gain + second_score * 0.10, 3),
                expected_outcome="Compare click effect on different objects.",
            ))

        return probes[:self.MAX_CLICK_SUGGESTIONS]

    def _hypothesis_discriminators(
        self,
        hypotheses: list[HypothesisEntry],
        available_actions: list[str],
        tested_actions: set[str],
        ledger: BeliefLedger,
    ) -> list[ProbeSuggestion]:
        """Find actions that maximally discriminate between hypothesis pairs.

        For each available action, compute pairwise prediction overlap across
        all hypothesis pairs.  Actions where hypotheses disagree most are the
        most informative.
        """
        probes: list[ProbeSuggestion] = []
        n = len(hypotheses)

        for action in available_actions:
            # Compute discrimination score for this action
            action_str = action if isinstance(action, str) else str(action)

            # Check if action semantics from ledger give us prediction hints
            semantics = ledger.action_semantics.get(action_str, [])

            # For each pair of hypotheses, estimate how differently they
            # predict the outcome of this action.
            total_disc = 0.0
            pair_count = 0
            discriminating_pairs: list[tuple[str, str]] = []

            for i in range(n):
                for j in range(i + 1, n):
                    overlap = _prediction_overlap(hypotheses[i], hypotheses[j])
                    # Boost discrimination if action semantics exist
                    # (known semantics make predictions more concrete)
                    if semantics:
                        overlap = min(overlap + 0.1, 1.0)
                    total_disc += overlap
                    pair_count += 1
                    if overlap > 0.5:
                        discriminating_pairs.append(
                            (hypotheses[i].hypothesis_id, hypotheses[j].hypothesis_id)
                        )

            if pair_count == 0:
                continue

            avg_disc = total_disc / pair_count

            # Already-tested actions get reduced (but not zero) gain —
            # repeating an action can still reveal state-dependent behavior
            if action_str in tested_actions:
                avg_disc *= 0.5

            info_gain = round(min(avg_disc * 0.9, 1.0), 3)

            family = _ACTION_FAMILY.get(action_str, ProbeFamily.HYPOTHESIS_DISCRIMINATOR)
            info_gain = self._apply_family_penalty(info_gain, family)

            if info_gain < 0.15:
                continue

            # Build rationale referencing which hypotheses disagree
            if discriminating_pairs:
                pair_strs = [f"{a} vs {b}" for a, b in discriminating_pairs[:2]]
                rationale = (f"{action_str} discriminates between {', '.join(pair_strs)}. "
                             f"Avg discrimination={avg_disc:.2f}.")
            else:
                rationale = (f"{action_str} may reveal differences across "
                             f"{n} active hypotheses.")

            probes.append(ProbeSuggestion(
                action=action_str,
                rationale=rationale,
                expected_information_gain=info_gain,
                expected_outcome=f"Clarify which hypothesis best explains {action_str} behavior.",
            ))

        return probes

    def _reversibility_probes(
        self,
        available_actions: list[str],
        tested_actions: set[str],
    ) -> list[ProbeSuggestion]:
        """Suggest paired probes to test if an action is reversible.

        Two strategies:
          (a) ACTION_X then reverse-ACTION_X (e.g., up then down).
          (b) ACTION_X then ACTION7 (undo), if ACTION7 is available.
        """
        probes: list[ProbeSuggestion] = []
        has_undo = "ACTION7" in available_actions

        for action in available_actions:
            if action == "ACTION7":
                continue

            # Skip if we already have a reversibility probe for this action
            rev_tested = any(
                r.family == ProbeFamily.REVERSIBILITY and
                (r.action == action or
                 (isinstance(r.action, dict) and r.action.get("primary") == action))
                for r in self.probe_history.records
            )
            if rev_tested:
                continue

            # Strategy (a): paired reverse
            reverse = _REVERSE_PAIRS.get(action)
            if reverse and reverse in available_actions and action in tested_actions:
                probes.append(ProbeSuggestion(
                    action={"sequence": [action, reverse],
                            "primary": action,
                            "probe_type": "reversibility_pair"},
                    rationale=(f"Test reversibility: {action} then {reverse}. "
                               "If state returns to original, the action is reversible."),
                    expected_information_gain=0.55,
                    expected_outcome=(f"Determine if {action}/{reverse} are inverse operations. "
                                      "Reversible actions are safe for exploration."),
                ))

            # Strategy (b): action then undo
            if has_undo and action in tested_actions:
                probes.append(ProbeSuggestion(
                    action={"sequence": [action, "ACTION7"],
                            "primary": action,
                            "probe_type": "reversibility_undo"},
                    rationale=(f"Test if ACTION7 undoes {action}. "
                               "Confirms whether ACTION7 is a general undo."),
                    expected_information_gain=0.50,
                    expected_outcome=f"Reveal if ACTION7 reverses {action}.",
                ))

        return probes

    def _boundary_probes(
        self,
        available_actions: list[str],
        tested_actions: set[str],
        ledger: BeliefLedger,
    ) -> list[ProbeSuggestion]:
        """Suggest probes to test boundary / edge behavior.

        Repeatedly applying a directional action should eventually hit a wall.
        This reveals grid topology (wrapping? blocking? energy cost?).
        """
        probes: list[ProbeSuggestion] = []
        directional = {"ACTION1", "ACTION2", "ACTION3", "ACTION4"}

        for action in directional:
            if action not in available_actions:
                continue
            if action not in tested_actions:
                continue  # test basic semantics first

            # Check if we already have a boundary probe for this direction
            boundary_tested = any(
                r.family == ProbeFamily.BOUNDARY and r.action == action
                for r in self.probe_history.records
            )
            if boundary_tested:
                continue

            semantics = ledger.action_semantics.get(action, [])
            direction_hint = semantics[0] if semantics else action

            probes.append(ProbeSuggestion(
                action={"action": action, "repeat": 5,
                        "probe_type": "boundary_test"},
                rationale=(f"Repeat {action} 5 times to test boundary behavior. "
                           f"Hint: {direction_hint}."),
                expected_information_gain=0.40,
                expected_outcome=(f"Reveal wall/edge behavior for {action}: "
                                  "blocking, wrapping, or energy cost."),
            ))

        return probes


# ===================================================================
# Convenience: quick probe from a belief ledger
# ===================================================================

def design_next_probe(
    belief_ledger: BeliefLedger,
    available_actions: list[str],
    step_budget: int = 50,
    tested_actions: set[str] | None = None,
    affordance_scores: dict[str, float] | None = None,
    grid_rows: int = 30,
    grid_cols: int = 30,
    current_step: int = 0,
    probe_history: ProbeHistory | None = None,
) -> ProbeSuggestion:
    """One-shot convenience function: create a designer and pick the best probe."""
    designer = ExperimentDesigner(probe_history=probe_history)
    return designer.suggest_probe(
        belief_ledger=belief_ledger,
        available_actions=available_actions,
        step_budget=step_budget,
        tested_actions=tested_actions,
        affordance_scores=affordance_scores,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        current_step=current_step,
    )


# ===================================================================
# Tests
# ===================================================================

if __name__ == "__main__":
    from .schemas import BeliefLedger, HypothesisEntry, MotifBelief

    def _header(title: str) -> None:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")

    # --- Build a test belief ledger ---
    ledger = BeliefLedger(
        episode_id="test-ep",
        game_id="test-game",
        step_index=3,
        mode="epistemic",
        top_motifs=[
            MotifBelief(name="navigation", confidence=0.6, evidence=["directional actions"]),
            MotifBelief(name="sorting", confidence=0.4, evidence=["repeated objects"]),
        ],
        hypotheses=[
            HypothesisEntry(
                hypothesis_id="H1",
                summary="Scene follows a navigation motif.",
                confidence=0.5,
                status="active",
                predicted_observations=[
                    "Directional actions move an object across the grid.",
                    "ACTION1 shifts the player upward.",
                ],
                evidence=["Four directional actions available."],
            ),
            HypothesisEntry(
                hypothesis_id="H2",
                summary="Scene follows a sorting motif.",
                confidence=0.35,
                status="provisional",
                predicted_observations=[
                    "Actions rearrange objects into a target order.",
                    "ACTION6 selects objects for swapping.",
                ],
                evidence=["Multiple same-size objects present."],
            ),
            HypothesisEntry(
                hypothesis_id="H3",
                summary="Scene involves pattern matching.",
                confidence=0.15,
                status="provisional",
                predicted_observations=[
                    "Objects must be transformed to match a reference pattern.",
                    "ACTION5 confirms a placement.",
                ],
                evidence=["Reference box detected."],
            ),
        ],
        action_semantics={
            "ACTION1": ["Possible upward move"],
            "ACTION2": ["Possible downward move"],
            "ACTION3": ["Possible leftward move"],
            "ACTION4": ["Possible rightward move"],
            "ACTION5": ["Possible confirm action"],
            "ACTION6": ["Coordinate action"],
            "ACTION7": ["Undo action"],
        },
    )

    available = ["ACTION1", "ACTION2", "ACTION3", "ACTION4",
                 "ACTION5", "ACTION6", "ACTION7"]
    tested = {"ACTION1", "ACTION2"}

    designer = ExperimentDesigner()

    # --- Test 1: suggest_probe with untested actions ---
    _header("Test 1: suggest_probe (untested actions)")
    probe = designer.suggest_probe(
        belief_ledger=ledger,
        available_actions=available,
        step_budget=50,
        tested_actions=tested,
        current_step=5,
    )
    print(f"Action: {probe.action}")
    print(f"Rationale: {probe.rationale}")
    print(f"Info gain: {probe.expected_information_gain}")
    print(f"Expected: {probe.expected_outcome}")
    assert probe.expected_information_gain > 0.5, "untested action should have high gain"

    # --- Test 2: rank_probes ---
    _header("Test 2: rank_probes")
    ranked = designer.rank_probes(
        belief_ledger=ledger,
        available_actions=available,
        step_budget=50,
        tested_actions=tested,
        current_step=5,
    )
    print(f"Total candidates: {len(ranked)}")
    for i, p in enumerate(ranked[:5]):
        print(f"  #{i+1}: action={p.action} gain={p.expected_information_gain} "
              f"| {p.rationale[:60]}")
    assert len(ranked) >= 3, "should have multiple candidates"
    # Verify descending order
    gains = [p.expected_information_gain for p in ranked]
    assert gains == sorted(gains, reverse=True), "should be sorted by gain"

    # --- Test 3: estimate_information_gain ---
    _header("Test 3: estimate_information_gain")
    hypotheses = [h for h in ledger.hypotheses if h.status in ("active", "provisional")]
    gain = designer.estimate_information_gain("ACTION3", hypotheses)
    print(f"Info gain for ACTION3: {gain}")
    assert 0.0 < gain <= 1.0, "gain should be in (0, 1]"

    # --- Test 4: Budget-tight filtering ---
    _header("Test 4: Budget-tight filtering")
    tight_ranked = designer.rank_probes(
        belief_ledger=ledger,
        available_actions=available,
        step_budget=50,
        tested_actions=tested,
        current_step=45,  # only 5 steps left = 10% budget
    )
    print(f"Candidates under tight budget: {len(tight_ranked)}")
    for p in tight_ranked:
        assert p.expected_information_gain >= designer.MIN_INFO_GAIN_TIGHT, \
            f"tight budget should filter low-gain probes (got {p.expected_information_gain})"
        print(f"  action={p.action} gain={p.expected_information_gain}")

    # --- Test 5: Click coordinate suggestions ---
    _header("Test 5: Click coordinate suggestions")
    affordances = {
        "obj_1_1": 0.8,
        "obj_2_2": 0.5,
        "obj_5_3": 0.1,
    }
    click_ranked = designer.rank_probes(
        belief_ledger=ledger,
        available_actions=available,
        step_budget=50,
        tested_actions={"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7"},
        affordance_scores=affordances,
        grid_rows=30,
        grid_cols=30,
        current_step=10,
    )
    click_probes = [p for p in click_ranked
                    if isinstance(p.action, dict) and p.action.get("action") == "ACTION6"]
    print(f"Click probes: {len(click_probes)}")
    for p in click_probes:
        print(f"  target={p.action} gain={p.expected_information_gain}")
    assert len(click_probes) >= 2, "should suggest multiple click targets"

    # --- Test 6: Reversibility probes ---
    _header("Test 6: Reversibility probes (generous budget)")
    rev_ranked = designer.rank_probes(
        belief_ledger=ledger,
        available_actions=available,
        step_budget=100,
        tested_actions={"ACTION1", "ACTION2", "ACTION3"},
        current_step=10,  # 90% budget remaining = generous
    )
    rev_probes = [p for p in rev_ranked
                  if isinstance(p.action, dict) and
                  p.action.get("probe_type", "").startswith("reversibility")]
    print(f"Reversibility probes: {len(rev_probes)}")
    for p in rev_probes:
        print(f"  {p.action} | {p.rationale[:60]}")
    assert len(rev_probes) >= 1, "should suggest at least one reversibility probe"

    # --- Test 7: Probe history tracking ---
    _header("Test 7: Probe history & family diversity")
    history = ProbeHistory()
    # Saturate MOVEMENT family
    for i in range(5):
        history.record("ACTION1", ProbeFamily.MOVEMENT, step_index=i)

    designer2 = ExperimentDesigner(probe_history=history)
    ranked2 = designer2.rank_probes(
        belief_ledger=ledger,
        available_actions=available,
        step_budget=50,
        tested_actions=tested,
        current_step=10,
    )
    # Movement probes should have reduced gain due to saturation
    movement_probes = [p for p in ranked2
                       if isinstance(p.action, str) and p.action in
                       {"ACTION3", "ACTION4"}]
    non_movement = [p for p in ranked2
                    if isinstance(p.action, str) and p.action in
                    {"ACTION5", "ACTION6", "ACTION7"}]
    print(f"Movement probe gains: {[p.expected_information_gain for p in movement_probes]}")
    print(f"Non-movement probe gains: {[p.expected_information_gain for p in non_movement]}")

    # --- Test 8: design_next_probe convenience ---
    _header("Test 8: design_next_probe convenience function")
    quick = design_next_probe(
        belief_ledger=ledger,
        available_actions=available,
        step_budget=50,
        tested_actions=tested,
    )
    print(f"Quick probe: {quick.action} (gain={quick.expected_information_gain})")
    assert quick.expected_information_gain > 0

    print(f"\n{'='*60}")
    print("  ALL TESTS PASSED")
    print(f"{'='*60}")
