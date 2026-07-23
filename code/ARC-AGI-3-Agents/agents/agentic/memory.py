# [Mar 29] Created by SD with GPT-5.4.

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import (
    BeliefLedger,
    BeliefDiffSummary,
    DecisionRecord,
    EpisodeMetadata,
    MotifBelief,
    ObservationSnapshot,
    TrajectoryRecord,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def bootstrap_belief_ledger(
    episode_id: str,
    observation: ObservationSnapshot,
    motif_names: list[str] | None = None,
    mode: str = "epistemic",
) -> BeliefLedger:
    top_motifs = [
        MotifBelief(name=name, confidence=0.0, evidence=["bootstrap"])
        for name in (motif_names or [])
    ]
    return BeliefLedger(
        episode_id=episode_id,
        game_id=observation.game_id,
        step_index=observation.step_index,
        mode=mode,  # type: ignore[arg-type]
        top_motifs=top_motifs,
        notes=["Bootstrap ledger created from observation snapshot."],
    )


def _truncate_text(text: str | None, limit: int = 32) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _short_pid(pid: str | None) -> str:
    if not pid:
        return "anon"
    return pid if len(pid) <= 10 else pid[:10]


def _format_dynamics_rule_summary(rule: Any) -> str:
    action_name = _truncate_text(getattr(rule, "action_name", None) or "passive", 12)
    effect = _truncate_text(getattr(rule, "effect", None) or "unknown", 40)
    confidence = float(getattr(rule, "confidence", 0.0) or 0.0)
    times_verified = int(getattr(rule, "times_verified", 0) or 0)
    return f"{action_name}->{effect} (c{confidence:.2f},v{times_verified})"


def _format_interaction_rule_summary(rule: Any) -> str:
    trigger_pid = _short_pid(getattr(rule, "trigger_pid", None))
    affected_pid = _short_pid(getattr(rule, "affected_pid", None))
    rule_type = _truncate_text(getattr(rule, "rule_type", None) or "unknown", 12)
    confidence = float(getattr(rule, "confidence", 0.0) or 0.0)
    effect = _truncate_text(getattr(rule, "effect", None), 20)
    base = f"{trigger_pid} {rule_type} {affected_pid}"
    if effect and effect.lower() not in rule_type.lower():
        base = f"{base}:{effect}"
    return f"{base} (c{confidence:.2f})"


def _format_region_summary(region: Any) -> str:
    label = (
        _truncate_text(getattr(region, "name", None), 14)
        or _truncate_text(getattr(region, "role", None), 14)
        or _truncate_text(getattr(region, "region_id", None), 14)
    )
    bbox = (
        f"r{int(getattr(region, 'row_min', 0))}-{int(getattr(region, 'row_max', 0))},"
        f"c{int(getattr(region, 'col_min', 0))}-{int(getattr(region, 'col_max', 0))}"
    )
    extras = [f"trv={1 if getattr(region, 'traversable', True) else 0}"]
    dominant_value = getattr(region, "dominant_value", None)
    if dominant_value is not None:
        extras.append(f"v{dominant_value}")
    return f"{label}[{bbox},{','.join(extras)}]"


def _format_reference_pattern_summary(pattern: Any) -> str:
    surface_id = _truncate_text(getattr(pattern, "surface_id", None) or "surface", 12)
    kind = _truncate_text(getattr(pattern, "kind", None) or "unknown", 14)
    pattern_rows = list(getattr(pattern, "pattern_rows", []) or [])
    if pattern_rows:
        row_count = len(pattern_rows)
        col_count = max((len(row) for row in pattern_rows), default=0)
        preview_rows = pattern_rows[:4]
        preview = "/".join(preview_rows)
        if len(pattern_rows) > 4:
            preview += "/..."
        return f"{surface_id}:{kind} {row_count}x{col_count} {preview}"

    description = _truncate_text(getattr(pattern, "pattern_description", None), 40)
    if description:
        return f"{surface_id}:{kind} {description}"
    return f"{surface_id}:{kind}"


class TrajectoryCurator:
    def curate(
        self,
        observation: ObservationSnapshot,
        belief: BeliefLedger | None = None,
        decision: DecisionRecord | None = None,
        prediction: str | None = None,
        actual_diff: str | None = None,
        surprise: str | None = None,
        dynamics_revision: str | None = None,
        surprise_magnitude: float | None = None,
        confidence_update: dict[str, str] | None = None,
        belief_diff: BeliefDiffSummary | None = None,
        belief_revision_summary: list[str] | None = None,
        belief_revision_score: float | None = None,
        belief_revision_reasons: list[str] | None = None,
        hypothesis_pruning_count: int = 0,
        suggested_hypotheses: list[str] | None = None,
        motif_updates: list[str] | None = None,
        anchoring_alerts: list[str] | None = None,
        actual_information_gain: float | None = None,
        actual_information_gain_reasons: list[str] | None = None,
        llm_used: bool = False,
        llm_model: str | None = None,
        # Six-stage reasoning chain (data-logging-principles.md)
        observe_text: str | None = None,
        interpret_text: str | None = None,
        hypothesize_text: str | None = None,
        predict_text: str | None = None,
        result_text: str | None = None,
        revise_text: str | None = None,
        predicted_diff_cells: int | None = None,
        predicted_diff_low: int | None = None,
        predicted_diff_high: int | None = None,
        prediction_hit: bool | None = None,
    ) -> TrajectoryRecord:
        motif_beliefs = (
            {motif.name: motif.confidence for motif in belief.top_motifs}
            if belief
            else {}
        )
        active_hypotheses = (
            [
                hypothesis.summary
                for hypothesis in belief.hypotheses
                if hypothesis.status != "discarded"
            ]
            if belief
            else []
        )
        discarded_hypotheses = (
            [hypothesis for hypothesis in belief.hypotheses if hypothesis.status == "discarded"]
            if belief
            else []
        )
        dynamics_rule_summary = (
            [
                _format_dynamics_rule_summary(rule)
                for rule in sorted(
                    belief.dynamics_rules,
                    key=lambda item: (-float(item.confidence), -int(item.times_verified)),
                )[:2]
            ]
            if belief
            else []
        )
        interaction_rule_summary = (
            [
                _format_interaction_rule_summary(rule)
                for rule in sorted(
                    belief.interaction_rules,
                    key=lambda item: (-float(item.confidence), -int(item.times_observed)),
                )[:2]
            ]
            if belief
            else []
        )
        region_summary = (
            [
                _format_region_summary(region)
                for region in sorted(
                    belief.regions,
                    key=lambda item: (
                        {
                            "reference": 4,
                            "play_area": 3,
                            "barrier": 2,
                            "corridor": 1,
                            "energy_display": 1,
                            "status_display": 1,
                        }.get(item.role, 0),
                        -abs(int(item.row_max) - int(item.row_min) + 1)
                        * abs(int(item.col_max) - int(item.col_min) + 1),
                    ),
                    reverse=True,
                )[:3]
            ]
            if belief
            else []
        )
        reference_pattern_summary = (
            _format_reference_pattern_summary(
                sorted(
                    belief.reference_patterns,
                    key=lambda item: (-float(item.confidence), item.surface_id),
                )[0]
            )
            if belief and belief.reference_patterns
            else None
        )
        return TrajectoryRecord(
            episode_id=belief.episode_id if belief else "",
            game_id=observation.game_id,
            step_index=observation.step_index,
            state_summary=(
                f"{observation.state} | "
                f"L{observation.levels_completed} | "
                f"{len(observation.objects)} objects"
            ),
            motif_beliefs=motif_beliefs,
            active_hypotheses=active_hypotheses,
            action_taken=decision.chosen_action if decision else None,
            prediction=prediction,
            actual_diff=actual_diff or observation.diff_summary,
            surprise=surprise,
            surprise_magnitude=surprise_magnitude,
            confidence_update=confidence_update or {},
            belief_diff=belief_diff,
            belief_revision_summary=belief_revision_summary or [],
            suggested_hypotheses=suggested_hypotheses or [],
            motif_updates=motif_updates or [],
            anchoring_alerts=anchoring_alerts or [],
            dynamics_rule_summary=dynamics_rule_summary,
            interaction_rule_summary=interaction_rule_summary,
            region_summary=region_summary,
            reference_pattern_summary=reference_pattern_summary,
            dynamics_revision=dynamics_revision,
            active_hypothesis_count=len(active_hypotheses),
            discarded_hypothesis_count=len(discarded_hypotheses),
            hypothesis_pruning_count=hypothesis_pruning_count,
            belief_revision_score=belief_revision_score,
            belief_revision_reasons=belief_revision_reasons or [],
            actual_information_gain=actual_information_gain,
            actual_information_gain_reasons=actual_information_gain_reasons or [],
            planning_mode=belief.mode if belief else "epistemic",
            llm_used=llm_used,
            llm_model=llm_model or "",
            observe_text=observe_text,
            interpret_text=interpret_text,
            hypothesize_text=hypothesize_text,
            predict_text=predict_text,
            result_text=result_text,
            revise_text=revise_text,
            predicted_diff_cells=predicted_diff_cells,
            predicted_diff_low=predicted_diff_low,
            predicted_diff_high=predicted_diff_high,
            prediction_hit=prediction_hit,
        )


def load_trace_records(trace_path: str | Path) -> list[TrajectoryRecord]:
    path = Path(trace_path)
    if not path.exists():
        return []
    records: list[TrajectoryRecord] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        records.append(TrajectoryRecord.model_validate_json(line))
    return records


def rewrite_trace_records(trace_path: str | Path, records: list[TrajectoryRecord]) -> Path:
    path = Path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json())
            handle.write("\n")
    return path


