"""Brain — the pluggable author of world models.

The solve loop is model-agnostic. A `Brain` reads the recorded timeline (and,
after a failed certification, the pointed-bug counterexample) and returns a
`WorldModel`. Two implementations:

  - CallableBrain : returns a fixed, pre-authored model. Used for offline tests
    and as the interface a real coding-agent must ultimately satisfy.
  - ClaudeBrain   : the frontier seam. Builds a prompt from the timeline +
    counterexample, asks the driver model (Claude Opus, per our decision) to
    WRITE the reconstruct/step/render/is_goal code, execs it, and returns the
    resulting WorldModel. The network/exec wiring runs where a model + game
    files are available (the Mac / a GPU box); here it is a documented stub with
    the prompt builder implemented so the contract is real.
"""

from __future__ import annotations

from typing import Optional, Protocol

from .backtest import BacktestReport
from .core import Timeline, WorldModel


class Brain(Protocol):
    def propose(
        self,
        timeline: Timeline,
        prev: Optional[WorldModel],
        last_report: Optional[BacktestReport],
    ) -> WorldModel: ...


class CallableBrain:
    """A brain that always returns the same pre-authored model (version-bumped).

    Useful for tests and for pinning a hand-written reference simulator (e.g. the
    tu93 one) into the loop while the frontier author is being wired.
    """

    def __init__(self, model: WorldModel):
        self._model = model
        self._version = model.version

    def propose(
        self,
        timeline: Timeline,
        prev: Optional[WorldModel],
        last_report: Optional[BacktestReport],
    ) -> WorldModel:
        self._version += 1
        m = self._model
        return WorldModel(
            version=self._version,
            reconstruct=m.reconstruct,
            step=m.step,
            render=m.render,
            is_goal=m.is_goal,
            notes=m.notes,
            source_code=m.source_code,
            confidence=m.confidence,
            fingerprint=m.fingerprint,
        )


class ClaudeBrain:
    """Frontier seam: Claude Opus writes the world-model code.

    Wiring (done where model access exists):
      1. build_prompt(timeline, prev, last_report)  -> instruction string
      2. call the model -> Python source defining reconstruct/step/render/is_goal
      3. exec the source in a restricted namespace
      4. wrap the four callables in a WorldModel and return it

    Kept as a stub here so the offline test suite never needs network/model
    access; `build_prompt` is fully implemented because it is the real contract.
    """

    SYSTEM = (
        "You are a physicist playing an unknown grid game. Write the game's "
        "mechanism as an executable Python world model with EXACTLY these "
        "callables operating on a frame (2D list of ints):\n"
        "  reconstruct(frame) -> state\n"
        "  step(state, action) -> (new_state, status)   # status in "
        "{'RUNNING','LEVEL_COMPLETED','GAME_OVER'}\n"
        "  render(state) -> frame\n"
        "  is_goal(state) -> bool\n"
        "Infer a compact, general rule system from the recorded history. Do NOT "
        "hardcode level layouts. Your model is only acceptable if render() "
        "reproduces every recorded frame EXACTLY (it will be backtested)."
    )

    def __init__(self, model_id: str = "claude-opus-4-8"):
        self.model_id = model_id

    def build_prompt(
        self,
        timeline: Timeline,
        prev: Optional[WorldModel],
        last_report: Optional[BacktestReport],
    ) -> str:
        lines: list[str] = []
        lines.append(f"Initial frame ({len(timeline.initial_frame)} rows):")
        lines.append(_render_frame_text(timeline.initial_frame))
        lines.append("")
        lines.append(f"Recorded transitions ({len(timeline)}):")
        for tr in timeline.transitions:
            lines.append(
                f"  step {tr.step_index}: {tr.action} -> status={tr.status}, "
                f"{tr.changed_cells} cells changed"
            )
        if prev is not None and prev.source_code:
            lines.append("")
            lines.append("Your previous world model (revise it, do not restart):")
            lines.append(prev.source_code)
        if last_report is not None and last_report.first_mismatch is not None:
            mm = last_report.first_mismatch
            lines.append("")
            lines.append("BACKTEST COUNTEREXAMPLE — fix exactly this:")
            lines.append("  " + mm.summary())
            lines.append("  predicted frame:")
            lines.append(_render_frame_text(mm.predicted_frame, indent=4))
            lines.append("  actual frame:")
            lines.append(_render_frame_text(mm.actual_frame, indent=4))
        return "\n".join(lines)

    def propose(
        self,
        timeline: Timeline,
        prev: Optional[WorldModel],
        last_report: Optional[BacktestReport],
    ) -> WorldModel:
        raise NotImplementedError(
            "ClaudeBrain.propose needs model access; wire the API call on a host "
            "with credentials. Use build_prompt() to see the instruction, and "
            "CallableBrain for offline tests."
        )


def _render_frame_text(frame, indent: int = 0) -> str:
    pad = " " * indent
    return "\n".join(pad + " ".join(f"{v:2d}" for v in row) for row in frame)
