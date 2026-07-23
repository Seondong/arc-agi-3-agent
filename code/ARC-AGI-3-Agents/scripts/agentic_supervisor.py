# [Mar 29] Created by SD with GPT-5.4.

"""Batch supervisor for unattended ARC-AGI-3 agentic episodes.

This script reads a JSONL work queue and, for each item:
1. Creates an EpisodeMemoryStore directory
2. Replays the provided action prefix through harness.py
3. Saves a structured ObservationSnapshot via --agentic-out
4. Bootstraps a BeliefLedger and DecisionRecord
5. Appends a compact trajectory trace
6. Writes a manifest entry for later review

The intent is not to solve games autonomously yet, but to provide a reliable
outer loop that can run overnight and accumulate structured episode artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_MPLCONFIGDIR = REPO_ROOT / "artifacts" / "mplconfig"
DEFAULT_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(DEFAULT_MPLCONFIGDIR))

from agents.agentic import (
    PhaseManager,
    PhaseState,
    ProbeFamily,
    ProbeHistory,
    build_bootstrap_ledger,
    design_next_probe,
    exploration_guidance,
    suggest_next_probe,
)
from agents.agentic.memory import EpisodeMemoryStore, TrajectoryCurator
from agents.agentic.schemas import DecisionRecord, ObservationSnapshot


DEFAULT_HARNESS = REPO_ROOT / "harness.py"
DEFAULT_SOLVER_WRAPPER = REPO_ROOT / "scripts" / "run_agentic_solver_job.py"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "agentic_episodes"
DEFAULT_MANIFEST = DEFAULT_OUTPUT_ROOT / "manifest.jsonl"
DEFAULT_STEP_BUDGET = 64

MODE_TO_PHASE = {
    "epistemic": PhaseState.EPISTEMIC,
    "instrumental": PhaseState.INSTRUMENTAL,
    "recovery": PhaseState.RECOVERY,
}


@dataclass
class QueueItem:
    game_id: str
    actions: list[Any]
    motif_names: list[str]
    tags: list[str]
    notes: list[str]
    queue_id: str | None = None
    depth: int = 0
    expected_mode: str | None = None
    goal_hint: str | None = None
    probe_family: str | None = None
    expected_information_gain: float | None = None
    parent_episode_id: str | None = None
    runner: str = "bootstrap"
    max_steps: int | None = None
    llm_model: str | None = None
    llm_memory_window: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "QueueItem":
        return cls(
            game_id=payload["game_id"],
            actions=payload.get("actions", ["RESET"]),
            motif_names=payload.get("motif_names", []),
            tags=payload.get("tags", []),
            notes=payload.get("notes", []),
            queue_id=payload.get("queue_id"),
            depth=payload.get("depth", 0),
            expected_mode=payload.get("expected_mode"),
            goal_hint=payload.get("goal_hint"),
            probe_family=payload.get("probe_family"),
            expected_information_gain=payload.get("expected_information_gain"),
            parent_episode_id=payload.get("parent_episode_id"),
            runner=payload.get("runner", "bootstrap"),
            max_steps=payload.get("max_steps"),
            llm_model=payload.get("llm_model"),
            llm_memory_window=payload.get("llm_memory_window"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "game_id": self.game_id,
            "actions": self.actions,
            "motif_names": self.motif_names,
            "tags": self.tags,
            "notes": self.notes,
            "depth": self.depth,
            "expected_mode": self.expected_mode,
            "goal_hint": self.goal_hint,
            "probe_family": self.probe_family,
            "expected_information_gain": self.expected_information_gain,
            "parent_episode_id": self.parent_episode_id,
            "runner": self.runner,
            "max_steps": self.max_steps,
            "llm_model": self.llm_model,
            "llm_memory_window": self.llm_memory_window,
        }


def load_queue(queue_path: Path) -> list[QueueItem]:
    items: list[QueueItem] = []
    for raw_line in queue_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        items.append(QueueItem.from_dict(json.loads(line)))
    return items


def build_harness_command(
    python_bin: str,
    harness_path: Path,
    item: QueueItem,
    observation_path: Path,
) -> list[str]:
    return [
        python_bin,
        str(harness_path),
        "--game",
        item.game_id,
        "--actions",
        json.dumps(item.actions, ensure_ascii=False),
        "--agentic-out",
        str(observation_path),
    ]


def build_solver_command(
    python_bin: str,
    solver_wrapper_path: Path,
    item: QueueItem,
    output_root: Path,
    result_json_path: Path,
) -> list[str]:
    command = [
        python_bin,
        str(solver_wrapper_path),
        "--game",
        item.game_id,
        "--memory-root",
        str(output_root),
        "--result-json",
        str(result_json_path),
        "--quiet",
    ]
    if item.max_steps is not None:
        command.extend(["--max-steps", str(item.max_steps)])
    if item.llm_model:
        command.extend(["--llm-model", item.llm_model])
    if item.llm_memory_window is not None:
        command.extend(["--llm-memory-window", str(item.llm_memory_window)])
    return command


def append_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def append_queue_item(queue_path: Path, payload: dict[str, Any]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def build_runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    DEFAULT_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
    env.setdefault("MPLCONFIGDIR", str(DEFAULT_MPLCONFIGDIR))
    return env


def summarize_actions(actions: list[Any]) -> str:
    if not actions:
        return "No actions"
    if len(actions) == 1:
        return f"Seed action: {actions[0]}"
    return f"{len(actions)} actions seeded"


def probe_family_for_action(action: Any) -> ProbeFamily:
    action_name = action if isinstance(action, str) else str(action)
    if action_name in {"ACTION1", "ACTION2", "ACTION3", "ACTION4"}:
        return ProbeFamily.MOVEMENT
    if action_name == "ACTION5":
        return ProbeFamily.TOGGLE
    if action_name == "ACTION6":
        return ProbeFamily.CLICK
    if action_name == "ACTION7":
        return ProbeFamily.UNDO
    return ProbeFamily.HYPOTHESIS_DISCRIMINATOR


def build_probe_history(actions: list[Any], step_index: int) -> ProbeHistory:
    history = ProbeHistory()
    for offset, action in enumerate(actions):
        history.record(
            action=action,
            family=probe_family_for_action(action),
            step_index=max(0, step_index - len(actions) + offset),
        )
    return history


def ordered_tested_actions(prior_actions: list[Any], observation_actions: list[Any]) -> list[Any]:
    ordered: list[Any] = []
    seen: set[str] = set()
    for raw_action in [*prior_actions, *observation_actions]:
        action = raw_action["action"] if isinstance(raw_action, dict) and "action" in raw_action else raw_action
        action_key = str(action)
        if action_key in seen:
            continue
        seen.add(action_key)
        ordered.append(action)
    return ordered


def expand_probe_action_for_queue(probe_action: Any) -> list[Any]:
    if isinstance(probe_action, str):
        return [probe_action]
    if isinstance(probe_action, dict):
        if isinstance(probe_action.get("sequence"), list):
            return list(probe_action["sequence"])
        if isinstance(probe_action.get("action"), str):
            return [probe_action["action"]]
    return [probe_action]


def _initial_phase_for_mode(mode: str | None) -> PhaseState:
    if not mode:
        return PhaseState.EPISTEMIC
    return MODE_TO_PHASE.get(mode.lower(), PhaseState.EPISTEMIC)


def evaluate_bootstrap_phase(
    item: QueueItem,
    observation: ObservationSnapshot,
    belief: Any,
    step_budget: int = DEFAULT_STEP_BUDGET,
) -> tuple[str, str, str, float]:
    tested_actions = ordered_tested_actions(item.actions, observation.action_history)
    phase_ledger = belief.model_copy(deep=True)
    phase_ledger.action_semantics = {
        str(action): belief.action_semantics.get(
            str(action),
            [f"{action} was present in the executed prefix."],
        )
        for action in tested_actions
    }

    evaluated_step = max(observation.step_index, len(tested_actions) - 1, 0)
    budget_remaining = max(
        0.0,
        min(1.0, (step_budget - evaluated_step) / max(step_budget, 1)),
    )
    manager = PhaseManager(initial_phase=_initial_phase_for_mode(item.expected_mode))
    phase = manager.evaluate_transition(
        belief_ledger=phase_ledger,
        surprise_history=[],
        step=evaluated_step,
        budget_remaining=budget_remaining,
        levels_completed=observation.levels_completed,
    )
    guidance = exploration_guidance(phase, budget_remaining)
    reason = (
        manager.history[-1].reason
        if manager.history
        else f"Phase remained {phase.name} after bootstrap evaluation."
    )
    return phase.name.lower(), guidance, reason, budget_remaining


def select_next_probe(
    observation: ObservationSnapshot,
    belief: Any,
    prior_actions: list[Any],
    step_budget: int = DEFAULT_STEP_BUDGET,
) -> tuple[Any, str]:
    tested_actions = ordered_tested_actions(prior_actions, observation.action_history)
    probe_history = build_probe_history(tested_actions, observation.step_index)

    try:
        probe = design_next_probe(
            belief_ledger=belief,
            available_actions=observation.available_actions,
            step_budget=step_budget,
            tested_actions={str(action) for action in tested_actions},
            grid_rows=observation.grid_rows,
            grid_cols=observation.grid_cols,
            current_step=observation.step_index,
            probe_history=probe_history,
        )
        return probe, "experiment_designer"
    except Exception:
        fallback = suggest_next_probe(observation, belief)
        return fallback, "bootstrap_reasoner_fallback"


def derive_followup_item(
    item: QueueItem,
    episode_id: str,
    probe_action: Any,
    probe_rationale: str,
    expected_outcome: str,
    mode: str,
    probe_family: str,
    expected_information_gain: float | None,
) -> QueueItem:
    appended_actions = expand_probe_action_for_queue(probe_action)
    return QueueItem(
        game_id=item.game_id,
        actions=[*item.actions, *appended_actions],
        motif_names=item.motif_names,
        tags=sorted(set([*item.tags, "followup"])),
        notes=[
            *item.notes,
            f"Derived from episode {episode_id}.",
            f"Suggested probe: {probe_action}.",
            probe_rationale,
        ],
        queue_id=f"{item.queue_id or item.game_id}-d{item.depth + 1}",
        depth=item.depth + 1,
        expected_mode=mode,
        goal_hint=expected_outcome,
        probe_family=probe_family,
        expected_information_gain=expected_information_gain,
        parent_episode_id=episode_id,
    )


def run_queue_item(
    item: QueueItem,
    output_root: Path,
    python_bin: str,
    harness_path: Path,
    manifest_path: Path,
    followup_queue_path: Path | None = None,
    max_followup_depth: int = 0,
    dry_run: bool = False,
    solver_wrapper_path: Path = DEFAULT_SOLVER_WRAPPER,
) -> dict[str, Any]:
    if item.runner == "solve_loop":
        result_json_path = output_root / f"{item.queue_id or item.game_id}-solve-result.json"
        command = build_solver_command(
            python_bin=python_bin,
            solver_wrapper_path=solver_wrapper_path,
            item=item,
            output_root=output_root,
            result_json_path=result_json_path,
        )
        manifest_entry: dict[str, Any] = {
            "queue_id": item.queue_id,
            "game_id": item.game_id,
            "status": "planned" if dry_run else "started",
            "tags": item.tags,
            "motif_names": item.motif_names,
            "depth": item.depth,
            "expected_mode": item.expected_mode,
            "expected_information_gain": item.expected_information_gain,
            "goal_hint": item.goal_hint,
            "probe_family": item.probe_family,
            "parent_episode_id": item.parent_episode_id,
            "actions": item.actions,
            "runner": item.runner,
            "max_steps": item.max_steps,
            "llm_model": item.llm_model,
            "llm_memory_window": item.llm_memory_window,
            "episode_root": None,
            "observation_path": None,
            "command": command,
        }
        append_manifest(manifest_path, manifest_entry)

        if dry_run:
            return manifest_entry

        completed = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=build_runtime_env(),
        )
        if completed.returncode != 0 or not result_json_path.exists():
            failure_payload = {
                **manifest_entry,
                "status": "failed",
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
            append_manifest(manifest_path, failure_payload)
            return failure_payload

        solver_result = json.loads(result_json_path.read_text(encoding="utf-8"))
        success_payload = {
            **manifest_entry,
            "status": "completed",
            "runner": "solve_loop",
            "episode_id": solver_result.get("episode_id"),
            "episode_root": solver_result.get("episode_root"),
            "trace_path": solver_result.get("trace_path"),
            "episode_json_path": solver_result.get("episode_json_path"),
            "levels_completed": solver_result.get("levels_completed"),
            "total_steps": solver_result.get("total_steps"),
            "final_state": solver_result.get("final_state"),
            "phase_transitions": solver_result.get("phase_transitions"),
            "world_model_summary": solver_result.get("world_model_summary"),
            "trajectory_length": solver_result.get("trajectory_length"),
            "llm_used": solver_result.get("llm_used"),
            "resolved_llm_model": solver_result.get("llm_model"),
            "resolved_llm_memory_window": solver_result.get("llm_memory_window"),
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
            "followup_emitted": False,
            "followup_queue_path": None,
            "followup_item": None,
        }
        append_manifest(manifest_path, success_payload)
        return success_payload

    store = EpisodeMemoryStore.create(
        output_root,
        game_id=item.game_id,
        tags=item.tags,
        notes=item.notes,
    )
    observation_path = store.step_path(0, "observation")
    command = build_harness_command(
        python_bin=python_bin,
        harness_path=harness_path,
        item=item,
        observation_path=observation_path,
    )

    manifest_entry: dict[str, Any] = {
        "episode_id": store.metadata.episode_id,
        "queue_id": item.queue_id,
        "game_id": item.game_id,
        "status": "planned" if dry_run else "started",
        "tags": item.tags,
        "motif_names": item.motif_names,
        "depth": item.depth,
        "expected_mode": item.expected_mode,
        "expected_information_gain": item.expected_information_gain,
        "goal_hint": item.goal_hint,
        "probe_family": item.probe_family,
        "parent_episode_id": item.parent_episode_id,
        "actions": item.actions,
        "runner": item.runner,
        "max_steps": item.max_steps,
        "episode_root": str(store.root),
        "observation_path": str(observation_path),
        "command": command,
    }
    append_manifest(manifest_path, manifest_entry)

    if dry_run:
        return manifest_entry

    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=build_runtime_env(),
    )

    if completed.returncode != 0 or not observation_path.exists():
        failure_payload = {
            **manifest_entry,
            "status": "failed",
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
        append_manifest(manifest_path, failure_payload)
        return failure_payload

    observation = ObservationSnapshot.model_validate_json(
        observation_path.read_text(encoding="utf-8")
    )
    belief = build_bootstrap_ledger(
        store.metadata.episode_id,
        observation,
        seeded_names=item.motif_names,
    )
    belief.notes.extend(item.notes)
    resolved_mode, phase_guidance, phase_reason, budget_remaining = evaluate_bootstrap_phase(
        item=item,
        observation=observation,
        belief=belief,
    )
    belief.mode = resolved_mode
    belief.notes.append(f"Phase evaluation: {phase_reason}")
    belief.notes.append(phase_guidance)
    probe, probe_selector = select_next_probe(
        observation=observation,
        belief=belief,
        prior_actions=item.actions,
    )
    decision = DecisionRecord(
        episode_id=store.metadata.episode_id,
        game_id=item.game_id,
        step_index=observation.step_index,
        mode=resolved_mode,
        chosen_action=item.actions[-1] if item.actions else "RESET",
        rationale=summarize_actions(item.actions),
        expected_outcome="Structured bootstrap run for unattended supervisor.",
        expected_information_gain=item.expected_information_gain,
        next_probe_action=probe.action,
        next_probe_rationale=probe.rationale,
        next_probe_expected_outcome=probe.expected_outcome,
        next_probe_expected_information_gain=probe.expected_information_gain,
        notes=[
            "Bootstrapped by agentic_supervisor.py",
            "No LLM decision was made yet; this is a seed episode.",
            "Belief ledger was enriched by heuristic motif/goal/action-semantic inference.",
            f"Phase guidance: {phase_guidance}",
            f"Phase evaluation: {phase_reason}",
            f"Next probe selected by {probe_selector}.",
        ],
    )
    store.write_belief(belief)
    store.write_decision(decision)

    curator = TrajectoryCurator()
    trace = curator.curate(
        observation=observation,
        belief=belief,
        decision=decision,
        prediction=f"Bootstrap observation capture; next probe candidate is {probe.action}",
        actual_diff=observation.diff_summary,
        surprise=None,
        dynamics_revision="Bootstrap heuristics only",
    )
    store.append_trace(trace)

    followup_payload: dict[str, Any] | None = None
    if (
        followup_queue_path is not None
        and item.depth < max_followup_depth
        and probe.action is not None
    ):
        followup_item = derive_followup_item(
            item=item,
            episode_id=store.metadata.episode_id,
            probe_action=probe.action,
            probe_rationale=probe.rationale,
            expected_outcome=probe.expected_outcome,
            mode=belief.mode,
            probe_family="experiment-designer-followup"
            if probe_selector == "experiment_designer"
            else "bootstrap-followup",
            expected_information_gain=probe.expected_information_gain,
        )
        followup_payload = followup_item.to_dict()
        append_queue_item(followup_queue_path, followup_payload)

    success_payload = {
        **manifest_entry,
        "status": "completed",
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
        "belief_path": str(store.step_path(observation.step_index, "belief")),
        "decision_path": str(store.step_path(observation.step_index, "decision")),
        "trace_path": str(store.trace_path),
        "resolved_mode": resolved_mode,
        "phase_transition_reason": phase_reason,
        "budget_remaining": round(budget_remaining, 3),
        "exploration_guidance": phase_guidance,
        "next_probe": {
            "action": probe.action,
            "rationale": probe.rationale,
            "expected_information_gain": probe.expected_information_gain,
            "expected_outcome": probe.expected_outcome,
        },
        "next_probe_selector": probe_selector,
        "followup_emitted": followup_payload is not None,
        "followup_queue_path": str(followup_queue_path) if followup_payload else None,
        "followup_item": followup_payload,
    }
    append_manifest(manifest_path, success_payload)
    return success_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a JSONL work queue into structured ARC-AGI-3 episodes."
    )
    parser.add_argument("--queue", required=True, help="Path to queue JSONL file.")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Directory for structured episode outputs.",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Manifest JSONL that records queue execution.",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used to launch harness.py",
    )
    parser.add_argument(
        "--harness-path",
        default=str(DEFAULT_HARNESS),
        help="Path to harness.py",
    )
    parser.add_argument(
        "--solver-wrapper-path",
        default=str(DEFAULT_SOLVER_WRAPPER),
        help="Path to run_agentic_solver_job.py",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Optional cap on number of queue items to run.",
    )
    parser.add_argument(
        "--followup-queue",
        default=None,
        help="Optional JSONL path where suggested follow-up probes are appended.",
    )
    parser.add_argument(
        "--max-followup-depth",
        type=int,
        default=0,
        help="Emit follow-up queue items only while item.depth is below this value.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only plan queue execution without launching harness.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queue_path = Path(args.queue)
    output_root = Path(args.output_root)
    manifest_path = Path(args.manifest)
    harness_path = Path(args.harness_path)
    solver_wrapper_path = Path(args.solver_wrapper_path)
    followup_queue_path = Path(args.followup_queue) if args.followup_queue else None

    items = load_queue(queue_path)
    if args.max_items is not None:
        items = items[: args.max_items]

    if not items:
        raise SystemExit("Queue is empty.")

    results: list[dict[str, Any]] = []
    for item in items:
        result = run_queue_item(
            item=item,
            output_root=output_root,
            python_bin=args.python_bin,
            harness_path=harness_path,
            manifest_path=manifest_path,
            followup_queue_path=followup_queue_path,
            max_followup_depth=args.max_followup_depth,
            dry_run=args.dry_run,
            solver_wrapper_path=solver_wrapper_path,
        )
        results.append(result)
        status = result["status"]
        print(f"[{status}] {item.game_id} -> {result['episode_root']}")

    completed = sum(1 for result in results if result["status"] == "completed")
    failed = sum(1 for result in results if result["status"] == "failed")
    planned = sum(1 for result in results if result["status"] == "planned")
    print(
        f"Summary: total={len(results)} completed={completed} failed={failed} planned={planned}"
    )


if __name__ == "__main__":
    main()
