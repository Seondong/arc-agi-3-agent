"""[Mar 30] Created by SD with GPT-5.4."""

import json

import pytest

from scripts.compile_seed_queue_from_narratives import (
    build_queue_item,
    extract_available_actions,
    extract_candidate_actions,
    extract_motif_names,
    normalize_motif_label,
    write_queue,
)


@pytest.mark.unit
class TestCompileSeedQueueFromNarratives:
    def test_normalize_motif_label(self):
        assert (
            normalize_motif_label("Click-Semantics / Coordinate Selection (좌표 선택)")
            == "click-semantics"
        )

    def test_extract_motif_names_and_actions(self):
        text = """
## 2단계: Motif 추정
**Motif 후보 분포**:
1. **Click-Semantics / Coordinate Selection (좌표 선택)**: 0.35 — 설명
2. **Navigation + Collection (수집)**: 0.25 — 설명

## 3단계: Epistemic Planning
**실험 계획**:
실험 1: ACTION1 1회 → diff 분석
실험 2: ACTION5 1회 → diff 분석
"""
        assert extract_motif_names(text)[:2] == [
            "click-semantics",
            "navigation-collection",
        ]
        assert extract_candidate_actions(text) == ["ACTION1", "ACTION5"]
        assert extract_available_actions(text) == ["ACTION1", "ACTION5"]

    def test_write_queue_serializes_rows(self, tmp_path):
        queue_path = tmp_path / "queue.jsonl"
        row = build_queue_item(
            game_id="sk48",
            source_name="sk48-harness-narrative.md",
            motif_names=["threading", "assembly"],
            candidate_actions=["ACTION1", "ACTION4"],
        )

        write_queue(queue_path, [row])

        lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["game_id"] == "sk48"
        assert payload["actions"] == ["RESET"]
        assert payload["motif_names"] == ["threading", "assembly"]
