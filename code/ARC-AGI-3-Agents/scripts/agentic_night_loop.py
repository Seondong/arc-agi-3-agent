# [Mar 30] Created by SD with GPT-5.4.

"""Bounded night orchestrator for unattended ARC-AGI-3 agentic runs.

This script sits one layer above ``agentic_supervisor.py``.
It repeatedly:
1. Selects a deduplicated batch from a pending queue
2. Runs the supervisor on that batch
3. Collects follow-up probe suggestions
4. Requeues bounded follow-ups for the next round
5. Persists run-level summaries and seen signatures

The goal is still not full autonomy. The goal is to safely stretch the outer
loop from "one bootstrap episode" into "several rounds of bounded overnight
probe/refinement" without colliding with solver-specific work.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agentic_queue_policy import (
    build_game_histories,
    queue_signature,
    select_policy_batch,
)
from scripts.agentic_trace_enricher import enrich_completed_manifest_rows
from scripts.agentic_supervisor import QueueItem, load_queue


DEFAULT_RUN_ROOT = REPO_ROOT / "artifacts" / "agentic_night_runs"
DEFAULT_SUPERVISOR = Path(__file__).resolve().with_name("agentic_supervisor.py")
DEFAULT_SOLVER_WRAPPER = Path(__file__).resolve().with_name("run_agentic_solver_job.py")


def write_queue(queue_path: Path, items: list[QueueItem]) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item.to_dict(), ensure_ascii=False))
            handle.write("\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def save_seen_signatures(path: Path, signatures: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sorted(signatures), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_seen_signatures(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def append_round_trace(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def summarize_manifest_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "completed": sum(1 for row in rows if row.get("status") == "completed"),
        "failed": sum(1 for row in rows if row.get("status") == "failed"),
        "planned": sum(1 for row in rows if row.get("status") == "planned"),
        "started": sum(1 for row in rows if row.get("status") == "started"),
    }


def load_manifest_history(rounds_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not rounds_root.exists():
        return rows
    for manifest_path in sorted(rounds_root.glob("round_*/manifest.jsonl")):
        rows.extend(load_jsonl(manifest_path))
    return rows


def build_supervisor_command(
    python_bin: str,
    supervisor_path: Path,
    queue_path: Path,
    round_root: Path,
    harness_path: Path,
    solver_wrapper_path: Path,
    max_followup_depth: int,
    dry_run: bool,
) -> list[str]:
    command = [
        python_bin,
        str(supervisor_path),
        "--queue",
        str(queue_path),
        "--output-root",
        str(round_root / "episodes"),
        "--manifest",
        str(round_root / "manifest.jsonl"),
        "--followup-queue",
        str(round_root / "followups.jsonl"),
        "--max-followup-depth",
        str(max_followup_depth),
        "--python-bin",
        python_bin,
        "--harness-path",
        str(harness_path),
        "--solver-wrapper-path",
        str(solver_wrapper_path),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def run_supervisor_round(
    python_bin: str,
    supervisor_path: Path,
    queue_path: Path,
    round_root: Path,
    harness_path: Path,
    solver_wrapper_path: Path,
    max_followup_depth: int,
    dry_run: bool,
) -> subprocess.CompletedProcess[str]:
    command = build_supervisor_command(
        python_bin=python_bin,
        supervisor_path=supervisor_path,
        queue_path=queue_path,
        round_root=round_root,
        harness_path=harness_path,
        solver_wrapper_path=solver_wrapper_path,
        max_followup_depth=max_followup_depth,
        dry_run=dry_run,
    )
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded multi-round unattended ARC-AGI-3 loop."
    )
    parser.add_argument("--seed-queue", required=True, help="Initial queue JSONL path.")
    parser.add_argument(
        "--run-root",
        default=str(DEFAULT_RUN_ROOT),
        help="Directory where the orchestrated night run is stored.",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used to launch the supervisor.",
    )
    parser.add_argument(
        "--supervisor-path",
        default=str(DEFAULT_SUPERVISOR),
        help="Path to agentic_supervisor.py.",
    )
    parser.add_argument(
        "--harness-path",
        default=str(REPO_ROOT / "harness.py"),
        help="Path to harness.py.",
    )
    parser.add_argument(
        "--solver-wrapper-path",
        default=str(DEFAULT_SOLVER_WRAPPER),
        help="Path to run_agentic_solver_job.py.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="Maximum number of rounds to execute.",
    )
    parser.add_argument(
        "--items-per-round",
        type=int,
        default=2,
        help="Maximum number of queue items to execute per round.",
    )
    parser.add_argument(
        "--max-followup-depth",
        type=int,
        default=1,
        help="Maximum probe depth that the supervisor is allowed to emit.",
    )
    parser.add_argument(
        "--max-items-per-game",
        type=int,
        default=1,
        help="Maximum number of selected queue items per game in one round.",
    )
    parser.add_argument(
        "--stagnation-threshold",
        type=int,
        default=2,
        help="Apply stagnation penalties after this many non-progress episodes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run orchestrator planning without executing harness workloads.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_root = Path(args.run_root)
    rounds_root = run_root / "rounds"
    seen_path = run_root / "seen_signatures.json"
    trace_path = run_root / "night_trace.jsonl"
    summary_path = run_root / "night_summary.json"

    pending = load_queue(Path(args.seed_queue))
    seen_signatures = load_seen_signatures(seen_path)
    manifest_history_rows = load_manifest_history(rounds_root)

    total_completed = 0
    total_failed = 0
    executed_rounds = 0
    stop_reason = "round_limit_reached"

    for round_index in range(args.rounds):
        histories = build_game_histories(manifest_history_rows)
        batch, remainder, assessments = select_policy_batch(
            pending,
            seen_signatures,
            histories=histories,
            batch_size=args.items_per_round,
            max_items_per_game=args.max_items_per_game,
            stagnation_threshold=args.stagnation_threshold,
        )
        if not batch:
            stop_reason = "queue_exhausted_or_deduped"
            break

        round_root = rounds_root / f"round_{round_index:03d}"
        round_queue_path = round_root / "queue.jsonl"
        write_queue(round_queue_path, batch)

        result = run_supervisor_round(
            python_bin=args.python_bin,
            supervisor_path=Path(args.supervisor_path),
            queue_path=round_queue_path,
            round_root=round_root,
            harness_path=Path(args.harness_path),
            solver_wrapper_path=Path(args.solver_wrapper_path),
            max_followup_depth=args.max_followup_depth,
            dry_run=args.dry_run,
        )

        manifest_rows = load_jsonl(round_root / "manifest.jsonl")
        manifest_history_rows.extend(manifest_rows)
        enriched_metrics = enrich_completed_manifest_rows(
            current_rows=manifest_rows,
            all_rows=manifest_history_rows,
        )
        manifest_counts = summarize_manifest_rows(manifest_rows)
        total_completed += manifest_counts["completed"]
        total_failed += manifest_counts["failed"]

        followup_rows = load_jsonl(round_root / "followups.jsonl")
        followups = [QueueItem.from_dict(row) for row in followup_rows]

        round_trace = {
            "round_index": round_index,
            "batch_size": len(batch),
            "remainder_size": len(remainder),
            "followups_emitted": len(followups),
            "returncode": result.returncode,
            "manifest_counts": manifest_counts,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
            "selected_items": [item.to_dict() for item in batch],
            "queue_assessments": [assessment.to_dict() for assessment in assessments],
            "enriched_episode_metrics": enriched_metrics,
        }
        append_round_trace(trace_path, round_trace)

        for item in batch:
            seen_signatures.add(queue_signature(item))
        save_seen_signatures(seen_path, seen_signatures)

        pending = [*remainder, *followups]
        executed_rounds += 1

        if result.returncode != 0:
            stop_reason = "supervisor_failed"
            break
        if not pending:
            stop_reason = "no_followups_remaining"
            break

    summary = {
        "rounds_requested": args.rounds,
        "rounds_executed": executed_rounds,
        "items_per_round": args.items_per_round,
        "max_followup_depth": args.max_followup_depth,
        "max_items_per_game": args.max_items_per_game,
        "stagnation_threshold": args.stagnation_threshold,
        "dry_run": args.dry_run,
        "stop_reason": stop_reason,
        "total_completed": total_completed,
        "total_failed": total_failed,
        "pending_after_stop": len(pending),
        "seen_signature_count": len(seen_signatures),
        "run_root": str(run_root),
    }
    run_root.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        "Night loop summary: "
        f"rounds={executed_rounds} completed={total_completed} "
        f"failed={total_failed} stop_reason={stop_reason}"
    )


if __name__ == "__main__":
    main()
