# [Mar 30] Created by SD with GPT-5.4.

"""Queue policy helpers for bounded unattended ARC-AGI-3 loops."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from scripts.agentic_episode_metrics import estimate_actual_information_gain_for_row
from scripts.agentic_supervisor import QueueItem


@dataclass
class GameHistory:
    game_id: str
    completed_episodes: int = 0
    best_levels: int = 0
    stagnant_streak: int = 0
    recent_probe_families: list[str] = field(default_factory=list)
    recent_goal_hints: list[str] = field(default_factory=list)
    recent_next_probe_selectors: list[str] = field(default_factory=list)
    recent_resolved_modes: list[str] = field(default_factory=list)
    recent_phase_transition_reasons: list[str] = field(default_factory=list)
    recent_expected_information_gains: list[float] = field(default_factory=list)
    recent_actual_information_gains: list[float] = field(default_factory=list)
    recent_belief_revision_scores: list[float] = field(default_factory=list)
    recent_hypothesis_pruning_counts: list[float] = field(default_factory=list)
    recent_rule_discovery_scores: list[float] = field(default_factory=list)
    recent_dynamics_rule_discoveries: list[float] = field(default_factory=list)
    recent_interaction_rule_discoveries: list[float] = field(default_factory=list)
    recent_region_discoveries: list[float] = field(default_factory=list)
    recent_reference_pattern_updates: list[float] = field(default_factory=list)
    experiment_designer_followups: int = 0
    bootstrap_followups: int = 0


@dataclass
class PendingAssessment:
    item: QueueItem
    signature: str
    score: float
    keep: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "queue_id": self.item.queue_id,
            "game_id": self.item.game_id,
            "actions": self.item.actions,
            "runner": self.item.runner,
            "max_steps": self.item.max_steps,
            "llm_memory_window": self.item.llm_memory_window,
            "depth": self.item.depth,
            "expected_mode": self.item.expected_mode,
            "expected_information_gain": self.item.expected_information_gain,
            "score": round(self.score, 3),
            "keep": self.keep,
            "reasons": self.reasons,
        }


def queue_signature(item: QueueItem) -> str:
    payload = {
        "game_id": item.game_id,
        "actions": item.actions,
        "runner": item.runner,
        "max_steps": item.max_steps if item.runner == "solve_loop" else None,
        "llm_model": item.llm_model if item.runner == "solve_loop" else None,
        "llm_memory_window": item.llm_memory_window if item.runner == "solve_loop" else None,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _append_recent(values: list[str], value: str | None, limit: int = 5) -> None:
    if not value:
        return
    values.append(value)
    if len(values) > limit:
        del values[0 : len(values) - limit]


def _append_recent_float(values: list[float], value: float | None, limit: int = 5) -> None:
    if value is None:
        return
    values.append(value)
    if len(values) > limit:
        del values[0 : len(values) - limit]


def _load_observation_metrics(observation_path: str | None) -> tuple[int, str, str]:
    if not observation_path:
        return 0, "INITIAL", "UNKNOWN"
    path = Path(observation_path)
    if not path.exists():
        return 0, "INITIAL", "UNKNOWN"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        int(payload.get("levels_completed", 0)),
        str(payload.get("diff_summary", "INITIAL")),
        str(payload.get("state", "UNKNOWN")),
    )


def build_game_histories(manifest_rows: list[dict[str, object]]) -> dict[str, GameHistory]:
    histories: dict[str, GameHistory] = {}
    completed_rows_by_episode_id: dict[str, dict[str, object]] = {}
    observation_cache: dict[Path, dict[str, object]] = {}
    trace_cache: dict[Path, dict[str, object]] = {}
    for row in manifest_rows:
        if row.get("status") != "completed":
            continue
        game_id = str(row.get("game_id"))
        history = histories.setdefault(game_id, GameHistory(game_id=game_id))
        levels_completed, diff_summary, state = _load_observation_metrics(
            row.get("observation_path") if isinstance(row.get("observation_path"), str) else None
        )

        history.completed_episodes += 1
        progress = (
            state == "WON"
            or levels_completed > history.best_levels
            or diff_summary != "INITIAL"
        )
        if progress:
            history.stagnant_streak = 0
        else:
            history.stagnant_streak += 1
        history.best_levels = max(history.best_levels, levels_completed)

        probe_family = row.get("probe_family")
        goal_hint = row.get("goal_hint")
        next_probe_selector = row.get("next_probe_selector")
        resolved_mode = row.get("resolved_mode")
        phase_transition_reason = row.get("phase_transition_reason")
        next_probe = row.get("next_probe")
        followup_item = row.get("followup_item")
        _append_recent(
            history.recent_probe_families,
            str(probe_family) if isinstance(probe_family, str) else None,
        )
        _append_recent(
            history.recent_goal_hints,
            str(goal_hint) if isinstance(goal_hint, str) else None,
        )
        _append_recent(
            history.recent_next_probe_selectors,
            str(next_probe_selector) if isinstance(next_probe_selector, str) else None,
        )
        _append_recent(
            history.recent_resolved_modes,
            str(resolved_mode) if isinstance(resolved_mode, str) else None,
        )
        _append_recent(
            history.recent_phase_transition_reasons,
            str(phase_transition_reason) if isinstance(phase_transition_reason, str) else None,
        )
        next_gain = None
        if isinstance(followup_item, dict):
            raw_followup_gain = followup_item.get("expected_information_gain")
            if isinstance(raw_followup_gain, (int, float)):
                next_gain = float(raw_followup_gain)
        if next_gain is None and isinstance(next_probe, dict):
            raw_probe_gain = next_probe.get("expected_information_gain")
            if isinstance(raw_probe_gain, (int, float)):
                next_gain = float(raw_probe_gain)
        _append_recent_float(history.recent_expected_information_gains, next_gain)

        if isinstance(row.get("actual_information_gain"), (int, float)):
            actual_gain_estimate_value = float(row["actual_information_gain"])
        else:
            actual_gain_estimate = estimate_actual_information_gain_for_row(
                row,
                completed_rows_by_episode_id=completed_rows_by_episode_id,
                observation_cache=observation_cache,
                trace_cache=trace_cache,
            )
            actual_gain_estimate_value = actual_gain_estimate.value
        _append_recent_float(
            history.recent_actual_information_gains,
            actual_gain_estimate_value,
        )
        _append_recent_float(
            history.recent_belief_revision_scores,
            float(row["belief_revision_score"])
            if isinstance(row.get("belief_revision_score"), (int, float))
            else None,
        )
        _append_recent_float(
            history.recent_hypothesis_pruning_counts,
            float(row["hypothesis_pruning_count"])
            if isinstance(row.get("hypothesis_pruning_count"), (int, float))
            else None,
        )
        _append_recent_float(
            history.recent_rule_discovery_scores,
            float(row["rule_discovery_score"])
            if isinstance(row.get("rule_discovery_score"), (int, float))
            else None,
        )
        _append_recent_float(
            history.recent_dynamics_rule_discoveries,
            float(row["new_dynamics_rules_count"])
            if isinstance(row.get("new_dynamics_rules_count"), (int, float))
            else None,
        )
        _append_recent_float(
            history.recent_interaction_rule_discoveries,
            float(row["new_interaction_rules_count"])
            if isinstance(row.get("new_interaction_rules_count"), (int, float))
            else None,
        )
        _append_recent_float(
            history.recent_region_discoveries,
            float(row["new_region_count"])
            if isinstance(row.get("new_region_count"), (int, float))
            else None,
        )
        _append_recent_float(
            history.recent_reference_pattern_updates,
            float(row["reference_pattern_update_count"])
            if isinstance(row.get("reference_pattern_update_count"), (int, float))
            else None,
        )

        if probe_family == "experiment-designer-followup":
            history.experiment_designer_followups += 1
        if probe_family == "bootstrap-followup":
            history.bootstrap_followups += 1

        episode_id = row.get("episode_id")
        if isinstance(episode_id, str):
            completed_rows_by_episode_id[episode_id] = row

    return histories


def assess_queue_item(
    item: QueueItem,
    seen_signatures: set[str],
    histories: dict[str, GameHistory],
    stagnation_threshold: int = 2,
) -> PendingAssessment:
    signature = queue_signature(item)
    reasons: list[str] = []
    if signature in seen_signatures:
        return PendingAssessment(
            item=item,
            signature=signature,
            score=-999.0,
            keep=False,
            reasons=["Already executed action prefix."],
        )

    history = histories.get(item.game_id, GameHistory(game_id=item.game_id))
    score = 0.0
    last_resolved_mode = (
        history.recent_resolved_modes[-1] if history.recent_resolved_modes else None
    )

    if history.completed_episodes == 0:
        score += 0.9
        reasons.append("Fresh game with no completed episodes yet.")
    else:
        score += 0.1
        reasons.append(f"{history.completed_episodes} completed episodes already exist.")

    if item.expected_mode == "epistemic":
        score += 0.25
        reasons.append("Epistemic probe is favored in early unattended loops.")
    elif item.expected_mode == "instrumental":
        score += 0.05
        reasons.append("Instrumental follow-up is considered solve-oriented work.")
    elif item.expected_mode == "recovery":
        score += 0.18
        reasons.append("Recovery follow-up is valuable after a broken plan or surprise.")

    if item.expected_mode == "recovery":
        if last_resolved_mode == "recovery":
            score += 0.32
            reasons.append("Recent episode already entered recovery; keep the repair loop alive.")
        elif history.stagnant_streak >= stagnation_threshold:
            score += 0.14
            reasons.append("Stagnation makes recovery probes more plausible.")
    elif item.expected_mode == "epistemic":
        if last_resolved_mode == "recovery":
            score += 0.24
            reasons.append("Recent recovery suggests re-probing before another solve attempt.")
        elif last_resolved_mode == "instrumental" and history.best_levels > 0:
            score -= 0.05
            reasons.append("Recent instrumental progress slightly reduces the need for more probing.")
    elif item.expected_mode == "instrumental":
        if last_resolved_mode == "recovery":
            score -= 0.22
            reasons.append("Avoid solve-oriented follow-ups immediately after recovery.")
        elif history.best_levels > 0 or "instrumental" in history.recent_resolved_modes[-3:]:
            score += 0.2
            reasons.append("Prior progress supports another instrumental attempt.")
        elif history.completed_episodes == 0:
            score -= 0.08
            reasons.append("Fresh games get a small penalty for premature solve bias.")

    if item.depth == 0:
        score += 0.35
        reasons.append("Shallow depth is easier to audit.")
    else:
        penalty = min(0.45, 0.12 * item.depth)
        score -= penalty
        reasons.append(f"Depth penalty applied for depth={item.depth}.")

    if item.probe_family:
        if item.probe_family in history.recent_probe_families[-2:]:
            score -= 0.2
            reasons.append("Recent probe family was repeated.")
        else:
            score += 0.2
            reasons.append("Probe family is novel for this game's recent history.")

    if item.probe_family == "experiment-designer-followup":
        score += 0.32
        reasons.append("Experiment Designer follow-up is prioritized over generic bootstrap probes.")
        if "experiment_designer" not in history.recent_next_probe_selectors[-2:]:
            score += 0.08
            reasons.append("Experiment Designer selector is newly entering this game's recent history.")

    if item.probe_family == "bootstrap-followup":
        score += 0.05
        reasons.append("Bootstrap follow-up gets a small continuity bonus.")

    if item.expected_information_gain is not None:
        bounded_gain = max(0.0, min(1.0, float(item.expected_information_gain)))
        gain_bonus = 0.55 * bounded_gain
        score += gain_bonus
        reasons.append(
            f"Expected information gain bonus applied ({bounded_gain:.3f})."
        )
        if bounded_gain >= 0.65:
            score += 0.12
            reasons.append("High-value probe exceeds the strong information threshold.")
        elif bounded_gain <= 0.2 and item.depth > 0:
            score -= 0.12
            reasons.append("Low-gain follow-up is penalized once the queue has depth.")

        if history.recent_actual_information_gains:
            recent_mean = sum(history.recent_actual_information_gains) / len(
                history.recent_actual_information_gains
            )
            if bounded_gain > recent_mean + 0.08:
                score += 0.1
                reasons.append(
                    f"Probe beats the game's recent actual-gain baseline ({recent_mean:.3f})."
                )
            elif bounded_gain + 0.08 < recent_mean:
                score -= 0.08
                reasons.append(
                    f"Probe trails the game's recent actual-gain baseline ({recent_mean:.3f})."
                )
        elif history.recent_expected_information_gains:
            recent_mean = sum(history.recent_expected_information_gains) / len(
                history.recent_expected_information_gains
            )
            if bounded_gain > recent_mean + 0.08:
                score += 0.06
                reasons.append(
                    f"Probe beats the game's recent expected-gain baseline ({recent_mean:.3f})."
                )
            elif bounded_gain + 0.08 < recent_mean:
                score -= 0.05
                reasons.append(
                    f"Probe trails the game's recent expected-gain baseline ({recent_mean:.3f})."
                )
    elif item.probe_family in {"experiment-designer-followup", "bootstrap-followup"}:
        score -= 0.05
        reasons.append("Follow-up lacks expected information-gain metadata.")

    if item.goal_hint and item.goal_hint in history.recent_goal_hints[-2:]:
        score -= 0.15
        reasons.append("Goal hint repeated recently.")

    if history.recent_belief_revision_scores:
        mean_revision = sum(history.recent_belief_revision_scores) / len(
            history.recent_belief_revision_scores
        )
        if item.expected_mode in {"epistemic", "recovery"} and mean_revision >= 0.2:
            bonus = min(0.18, 0.08 + 0.16 * mean_revision)
            score += bonus
            reasons.append(
                f"Recent belief revisions are substantial ({mean_revision:.3f}); another probe may pay off."
            )
        elif (
            item.expected_mode == "instrumental"
            and history.best_levels == 0
            and mean_revision >= 0.25
        ):
            score -= 0.08
            reasons.append(
                "Beliefs are still moving quickly without level progress; defer another solve push."
            )
        elif (
            item.expected_mode in {"epistemic", "recovery"}
            and history.stagnant_streak >= stagnation_threshold
            and mean_revision < 0.05
        ):
            score -= 0.08
            reasons.append(
                "Recent probes barely revised beliefs despite stagnation."
            )

    if history.recent_hypothesis_pruning_counts:
        mean_pruning = sum(history.recent_hypothesis_pruning_counts) / len(
            history.recent_hypothesis_pruning_counts
        )
        if mean_pruning > 0 and item.expected_mode in {"epistemic", "recovery"}:
            bonus = min(0.1, 0.02 + 0.04 * mean_pruning)
            score += bonus
            reasons.append(
                f"Recent probes pruned hypotheses (avg {mean_pruning:.2f}); keep narrowing the search."
            )

    if history.recent_rule_discovery_scores:
        mean_rule_discovery = sum(history.recent_rule_discovery_scores) / len(
            history.recent_rule_discovery_scores
        )
        if item.expected_mode in {"epistemic", "recovery"} and mean_rule_discovery >= 0.12:
            bonus = min(0.2, 0.05 + 0.25 * mean_rule_discovery)
            score += bonus
            reasons.append(
                f"Recent probes discovered executable world-model structure ({mean_rule_discovery:.3f})."
            )
        elif (
            item.expected_mode == "instrumental"
            and history.best_levels == 0
            and mean_rule_discovery >= 0.18
        ):
            score -= 0.07
            reasons.append(
                "Rule discovery is still active without level progress; keep probing before another solve push."
            )

    if history.recent_reference_pattern_updates and item.expected_mode == "epistemic":
        mean_pattern_updates = sum(history.recent_reference_pattern_updates) / len(
            history.recent_reference_pattern_updates
        )
        if mean_pattern_updates > 0:
            score += min(0.08, 0.03 + 0.04 * mean_pattern_updates)
            reasons.append(
                f"Reference patterns are still being clarified (avg {mean_pattern_updates:.2f})."
            )

    if history.stagnant_streak >= stagnation_threshold:
        penalty = 0.35 * history.stagnant_streak
        if item.probe_family == "experiment-designer-followup":
            penalty *= 0.45
            reasons.append(
                "Stagnation penalty softened because this is an Experiment Designer follow-up."
            )
        score -= penalty
        reasons.append(
            f"Stagnation penalty applied because streak={history.stagnant_streak}."
        )

    if history.best_levels > 0:
        score += 0.25
        reasons.append("Game has shown prior level progress.")

    if (
        item.probe_family == "experiment-designer-followup"
        and history.bootstrap_followups > history.experiment_designer_followups
    ):
        score += 0.12
        reasons.append(
            "Selector diversity bonus: this game has relied more on bootstrap follow-ups so far."
        )

    if len(item.actions) >= 2 and item.actions[-1] not in item.actions[:-1]:
        score += 0.15
        reasons.append("Action prefix extends into a novel action.")

    keep = score > -0.75
    if not keep:
        reasons.append("Score fell below queue retention threshold.")

    return PendingAssessment(
        item=item,
        signature=signature,
        score=score,
        keep=keep,
        reasons=reasons,
    )


def effective_game_batch_cap(history: GameHistory, base_cap: int) -> int:
    cap = max(1, base_cap)
    last_resolved_mode = (
        history.recent_resolved_modes[-1] if history.recent_resolved_modes else None
    )
    if last_resolved_mode == "recovery":
        return 1
    if last_resolved_mode == "instrumental" and history.best_levels > 0:
        return max(cap, 2)
    return cap


def select_policy_batch(
    pending: list[QueueItem],
    seen_signatures: set[str],
    histories: dict[str, GameHistory],
    batch_size: int,
    max_items_per_game: int = 1,
    stagnation_threshold: int = 2,
) -> tuple[list[QueueItem], list[QueueItem], list[PendingAssessment]]:
    local_signatures: set[str] = set()
    assessments: list[PendingAssessment] = []

    for item in pending:
        signature = queue_signature(item)
        if signature in local_signatures:
            assessments.append(
                PendingAssessment(
                    item=item,
                    signature=signature,
                    score=-998.0,
                    keep=False,
                    reasons=["Duplicate action prefix inside pending queue."],
                )
            )
            continue
        local_signatures.add(signature)
        assessments.append(
            assess_queue_item(
                item=item,
                seen_signatures=seen_signatures,
                histories=histories,
                stagnation_threshold=stagnation_threshold,
            )
        )

    ranked = sorted(
        assessments,
        key=lambda assessment: (
            not assessment.keep,
            -assessment.score,
            len(assessment.item.actions),
            assessment.item.game_id,
        ),
    )

    recovery_cooloff_games = {
        assessment.item.game_id
        for assessment in ranked
        if assessment.keep
        and assessment.item.expected_mode in {"epistemic", "recovery"}
        and (
            histories.get(
                assessment.item.game_id, GameHistory(game_id=assessment.item.game_id)
            ).recent_resolved_modes[-1:]
            == ["recovery"]
        )
    }

    batch: list[QueueItem] = []
    remainder: list[QueueItem] = []
    per_game_counts: dict[str, int] = {}

    for assessment in ranked:
        if not assessment.keep:
            continue
        if (
            assessment.item.expected_mode == "instrumental"
            and assessment.item.game_id in recovery_cooloff_games
        ):
            remainder.append(assessment.item)
            continue
        history = histories.get(
            assessment.item.game_id, GameHistory(game_id=assessment.item.game_id)
        )
        game_cap = effective_game_batch_cap(history, max_items_per_game)
        game_count = per_game_counts.get(assessment.item.game_id, 0)
        if len(batch) < batch_size and game_count < game_cap:
            batch.append(assessment.item)
            per_game_counts[assessment.item.game_id] = game_count + 1
        else:
            remainder.append(assessment.item)

    return batch, remainder, ranked
