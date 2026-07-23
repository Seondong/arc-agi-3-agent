"""Trace emission in the project's `data-logging-principles` schema.

Every step writes one JSONL record carrying the 6-stage reasoning chain
(OBSERVE -> INTERPRET -> HYPOTHESIZE -> PREDICT -> RESULT -> REVISE), the
pre/post-action pair, the world-model version + source, the backtest summary,
and the plan. This is what makes each episode double as distillation data — the
supervision is the belief/model *revision*, not the bare action.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .core import Action, Frame


@dataclass
class ReasoningChain:
    """The mandatory 6-stage chain (Principle 2). Empty stages say 'none'."""

    observe: str = "none"
    interpret: str = "none"
    hypothesize: str = "none"
    predict: str = "none"
    result: str = "none"
    revise: str = "none"


@dataclass
class TraceRecord:
    step_index: int
    phase: str                      # epistemic | instrumental | recovery
    # pre-action pair
    action: dict = field(default_factory=dict)
    predicted_status: Optional[str] = None
    confidence: float = 0.0
    # post-action pair
    actual_status: Optional[str] = None
    actual_changed_cells: int = 0
    prediction_match: Optional[bool] = None
    surprise: str = "none"
    # world-model provenance
    world_model_version: int = 0
    world_model_confidence: float = 0.0
    backtest: str = ""
    backtest_ok: bool = False
    plan: str = ""
    # narrative
    reasoning: ReasoningChain = field(default_factory=ReasoningChain)
    strategy_change: Optional[dict] = None
    rule_updates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class TraceWriter:
    """Append-only JSONL writer. One record per real step."""

    def __init__(self, path: Optional[str]):
        self.path = path
        self._records: list[dict] = []
        if path is not None:
            # truncate at episode start
            open(path, "w").close()

    def write(self, record: TraceRecord) -> None:
        d = record.to_dict()
        self._records.append(d)
        if self.path is not None:
            with open(self.path, "a") as f:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

    @property
    def records(self) -> list[dict]:
        return list(self._records)


def sparse_frame(frame: Frame, background: Optional[int] = None) -> dict:
    """Object-ish sparse encoding of a frame (Principle 7).

    Minimal, dependency-free: infer background as the most common value unless
    given, then list non-background cells grouped by value. Good enough to keep
    a compact state summary in the trace; a richer object segmenter can replace
    it later without changing the schema.
    """
    counts: dict[int, int] = {}
    for row in frame:
        for v in row:
            counts[v] = counts.get(v, 0) + 1
    if background is None and counts:
        background = max(counts, key=lambda k: counts[k])
    cells_by_value: dict[int, list[list[int]]] = {}
    for r, row in enumerate(frame):
        for c, v in enumerate(row):
            if v == background:
                continue
            cells_by_value.setdefault(v, []).append([r, c])
    return {
        "rows": len(frame),
        "cols": len(frame[0]) if frame else 0,
        "background": background,
        "cells_by_value": {str(k): v for k, v in cells_by_value.items()},
    }
