"""[Mar 29] Created by SD with GPT-5.4.

Build small-policy and SFT datasets from ARC-AGI-3 trajectory logs.

This script converts collected JSONL trajectories into:
1. A compact supervised classification dataset for a lightweight policy prior.
2. An instruction-style SFT dataset for optional small-LLM fine-tuning.

The output is intentionally compact so small models can learn from summary
features rather than full 64x64 grids.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any


ACTION_VOCAB = ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6"]
ACTION_TO_ID = {name: idx for idx, name in enumerate(ACTION_VOCAB)}


def normalize_objects(objects: list[dict[str, Any]], limit: int = 8) -> list[dict[str, int]]:
    ranked = sorted(
        objects,
        key=lambda obj: (
            -int(obj.get("count", 0)),
            int(obj.get("value", 0)),
            int(obj.get("r_min", 0)),
            int(obj.get("c_min", 0)),
        ),
    )
    compact: list[dict[str, int]] = []
    for obj in ranked[:limit]:
        compact.append(
            {
                "value": int(obj.get("value", 0)),
                "count": int(obj.get("count", 0)),
                "r_min": int(obj.get("r_min", 0)),
                "r_max": int(obj.get("r_max", 0)),
                "c_min": int(obj.get("c_min", 0)),
                "c_max": int(obj.get("c_max", 0)),
            }
        )
    return compact


def summarize_objects(objects: list[dict[str, int]]) -> str:
    if not objects:
        return "none"
    parts = []
    for obj in objects:
        parts.append(
            "v{value}:n{count}@r{r_min}-{r_max}c{c_min}-{c_max}".format(**obj)
        )
    return "; ".join(parts)


def compute_quality(record: dict[str, Any]) -> float:
    diff_cells = int(record.get("diff_cells", 0) or 0)
    levels_before = int(record.get("levels_before", 0) or 0)
    levels_after = int(record.get("levels_after", 0) or 0)
    state_after = str(record.get("state_after", ""))

    quality = 0.2
    if diff_cells > 0:
        quality += min(0.5, math.log1p(diff_cells) / 10.0)
    if levels_after > levels_before:
        quality += 1.5
    if state_after == "WIN":
        quality += 1.0
    return round(quality, 4)


def action_history(records: list[dict[str, Any]], idx: int, window: int = 4) -> list[str]:
    start = max(0, idx - window)
    return [str(records[j].get("action", "UNK")) for j in range(start, idx)]


def build_policy_example(
    game: str,
    record: dict[str, Any],
    history: list[str],
) -> dict[str, Any] | None:
    action = str(record.get("action", ""))
    if action not in ACTION_TO_ID:
        return None

    available_ids = [int(x) for x in record.get("available_actions", [])]
    available_mask = [1 if (i + 1) in available_ids else 0 for i in range(6)]
    objects = normalize_objects(list(record.get("objects", [])))
    action_args = dict(record.get("action_args", {}) or {})

    coord = None
    if action == "ACTION6":
        coord = {
            "x": int(action_args.get("x", 0)),
            "y": int(action_args.get("y", 0)),
        }

    return {
        "game": game,
        "step": int(record.get("step", 0)),
        "level": int(record.get("level", 0)),
        "available_mask": available_mask,
        "diff_cells": int(record.get("diff_cells", 0) or 0),
        "levels_before": int(record.get("levels_before", 0) or 0),
        "levels_after": int(record.get("levels_after", 0) or 0),
        "state_after": str(record.get("state_after", "NOT_FINISHED")),
        "history": history,
        "objects": objects,
        "action": action,
        "action_id": ACTION_TO_ID[action],
        "coord": coord,
        "quality": compute_quality(record),
    }


def build_sft_example(
    game: str,
    record: dict[str, Any],
    history: list[str],
) -> dict[str, Any] | None:
    action = str(record.get("action", ""))
    if action not in ACTION_TO_ID:
        return None

    objects = normalize_objects(list(record.get("objects", [])))
    available = ", ".join(f"ACTION{x}" for x in record.get("available_actions", []))
    history_text = ", ".join(history) if history else "none"
    reasoning = str(record.get("reasoning", "")).strip() or "(not provided)"
    action_args = dict(record.get("action_args", {}) or {})

    if action == "ACTION6":
        answer = f"{action} x={int(action_args.get('x', 0))} y={int(action_args.get('y', 0))}"
    else:
        answer = action

    prompt = (
        f"Game: {game}\n"
        f"Step: {int(record.get('step', 0))}\n"
        f"Level: {int(record.get('level', 0))}\n"
        f"Available actions: {available or 'none'}\n"
        f"Recent actions: {history_text}\n"
        f"Diff cells after previous step: {int(record.get('diff_cells', 0) or 0)}\n"
        f"Objects: {summarize_objects(objects)}\n\n"
        "Choose the next action. Reply with either ACTION1-5 or ACTION6 x=<int> y=<int>."
    )

    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a compact ARC-AGI-3 action prior. "
                    "Prefer short action outputs and avoid explanations."
                ),
            },
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": answer},
        ],
        "metadata": {
            "game": game,
            "quality": compute_quality(record),
            "reasoning": reasoning,
            "state_after": str(record.get("state_after", "NOT_FINISHED")),
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data"),
        help="Directory with *_trajectory.jsonl files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/policy_data"),
        help="Directory for train/valid outputs.",
    )
    parser.add_argument(
        "--valid-ratio",
        type=float,
        default=0.2,
        help="Validation split ratio.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed for shuffling.",
    )
    args = parser.parse_args()

    rng = random.Random(args.seed)
    policy_rows: list[dict[str, Any]] = []
    sft_rows: list[dict[str, Any]] = []

    files = sorted(args.input_dir.glob("*_trajectory.jsonl"))
    if not files:
        raise SystemExit(f"No trajectory files found in {args.input_dir}")

    for path in files:
        game = path.stem.replace("_trajectory", "")
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for idx, record in enumerate(records):
            history = action_history(records, idx)
            policy_example = build_policy_example(game, record, history)
            if policy_example is not None:
                policy_rows.append(policy_example)
            sft_example = build_sft_example(game, record, history)
            if sft_example is not None:
                sft_rows.append(sft_example)

    rng.shuffle(policy_rows)
    rng.shuffle(sft_rows)

    policy_cut = max(1, int(len(policy_rows) * (1.0 - args.valid_ratio)))
    sft_cut = max(1, int(len(sft_rows) * (1.0 - args.valid_ratio)))

    write_jsonl(args.output_dir / "policy_train.jsonl", policy_rows[:policy_cut])
    write_jsonl(args.output_dir / "policy_valid.jsonl", policy_rows[policy_cut:])
    write_jsonl(args.output_dir / "sft_train.jsonl", sft_rows[:sft_cut])
    write_jsonl(args.output_dir / "sft_valid.jsonl", sft_rows[sft_cut:])

    action_counter = Counter(row["action"] for row in policy_rows)
    metadata = {
        "input_dir": str(args.input_dir),
        "num_policy_examples": len(policy_rows),
        "num_sft_examples": len(sft_rows),
        "action_distribution": dict(action_counter),
        "valid_ratio": args.valid_ratio,
        "seed": args.seed,
    }
    (args.output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
