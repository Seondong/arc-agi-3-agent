"""Simplification with a verifier: keep a simpler model only if it still predicts.

The ablation paper runs a scheduled simplification pass — at intervals the agent
is asked to remove distinctions not forced by evidence, replace case-by-case
behaviour with shared rules, and separate level-specific data from mechanics. It
helped in three of four settings, and its risk is obvious: a refactor can destroy
a partially correct model.

That risk is exactly what a replay verifier removes. So simplification here is not
a prompt, it is a *search with an acceptance test*: propose a weakening of the
model, replay everything ever recorded through it, and accept it only if it stays
cell-exact. A simplification that survives the whole evidence base is one the
evidence never forced you to make in the first place.

Two things this gives the distillation target, which is the point of keeping it:

  a training signal   every accepted simplification is a
                      (model, evidence) -> (simpler model) pair, and every
                      rejected one is a (model, counterexample) pair explaining
                      why the simpler rule is wrong. The rejections are the more
                      valuable half and they are free.
  a generality prior  our measured failure is coverage, not efficiency: models
                      solve the levels they were built on and stall on the next.
                      An unforced special case is precisely what fails to transfer.

The concrete weakenings tried are the ones our models actually accumulate — they
come from `model_debt.py`'s categories, so the gauge and the pass talk about the
same things.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .backtest import run_backtest
from .core import Timeline, WorldModel


@dataclass
class Candidate:
    """One proposed weakening of the model."""
    name: str
    why: str                      # what evidence would have to force this rule
    build: Callable[[], WorldModel]


@dataclass
class Outcome:
    name: str
    why: str
    accepted: bool
    report: str
    counterexample: Optional[dict] = None

    def line(self) -> str:
        verdict = "SIMPLER, kept" if self.accepted else "forced by evidence"
        return f"{self.name:<28} {verdict:<20} {self.report}"


def try_simplifications(candidates: list[Candidate], timelines: list[Timeline],
                        *, verbose: bool = True) -> list[Outcome]:
    """Replay every recorded timeline through each candidate; keep the survivors.

    `timelines` should be everything the game has ever produced, not just the
    latest level — a rule forced by L4 must not be dropped because L7 happens not
    to exercise it.
    """
    out = []
    for cand in candidates:
        try:
            model = cand.build()
        except Exception as exc:                       # noqa: BLE001
            out.append(Outcome(cand.name, cand.why, False,
                               f"could not even be constructed: {exc!r}"))
            continue
        worst = None
        total = matched = 0
        for tl in timelines:
            rep = run_backtest(model, tl)
            total += rep.total
            matched += rep.matched
            if not rep.ok and worst is None:
                m = rep.first_mismatch
                worst = {"step": getattr(m, "step_index", None),
                         "action": getattr(m, "action", None),
                         "cells": getattr(m, "changed_cells", None),
                         "summary": rep.summary()}
        ok = worst is None
        report = (f"{matched}/{total} exact"
                  if ok else f"{matched}/{total}, then {worst['summary']}")
        out.append(Outcome(cand.name, cand.why, ok, report, worst))
        if verbose:
            print("  " + out[-1].line())
    return out


def summarise(outcomes: list[Outcome]) -> dict:
    kept = [o for o in outcomes if o.accepted]
    forced = [o for o in outcomes if not o.accepted]
    return {
        "tried": len(outcomes),
        "accepted": [o.name for o in kept],
        "forced_by_evidence": [{"rule": o.name, "counterexample": o.counterexample}
                               for o in forced],
        # The rejections are the training signal worth keeping: each one says
        # "this rule is not decoration, here is the observation that needs it".
        "note": ("an accepted simplification means no recorded observation ever "
                 "forced that rule; a rejected one carries the counterexample "
                 "that does"),
    }
