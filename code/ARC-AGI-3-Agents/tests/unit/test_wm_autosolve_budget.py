"""The unattended loop must spend only what it was given.

Every test here pins a way a run overran or threw away its own work. They use a
fake clock and a fake sleep so a two-hour budget takes no wall-clock time.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "wm"))


class FakeClock:
    """A clock that only moves when something sleeps."""

    def __init__(self, now=1_000_000.0):
        self.now = now
        self.slept = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept += seconds
        self.now += seconds


class AlwaysLimited:
    """A brain whose every call is refused for capacity."""

    def __init__(self):
        self.calls = 0

    def propose(self, *a, **k):
        from agents.wm.brain_claude import RateLimited
        self.calls += 1
        raise RateLimited("You've hit your session limit · resets 9:10am (Asia/Seoul)")


class Args:
    max_brain = 12
    explore_budget = 4
    max_depth = 20
    budget_x = 5.0


class NullJournal:
    def note(self, **k):
        pass

    def author(self, **k):
        pass


def test_ask_brain_stops_at_the_deadline_instead_of_waiting_past_it(monkeypatch):
    """A run given 120 minutes waited eight hours.

    bp35 and cd82 each sat in the rate-limit wait loop overnight, spending 37
    and 39 engine steps in 28,696 and 28,671 seconds against a --minutes 120
    budget. The wait must never carry the run past the deadline it was given.
    """
    import autosolve

    clock = FakeClock()
    monkeypatch.setattr(autosolve.time, "time", clock.time)
    monkeypatch.setattr(autosolve.time, "sleep", clock.sleep)

    from agents.wm.brain_claude import RateLimited

    budget_s = 120 * 60
    deadline = clock.time() + budget_s

    with pytest.raises(RateLimited):
        autosolve.ask_brain(AlwaysLimited(), [], None, None, None, Args(),
                            deadline, NullJournal(), 0)

    assert clock.time() <= deadline, (
        f"ask_brain ran {clock.time() - deadline:.0f}s past its deadline")
    assert clock.slept <= budget_s, (
        f"slept {clock.slept:.0f}s against a {budget_s:.0f}s budget")


def test_a_brain_call_cannot_outlast_the_run(monkeypatch):
    """One call could take max_attempts x timeout_s no matter what --minutes said.

    This is what actually burned the night. `claude -p` HANGS when the account
    is out of capacity rather than exiting non-zero, so each attempt cost its
    full 600s timeout, four attempts made a 2400s call, and twelve calls made
    28,800s -- against a --minutes 120 budget, which was never consulted once a
    call had started. bp35 measured 28,696s. The deadline has to reach inside.
    """
    import autosolve

    clock = FakeClock()
    monkeypatch.setattr(autosolve.time, "time", clock.time)
    monkeypatch.setattr(autosolve.time, "sleep", clock.sleep)

    class Hangs:
        """Burns its whole per-attempt timeout, every attempt, like the real one."""

        max_attempts = 4
        timeout_s = 600

        def propose(self, *a, **k):
            for _ in range(self.max_attempts):
                clock.sleep(self.timeout_s)
            raise RuntimeError("no acceptable model after 4 attempt(s)")

    deadline = clock.time() + 10 * 60          # ten minutes left
    with pytest.raises(Exception):
        autosolve.ask_brain(Hangs(), [], None, None, None, Args(), deadline,
                            NullJournal(), 0)

    assert clock.time() <= deadline, (
        f"one brain call ran {clock.time() - deadline:.0f}s past the deadline")


def test_ask_brain_does_wait_when_the_budget_allows_it(monkeypatch):
    """The bounded wait must still work: this is what keeps budget unspent."""
    import autosolve
    from agents.wm.brain_claude import RateLimited

    clock = FakeClock()
    monkeypatch.setattr(autosolve.time, "time", clock.time)
    monkeypatch.setattr(autosolve.time, "sleep", clock.sleep)

    class LimitedOnce:
        def __init__(self):
            self.calls = 0

        def propose(self, *a, **k):
            self.calls += 1
            if self.calls == 1:
                raise RateLimited("session limit · resets 9:10am")
            return ("MODEL", "SOURCE", "replayed 3/3")

    brain = LimitedOnce()
    got = autosolve.ask_brain(brain, [], None, None, None, Args(),
                              clock.time() + 8 * 3600, NullJournal(), 0)
    assert got == ("MODEL", "SOURCE", "replayed 3/3")
    assert brain.calls == 2, "it must retry after waiting, not give up"
    assert clock.slept > 0, "it must actually wait rather than spin"


# ---------------------------------------------------------------------------
# Rejected proposals are the richest repair data the loop produces, and it was
# throwing the valuable half away.
# ---------------------------------------------------------------------------

class RecordingJournal:
    def __init__(self):
        self.notes = []

    def note(self, *, text):
        self.notes.append(text)

    def author(self, **k):
        pass


def test_a_rejected_proposal_is_journaled_with_its_source():
    """(rejected source + the verifier's exact complaint) -> (source that passed)
    is a complete repair pair, and the loop makes one every time a proposal is
    refused. It was journaling the complaint and dropping the source, so 27
    rejections across the games yielded 27 notes of ~150 characters and no
    trainable pair. The source exists in brain.log; it just was not written.
    """
    import autosolve
    from agents.wm.brain_claude import Proposal

    brain = type("B", (), {})()
    brain.log = [
        Proposal(source="def build(v=1):\n    return BROKEN", accepted=False,
                 report="", attempt=1,
                 error="ValueError: replay failed: backtest 0/1 then pointed bug "
                       "at step 1 after ACTION6(23,16): 38 cell(s) mispredicted"),
    ]
    J = RecordingJournal()
    autosolve.journal_rejections(J, brain, limit=4)

    assert J.notes, "a rejection must be journaled at all"
    text = "\n".join(J.notes)
    assert "38 cell(s) mispredicted" in text, "the complaint must survive"
    assert "return BROKEN" in text, (
        "the REJECTED SOURCE must survive — without it there is no pair, only "
        "an error message")


def test_a_rejection_without_source_is_still_journaled():
    """A reply with no code block has an error and no source. Still worth a line."""
    import autosolve
    from agents.wm.brain_claude import Proposal

    brain = type("B", (), {})()
    brain.log = [Proposal(source="", accepted=False, report="", attempt=1,
                          error="no fenced python block in the reply")]
    J = RecordingJournal()
    autosolve.journal_rejections(J, brain, limit=4)
    assert any("no fenced python block" in t for t in J.notes)
