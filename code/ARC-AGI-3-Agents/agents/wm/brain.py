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

import re
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
        "reproduces every recorded frame EXACTLY (it will be backtested).\n"
        "If a small region (e.g. a step/energy counter or HUD bar) changes every "
        "step without carrying game logic and you cannot yet model it, you MAY "
        "additionally define `ignore(frame) -> list of (row, col)` returning that "
        "region's cells to exclude from verification. Prefer modelling it in "
        "render(); a non-empty ignore set is modelling debt, not a solution."
    )

    def __init__(
        self,
        model_id: str = "claude-opus-4-8",
        *,
        effort: str = "high",
        max_tokens: int = 32000,
    ):
        self.model_id = model_id
        self.effort = effort
        self.max_tokens = max_tokens
        self._client = None  # lazily constructed so offline tests need no SDK

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
        """Ask Opus to (re)write the world-model code, then exec it into callables.

        Streams the response (per the SDK guidance for large max_tokens) with
        adaptive thinking. The model returns a single ```python block defining
        reconstruct/step/render/is_goal; we exec it in a fresh namespace and wrap
        the callables in a WorldModel.
        """
        import anthropic  # lazy: offline tests (CallableBrain) need no SDK

        if self._client is None:
            self._client = anthropic.Anthropic()

        prompt = self.build_prompt(timeline, prev, last_report)
        with self._client.messages.stream(
            model=self.model_id,
            max_tokens=self.max_tokens,
            system=self.SYSTEM,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()

        text = "".join(b.text for b in message.content if b.type == "text")
        code = _extract_code(text)
        callables = _exec_world_model(code)
        return WorldModel(
            version=(prev.version + 1) if prev else 1,
            reconstruct=callables["reconstruct"],
            step=callables["step"],
            render=callables["render"],
            is_goal=callables["is_goal"],
            fingerprint=callables.get("fingerprint")
            or WorldModel.__dataclass_fields__["fingerprint"].default,
            ignore=callables.get("ignore"),
            notes=text.split("```")[0].strip()[:500],
            source_code=code,
            confidence=0.6,
        )


def _extract_code(text: str) -> str:
    """Pull the last ```python fenced block (or the whole text if unfenced)."""
    fences = re.findall(r"```(?:python)?\s*(.*?)```", text, re.S)
    if fences:
        return fences[-1].strip()
    return text.strip()


_REQUIRED = ("reconstruct", "step", "render", "is_goal")


def _exec_world_model(code: str) -> dict:
    """Exec brain-written code in a fresh namespace; return its callables.

    The model authors this code, so it runs on the host that holds the model
    credentials (the operator's own machine) — not on untrusted input.
    """
    ns: dict = {}
    exec(compile(code, "<world_model>", "exec"), ns)  # noqa: S102 - author-trusted
    missing = [name for name in _REQUIRED if not callable(ns.get(name))]
    if missing:
        raise ValueError(
            f"world-model code is missing callables: {missing}. "
            f"Got: {[k for k, v in ns.items() if callable(v)]}"
        )
    out = {name: ns[name] for name in _REQUIRED}
    for optional in ("fingerprint", "ignore"):
        if callable(ns.get(optional)):
            out[optional] = ns[optional]
    return out


def _render_frame_text(frame, indent: int = 0) -> str:
    pad = " " * indent
    return "\n".join(pad + " ".join(f"{v:2d}" for v in row) for row in frame)
