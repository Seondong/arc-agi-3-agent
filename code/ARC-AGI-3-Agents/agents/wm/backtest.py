"""run_backtest — certify a world model against the full recorded history.

This is the organ the earlier framework lacked. `surprise_auditor` only checked
one prediction against one actual diff; here we replay the ENTIRE timeline
through the model and demand an exact match at every step, returning a *pointed
bug* (the first divergence, with predicted vs actual frames) when the model is
wrong. Only a model that backtests green may be trusted for free planning —
exactly the Schema `run_backtest` / Baseline1 `verify_world_model` contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .core import (
    Frame,
    Timeline,
    WorldModel,
    diff_cells,
    frames_equal,
    ignored_cells,
)


@dataclass
class Mismatch:
    """A pointed bug: the first recorded transition the model fails to reproduce."""

    step_index: int
    action: str
    frame_mismatch: bool
    status_mismatch: bool
    predicted_status: str
    actual_status: str
    changed_cells: int  # how many cells the prediction got wrong
    predicted_frame: Frame
    actual_frame: Frame

    def summary(self) -> str:
        bits = []
        if self.status_mismatch:
            bits.append(
                f"status predicted={self.predicted_status} actual={self.actual_status}"
            )
        if self.frame_mismatch:
            bits.append(f"{self.changed_cells} cell(s) mispredicted")
        detail = "; ".join(bits) or "no divergence"
        return f"pointed bug at step {self.step_index} after {self.action}: {detail}"


@dataclass
class BacktestReport:
    """Result of replaying a model over the whole timeline."""

    total: int
    matched: int
    ok: bool
    first_mismatch: Optional[Mismatch] = None
    error: Optional[str] = None  # model raised while simulating (also a failure)

    def summary(self) -> str:
        if self.error is not None:
            return f"backtest ERROR after {self.matched}/{self.total}: {self.error}"
        if self.ok:
            return f"backtest {self.matched}/{self.total} exact"
        assert self.first_mismatch is not None
        return (
            f"backtest {self.matched}/{self.total} then "
            f"{self.first_mismatch.summary()}"
        )


def run_backtest(model: WorldModel, timeline: Timeline) -> BacktestReport:
    """Replay `timeline` through `model`; return exact-match or the first bug.

    Semantics: reconstruct the initial state from the first frame, then apply
    each recorded action with `model.step`, rendering after each and comparing
    to the recorded frame AND status. Stops at the first divergence so the caller
    gets a single, actionable counterexample to feed back to the brain.
    """
    total = len(timeline)
    if total == 0:
        # Nothing recorded yet — a model can't be certified, but it isn't wrong.
        return BacktestReport(total=0, matched=0, ok=True)

    try:
        state = model.reconstruct(timeline.initial_frame)
    except Exception as exc:  # noqa: BLE001 - a broken reconstruct is a failed backtest
        return BacktestReport(total=total, matched=0, ok=False,
                              error=f"reconstruct raised: {exc!r}")

    matched = 0
    for tr in timeline.transitions:
        try:
            pred_state, pred_status = model.step(state, tr.action)
            pred_frame = model.render(pred_state)
        except Exception as exc:  # noqa: BLE001
            return BacktestReport(
                total=total, matched=matched, ok=False,
                error=f"step/render raised at step {tr.step_index}: {exc!r}",
            )

        # A death often comes back with no frame at all. There is then no ground
        # truth to compare against, so such a step can only certify the status —
        # scoring the render against a stale frame would invent a failure.
        if tr.after_frame is None:
            ignore, frame_bad = None, False
        else:
            ignore = ignored_cells(model, tr.after_frame)
            frame_bad = not frames_equal(pred_frame, tr.after_frame, ignore)
        status_bad = pred_status != tr.status
        if frame_bad or status_bad:
            return BacktestReport(
                total=total,
                matched=matched,
                ok=False,
                first_mismatch=Mismatch(
                    step_index=tr.step_index,
                    action=str(tr.action),
                    frame_mismatch=frame_bad,
                    status_mismatch=status_bad,
                    predicted_status=pred_status,
                    actual_status=tr.status,
                    # No recorded frame means nothing to count; a status-only
                    # mismatch still has to be reportable.
                    changed_cells=(0 if tr.after_frame is None
                                   else diff_cells(pred_frame, tr.after_frame, ignore)),
                    predicted_frame=pred_frame,
                    actual_frame=tr.after_frame,
                ),
            )

        matched += 1
        state = pred_state

    return BacktestReport(total=total, matched=matched, ok=True)


def reconstruct_current_state(model: WorldModel, timeline: Timeline):
    """Advance a (presumed-certified) model to the timeline's current state.

    Reconstructs the initial state and replays every recorded action through
    `model.step`. Only meaningful when `run_backtest` is green; used to seed
    planning from where the agent actually is.
    """
    state = model.reconstruct(timeline.initial_frame)
    for tr in timeline.transitions:
        state, _ = model.step(state, tr.action)
    return state
