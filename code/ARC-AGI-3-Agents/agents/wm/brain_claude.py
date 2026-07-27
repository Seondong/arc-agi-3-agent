"""propose() filled by a headless Claude Code process, with the answer verified.

This closes the seam that has been open the whole time. `SolveLoop` has always
called `brain.propose(timeline, prev_model, report) -> WorldModel`; until now the
models were written by a Claude Code session between conversational turns, which
means no run was ever unattended, no score was comparable to a published one, and
`repair` training pairs accumulated only as fast as someone typed.

Two properties matter more than the prompt:

**The answer is gated by the same verifier the loop already trusts.** A proposal
is not accepted because it looks plausible; it is imported, constructed, asked to
reconstruct the initial frame, and replayed against every recorded timeline. If
it fails it goes back with the failure attached. That is NOOA's validated-return
contract with `run_backtest` as the validator, and it is what makes a small model
usable later: a 7B that writes a wrong model is not a wrong agent, it is an agent
that gets a counterexample and another turn.

**Every accepted proposal is a training pair.** Input: the pointed bug plus the
source as it stood. Target: the source that passed. These are the `repair` pairs
the corpus is short of — three of them at the time this was written, all produced
by hand.

The subprocess returns SOURCE TEXT and never edits the repository. A brain that
writes files would be harder to sandbox, harder to retry, and would leave no
clean record of what it actually proposed.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .backtest import run_backtest
from .core import Timeline, WorldModel

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)

# "You've hit your session limit · resets 7:50pm (Asia/Seoul)", and the usual
# transport-level refusals that mean the same thing: come back later.
RATE_LIMIT = re.compile(r"session limit|rate limit|rate_limit|429|"
                        r"overloaded|quota|usage limit", re.I)
RESET_AT = re.compile(r"resets?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)


class RateLimited(RuntimeError):
    """The account is out of capacity. Not a failed proposal; costs no budget."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message

    def reset_epoch(self, now=None):
        """When the limit lifts, as a unix time, or None if the text has no clue."""
        import datetime as _dt
        m = RESET_AT.search(self.message)
        if not m:
            return None
        now = now or _dt.datetime.now()
        hour = int(m.group(1)) % 12
        if (m.group(3) or "").lower() == "pm":
            hour += 12
        at = now.replace(hour=hour, minute=int(m.group(2) or 0), second=0,
                         microsecond=0)
        if at <= now:                       # it must mean tomorrow
            at += _dt.timedelta(days=1)
        return at.timestamp()

CONTRACT = '''You are writing an executable world model for an unfamiliar grid game.

Return ONE fenced python code block and nothing else. It must be a complete,
self-contained module defining:

    def build(version: int = 1) -> WorldModel

`build` must return ANY object providing the six methods below. Define your own
class and return an instance of it:

    class Model:
        def reconstruct(self, frame): ...
        def step(self, state, action): ...
        ...
    def build(version: int = 1):
        return Model()

Do NOT construct `agents.wm.core.WorldModel` — it is a dataclass whose fields are
callables, and calling `WorldModel()` raises TypeError for five missing
arguments. That single mistake has cost two runs eleven minutes each. `Action`
and `Status` may be imported from `agents.wm.core` if you want them, but nothing
here requires it: `status` is just one of the three strings below.

The object must provide:
  reconstruct(frame)   -> state      built from ONE frame, the level's first
  step(state, action)  -> (state, status)   status in "RUNNING",
                                            "LEVEL_COMPLETED", "GAME_OVER"
  render(state)        -> frame      the full grid; raise NotImplementedError
                                     ONLY if you truly cannot reproduce it
  is_goal(state)       -> bool       return False if you do not know the win
                                     condition — never invent one
  fingerprint(state)   -> hashable   used to key the planner's visited set
  ignore(frame)        -> [(r, c)]   optional: cells excluded from checking.
                                     Every excluded cell is debt; exclude only
                                     what you genuinely cannot predict, such as
                                     a step counter.

Rules:
- An action arrives as `Action(name, x, y)`. Directional actions have x=y=None.
  ACTION6 is a COORDINATE action: `action.x` is the column and `action.y` the row
  that was clicked. Some games offer ACTION6 and nothing else.
- State must be immutable and hashable through `fingerprint`.
- Do not read any file outside what is given here. Do not import the game.
- Prefer rules that are forced by the evidence below. An unforced special case
  will not transfer to the next level.
- If you cannot explain some cells, exclude them via `ignore` and say so in a
  comment rather than guessing.
'''