def write_episode_metrics(episode_root: str | Path, payload: dict[str, Any]) -> Path:
    path = Path(episode_root) / "episode_metrics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


class EpisodeMemoryStore:
    def __init__(self, root: Path, metadata: EpisodeMetadata) -> None:
        self.root = root
        self.metadata = metadata
        self.steps_dir = self.root / "steps"
        self.trace_path = self.root / "episode_trace.jsonl"
        self.root.mkdir(parents=True, exist_ok=True)
        self.steps_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.root / "episode.json", self.metadata)

    @classmethod
    def create(
        cls,
        root_dir: str | Path,
        game_id: str,
        tags: list[str] | None = None,
        notes: list[str] | None = None,
        episode_id: str | None = None,
    ) -> "EpisodeMemoryStore":
        root = Path(root_dir)
        episode_id = episode_id or f"{game_id}-{uuid.uuid4().hex[:10]}"
        metadata = EpisodeMetadata(
            episode_id=episode_id,
            game_id=game_id,
            created_at=_utc_now_iso(),
            tags=tags or [],
            notes=notes or [],
        )
        return cls(root / episode_id, metadata)

    def step_path(self, step_index: int, kind: str) -> Path:
        return self.steps_dir / f"step_{step_index:04d}.{kind}.json"

    def write_observation(self, observation: ObservationSnapshot) -> Path:
        path = self.step_path(observation.step_index, "observation")
        self._write_json(path, observation)
        return path

    def write_belief(self, belief: BeliefLedger) -> Path:
        path = self.step_path(belief.step_index, "belief")
        self._write_json(path, belief)
        return path

    def write_decision(self, decision: DecisionRecord) -> Path:
        path = self.step_path(decision.step_index, "decision")
        self._write_json(path, decision)
        return path

    def append_trace(self, trace_record: TrajectoryRecord) -> Path:
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(trace_record.model_dump_json())
            handle.write("\n")
        return self.trace_path

    # --- Simulator evolution logging ---

    def write_simulator_snapshot(self, snapshot: "SimulatorSnapshot") -> Path:
        sim_dir = self.root / "simulator"
        sim_dir.mkdir(parents=True, exist_ok=True)
        path = sim_dir / f"simulator_v{snapshot.version:03d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(snapshot.model_dump(), handle, ensure_ascii=False, indent=2)
        return path

    def append_simulator_evolution(self, entry: "SimulatorEvolutionEntry") -> Path:
        sim_dir = self.root / "simulator"
        sim_dir.mkdir(parents=True, exist_ok=True)
        evo_path = sim_dir / "evolution.jsonl"
        with evo_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json())
            handle.write("\n")
        return evo_path

    def _write_json(
        self,
        path: Path,
        payload: EpisodeMetadata | ObservationSnapshot | BeliefLedger | DecisionRecord,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload.model_dump(), handle, ensure_ascii=False, indent=2)
