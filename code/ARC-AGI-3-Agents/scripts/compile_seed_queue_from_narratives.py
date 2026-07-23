# [Mar 30] Created by SD with GPT-5.4.

"""Compile harness narratives into seed queues and probe catalogs."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


CODE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_NARRATIVES_DIR = PROJECT_ROOT / "docs" / "harness-narratives"
DEFAULT_OUTPUT_QUEUE = CODE_ROOT / "artifacts" / "agentic_seed_queue_from_narratives.jsonl"
DEFAULT_OUTPUT_SUMMARY = CODE_ROOT / "artifacts" / "agentic_narrative_probe_catalog.json"

ACTION_RE = re.compile(r"\bACTION[1-7]\b")
MOTIF_BULLET_RE = re.compile(r"^\s*(?:-|\d+\.)\s+\*\*(.+?)\*\*")


@dataclass
class NarrativeExtraction:
    game_id: str
    source_path: str
    motif_names: list[str]
    candidate_actions: list[str]
    available_actions: list[str]
    queue_item: dict[str, object]


def normalize_motif_label(label: str) -> str:
    english = re.sub(r"\([^)]*\)", "", label)
    english = english.split("—", 1)[0]
    english = english.split("--", 1)[0]
    english = english.split("/", 1)[0]
    english = english.strip()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", english).strip("-").lower()
    return slug or "unknown-motif"


def unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def extract_motif_names(text: str, limit: int = 3) -> list[str]:
    lines = text.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        if "Motif 후보 분포" in line:
            start_index = index + 1
            break
    if start_index is None:
        return []

    motifs: list[str] = []
    for line in lines[start_index : start_index + 24]:
        match = MOTIF_BULLET_RE.match(line)
        if not match:
            continue
        motifs.append(normalize_motif_label(match.group(1)))

    return unique_in_order(motifs)[:limit]


def extract_candidate_actions(text: str, limit: int = 4) -> list[str]:
    lines = text.splitlines()
    candidates: list[str] = []
    in_experiment_area = False

    for line in lines:
        if "실험 계획" in line:
            in_experiment_area = True
            continue
        if in_experiment_area and line.startswith("## "):
            break
        if in_experiment_area and "실험" in line and "ACTION" in line:
            candidates.extend(ACTION_RE.findall(line))

    if not candidates:
        for line in lines[:140]:
            if "ACTION" in line:
                candidates.extend(ACTION_RE.findall(line))

    return unique_in_order(candidates)[:limit]


def extract_available_actions(text: str) -> list[str]:
    lines = text.splitlines()
    early_actions: list[str] = []
    for line in lines[:80]:
        if "ACTION" in line:
            early_actions.extend(ACTION_RE.findall(line))
    return unique_in_order(early_actions)


def build_queue_item(
    game_id: str,
    source_name: str,
    motif_names: list[str],
    candidate_actions: list[str],
) -> dict[str, object]:
    action_hint = ", ".join(candidate_actions) if candidate_actions else "none parsed"
    notes = [
        f"Compiled from {source_name}.",
        f"Candidate probes from narrative: {action_hint}.",
    ]
    goal_hint = (
        f"Bootstrap narrative-derived probe ordering; prioritize {candidate_actions[0]} first."
        if candidate_actions
        else "Bootstrap narrative-derived probe ordering."
    )
    return {
        "queue_id": f"q-{game_id}-seed",
        "game_id": game_id,
        "actions": ["RESET"],
        "motif_names": motif_names or ["bootstrap"],
        "tags": ["compiled", "nightly", "bootstrap", "narrative-seed"],
        "notes": notes,
        "expected_mode": "epistemic",
        "goal_hint": goal_hint,
        "probe_family": "narrative-seed",
    }


def extract_narrative(path: Path) -> NarrativeExtraction:
    text = path.read_text(encoding="utf-8")
    game_id = path.name.replace("-harness-narrative.md", "")
    motif_names = extract_motif_names(text)
    candidate_actions = extract_candidate_actions(text)
    available_actions = extract_available_actions(text)
    queue_item = build_queue_item(
        game_id=game_id,
        source_name=path.name,
        motif_names=motif_names,
        candidate_actions=candidate_actions,
    )
    return NarrativeExtraction(
        game_id=game_id,
        source_path=str(path),
        motif_names=motif_names,
        candidate_actions=candidate_actions,
        available_actions=available_actions,
        queue_item=queue_item,
    )


def write_queue(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def write_summary(path: Path, rows: list[NarrativeExtraction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "narrative_count": len(rows),
        "games": [asdict(row) for row in rows],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile harness narratives into a seed queue and probe catalog."
    )
    parser.add_argument(
        "--narratives-dir",
        default=str(DEFAULT_NARRATIVES_DIR),
        help="Directory containing *-harness-narrative.md files.",
    )
    parser.add_argument(
        "--output-queue",
        default=str(DEFAULT_OUTPUT_QUEUE),
        help="Output JSONL seed queue path.",
    )
    parser.add_argument(
        "--output-summary",
        default=str(DEFAULT_OUTPUT_SUMMARY),
        help="Output JSON summary path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    narratives_dir = Path(args.narratives_dir)
    narrative_paths = sorted(narratives_dir.glob("*-harness-narrative.md"))
    if not narrative_paths:
        raise SystemExit(f"No harness narratives found in {narratives_dir}")

    extracted = [extract_narrative(path) for path in narrative_paths]
    queue_rows = [row.queue_item for row in extracted]

    write_queue(Path(args.output_queue), queue_rows)
    write_summary(Path(args.output_summary), extracted)

    print(
        f"Compiled {len(extracted)} narratives -> "
        f"{args.output_queue} and {args.output_summary}"
    )


if __name__ == "__main__":
    main()