def _grid_text(frame, r0=0, r1=None, c0=0, c1=None, ch=None):
    if frame is None:
        return "(no frame)"
    r1 = len(frame) - 1 if r1 is None else r1
    c1 = len(frame[0]) - 1 if c1 is None else c1
    out = ["    " + "".join(str(c % 10) for c in range(c0, c1 + 1))]
    for r in range(r0, r1 + 1):
        out.append(f"{r:3d} " + "".join(f"{frame[r][c]:x}" for c in range(c0, c1 + 1)))
    return "\n".join(out)


def bug_report(report) -> str:
    """The pointed bug, as compactly as it can be stated without losing it."""
    if report is None or report.ok:
        return "No counterexample: the current model reproduces everything recorded."
    m = report.first_mismatch
    if m is None:
        return report.summary()
    lines = [f"COUNTEREXAMPLE — {report.summary()}",
             f"after action {m.action} at step {m.step_index}"]
    if m.predicted_frame is not None and m.actual_frame is not None:
        cells = [(r, c, m.predicted_frame[r][c], m.actual_frame[r][c])
                 for r in range(len(m.actual_frame))
                 for c in range(len(m.actual_frame[0]))
                 if m.predicted_frame[r][c] != m.actual_frame[r][c]]
        lines.append(f"{len(cells)} cell(s) differ [row, col, predicted, actual]:")
        lines.append("  " + ", ".join(f"[{r},{c},{p},{a}]" for r, c, p, a in cells[:60]))
        if len(cells) > 60:
            lines.append(f"  ... and {len(cells) - 60} more")
        rows = [c[0] for c in cells]
        cols = [c[1] for c in cells]
        r0, r1 = max(0, min(rows) - 3), min(len(m.actual_frame) - 1, max(rows) + 3)
        c0, c1 = max(0, min(cols) - 3), min(len(m.actual_frame[0]) - 1, max(cols) + 3)
        lines.append("\npredicted (hex values):")
        lines.append(_grid_text(m.predicted_frame, r0, r1, c0, c1))
        lines.append("\nactual:")
        lines.append(_grid_text(m.actual_frame, r0, r1, c0, c1))
    return "\n".join(lines)


def crop_box(frame, pad=1):
    """The interesting rectangle: everything that is not the most common value."""
    from collections import Counter
    bg = Counter(v for row in frame for v in row).most_common(1)[0][0]
    rs = [r for r in range(len(frame)) if any(v != bg for v in frame[r])]
    cs = [c for c in range(len(frame[0]))
          if any(frame[r][c] != bg for r in range(len(frame)))]
    if not rs or not cs:
        return 0, len(frame) - 1, 0, len(frame[0]) - 1
    return (max(0, min(rs) - pad), min(len(frame) - 1, max(rs) + pad),
            max(0, min(cs) - pad), min(len(frame[0]) - 1, max(cs) + pad))


def _pair_text(before, after, r0, r1, c0, c1, mark=None):
    """The changed region, before beside after, so the shape of the change shows.

    A flat list of 38 `[row,col,from,to]` tuples contains the same information
    and hides it: the reader has to plot 38 coordinates by hand before any
    geometry appears. Every coordinate-game model proposed for ft09, vc33, bp35
    and cd82 failed at step 1 while being given exactly that list. Two crops side
    by side make a rectangle filling in, a row shifting, or a block clearing
    visible at a glance.

    `mark` is the clicked cell, drawn as `*` in the BEFORE crop — a click whose
    location is not shown is a rule with its subject missing.
    """
    w = c1 - c0 + 1
    head = "    " + "".join(str(c % 10) for c in range(c0, c1 + 1))
    lines = [f"{head}   |{head}"]
    for r in range(r0, r1 + 1):
        b = "".join("*" if mark == (r, c) else f"{before[r][c]:x}"
                    for c in range(c0, c1 + 1))
        a = "".join(f"{after[r][c]:x}" for c in range(c0, c1 + 1))
        lines.append(f"{r:3d} {b}   |{r:3d} {a}")
    return "\n".join(lines), w


def evidence_text(timelines: list[Timeline], max_steps=30, max_cells=120) -> str:
    """What has been seen: the opening frame, and every cell each action changed.

    The first version of this gave only change COUNTS and bounding boxes. The
    brain read it, said so, and refused to invent dynamics it could not see —
    which was the correct answer to a bad question. A world model cannot be
    written from "100 cells changed somewhere"; it needs which cells, from what,
    to what.

    The second version gave the cells and nothing else, which is complete but
    unreadable for a coordinate game: see `_pair_text`.
    """
    out = []
    for i, tl in enumerate(timelines):
        init = tl.initial_frame
        r0, r1, c0, c1 = crop_box(init)
        out.append(f"--- recorded run {i + 1}: {len(tl)} step(s)")
        out.append(f"opening frame, rows {r0}-{r1} cols {c0}-{c1}, "
                   f"one hex digit per cell (full grid is "
                   f"{len(init)}x{len(init[0])}):")
        out.append(_grid_text(init, r0, r1, c0, c1))
        prev = init
        for tr in tl.transitions[:max_steps]:
            if tr.after_frame is None:
                out.append(f"  {tr.action} -> {tr.status} (engine returned no frame)")
                continue
            d = [(r, c, prev[r][c], tr.after_frame[r][c])
                 for r in range(len(prev)) for c in range(len(prev[0]))
                 if prev[r][c] != tr.after_frame[r][c]]
            act = tr.action
            where = ""
            if getattr(act, "x", None) is not None:
                y, x = act.y, act.x
                held = (prev[y][x] if 0 <= y < len(prev) and 0 <= x < len(prev[0])
                        else "?")
                where = (f"; clicked row {y} col {x}, which held value "
                         f"{held:x}" if held != "?" else
                         f"; clicked row {y} col {x} (outside the grid)")
            if not d:
                out.append(f"  {act} -> {tr.status}{where}; nothing changed at all")
                prev = tr.after_frame
                continue

            rows = [c[0] for c in d]
            cols = [c[1] for c in d]
            br0, br1 = max(0, min(rows) - 2), min(len(prev) - 1, max(rows) + 2)
            bc0, bc1 = max(0, min(cols) - 2), min(len(prev[0]) - 1, max(cols) + 2)
            out.append(f"  {act} -> {tr.status}{where}; {len(d)} cell(s) changed, "
                       f"all inside rows {br0}-{br1} cols {bc0}-{bc1}")
            # A change spanning the whole board is not a picture of anything;
            # the cell list stays the better representation there.
            if (br1 - br0 + 1) * (bc1 - bc0 + 1) <= 1200:
                mark = ((act.y, act.x) if getattr(act, "x", None) is not None
                        else None)
                body, _ = _pair_text(prev, tr.after_frame, br0, br1, bc0, bc1,
                                     mark)
                out.append("  BEFORE (* = the clicked cell)   |AFTER")
                out.append(body)
            shown = ", ".join(f"[{r},{c},{a},{b}]" for r, c, a, b in d[:max_cells])
            more = (f" ...and {len(d) - max_cells} more"
                    if len(d) > max_cells else "")
            out.append(f"  same change as [row,col,from,to]: {shown}{more}")
            prev = tr.after_frame
    return "\n".join(out)


@dataclass
class Proposal:
    source: str
    accepted: bool
    report: str
    attempt: int
    error: Optional[str] = None


@dataclass
class ClaudeCodeBrain:
    """`propose()` backed by `claude -p`, with the result verified before use."""

    game: str
    workdir: Path = field(default_factory=lambda: Path(tempfile.mkdtemp(prefix="wmbrain-")))
    max_attempts: int = 3
    timeout_s: int = 900
    model: Optional[str] = None
    log: list = field(default_factory=list)

    # -- the call ------------------------------------------------------------
    def _ask(self, prompt: str) -> str:
        cmd = ["claude", "-p", prompt, "--output-format", "text"]
        if self.model:
            cmd += ["--model", self.model]
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=self.timeout_s, cwd=str(self.workdir))
        if r.returncode != 0:
            msg = (r.stderr or r.stdout)[:400]
            # Not the same kind of thing as a bad proposal, and the caller must
            # not spend budget on it. Four games running in parallel exhausted
            # the account's session limit, and the loop then treated each
            # instant refusal as a failed model: 34 of 45 brain calls across the
            # four runs were consumed in seconds, each one also paying for an
            # exploration round of real engine steps. ft09 hit it at call 3 of
            # 12 and the other nine evaporated without a single question asked.
            if RATE_LIMIT.search(msg):
                raise RateLimited(msg)
            raise RuntimeError(f"claude -p failed ({r.returncode}): {msg}")
        return r.stdout

    def build_prompt(self, timelines, prev_source, report, extra=None) -> str:
        parts = [CONTRACT,
                 f"\nGAME: {self.game}. Actions are named ACTION1..ACTION7; only the "
                 f"ones appearing in the evidence below are available.",
                 "\nEVIDENCE — every interaction recorded so far:",
                 evidence_text(timelines),
                 "\n" + bug_report(report)]
        if prev_source:
            parts.append("\nTHE MODEL AS IT STANDS (fix it; keep what the evidence "
                         "forces, drop what it does not):\n```python\n"
                         + prev_source + "\n```")
        else:
            parts.append("\nThere is no model yet. Write the first one.")
        if extra:
            parts.append("\n" + extra)
        parts.append("\nReturn the complete module in one fenced python block.")
        return "\n".join(parts)

    # -- verification --------------------------------------------------------
    def _load(self, source: str):
        import importlib.util
        path = self.workdir / f"cand_{uuid.uuid4().hex[:8]}.py"
        path.write_text(source)
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "build"):
            raise AttributeError("module defines no build(version) function")
        return mod.build(1), path

    def verify(self, source: str, timelines: list[Timeline]):
        """Import, construct, reconstruct, and replay. Returns (model, report)."""
        model, _ = self._load(source)
        if not timelines:
            return model, "no recorded evidence yet; nothing to verify against"
        total = matched = 0
        for tl in timelines:
            rep = run_backtest(model, tl)
            total += rep.total
            matched += rep.matched
            if not rep.ok:
                raise ValueError(f"replay failed: {rep.summary()}")
        return model, f"replayed {matched}/{total} recorded steps exactly"

    # -- the seam ------------------------------------------------------------
    def propose(self, timelines, prev_source, report, extra=None):
        """Ask, verify, and on failure ask again with the failure attached."""
        prompt = self.build_prompt(timelines, prev_source, report, extra)
        last_err = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                text = self._ask(prompt if last_err is None else
                                 prompt + f"\n\nYOUR PREVIOUS ANSWER WAS REJECTED:\n"
                                          f"{last_err}\nFix exactly that and return "
                                          f"the whole module again.")
            except RateLimited:
                # Straight through: retrying here would burn the remaining
                # attempts against a wall that does not move for hours.
                raise
            except subprocess.TimeoutExpired:
                # A timeout used to kill the whole level: cd82's first call ran
                # out at 900s and the level was abandoned with 7 brain calls and
                # 55 minutes unspent. A slow answer is not a wrong one, and the
                # next attempt is asked to be brief rather than asked again.
                last_err = (f"your previous attempt did not finish within "
                            f"{self.timeout_s}s. Answer with the shortest model "
                            f"that fits the evidence; do not explain it.")
                self.log.append(Proposal("", False, "", attempt, last_err))
                continue
            blocks = CODE_BLOCK.findall(text)
            if not blocks:
                last_err = "no fenced python block in the reply"
                self.log.append(Proposal("", False, "", attempt, last_err))
                continue
            source = max(blocks, key=len)
            try:
                model, note = self.verify(source, timelines)
            except Exception as exc:                      # noqa: BLE001
                import traceback
                tb = traceback.format_exc(limit=6)
                # The candidate is kept on disk: a rejected proposal is the more
                # valuable half of a repair pair and must not evaporate.
                bad = self.workdir / f"rejected_{attempt}.py"
                bad.write_text(source)
                last_err = f"{type(exc).__name__}: {exc}\n{tb[-900:]}"
                self.log.append(Proposal(source, False, "", attempt, last_err))
                continue
            self.log.append(Proposal(source, True, note, attempt))
            return model, source, note
        raise RuntimeError(f"no acceptable model after {self.max_attempts} "
                           f"attempt(s); last failure: {last_err}")
