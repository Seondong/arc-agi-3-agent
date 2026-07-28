"""A training pair has to teach something.

The journal is an audit trail: failed searches, empty explorations and boilerplate
notes belong in it. The dataset is not the journal. Exporting one as the other
produced 2,011 "pairs" of which a large fraction taught nothing or taught the
wrong thing, while the counts read as progress.

Each test below pins one measured defect.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "wm"))

import export_dataset as ex  # noqa: E402


def test_a_plan_pair_with_no_actions_is_not_trainable():
    """26 of 47 plan pairs had an empty action list — a failed search kept as an
    example, teaching 'given this frame, output nothing'."""
    bad = {"type": "plan", "input": {"frame": [[0]], "level": 0},
           "target": {"actions": [], "stats": {"found": False}}}
    assert not ex.is_trainable(bad)


def test_a_plan_pair_with_no_frame_is_not_trainable():
    """20 of 47 had input frame None: a target with no question attached."""
    bad = {"type": "plan", "input": {"frame": None, "level": 0},
           "target": {"actions": ["ACTION1"], "stats": {}}}
    assert not ex.is_trainable(bad)


def test_a_real_plan_pair_is_trainable():
    good = {"type": "plan", "input": {"frame": [[0]], "level": 0},
            "target": {"actions": ["ACTION1", "ACTION2"], "stats": {"found": True}}}
    assert ex.is_trainable(good)


def test_an_analyse_pair_that_is_only_a_log_line_is_not_trainable():
    """38 of 59 analyse targets were entities-empty, carrying only a note like
    'autosolve: gathered 16 evidence run(s) on L0'."""
    bad = {"type": "analyse", "input": {"frame": [[0]]},
           "target": {"entities": {}, "note": "autosolve: gathered 16 evidence run(s)"}}
    assert not ex.is_trainable(bad)


def test_an_analyse_pair_with_entities_is_trainable():
    good = {"type": "analyse", "input": {"frame": [[0]]},
            "target": {"entities": {"tiles": [[9, 9, 9]]}, "note": "x"}}
    assert ex.is_trainable(good)


def test_a_repair_pair_without_the_pointed_cells_is_not_trainable():
    """All 9 repair pairs had cells: [] — the pointed cells are the whole reason
    a refutation beats a vague complaint, and they were absent."""
    bad = {"type": "repair",
           "input": {"bug": "step 4 after ACTION4: 1094 cells mispredicted",
                     "cells": [], "model_source_before": "x" * 200},
           "target": {"model_source_after": "y" * 200, "changed": "fixed the rule"}}
    assert not ex.is_trainable(bad)


def test_a_repair_pair_answered_by_an_unrelated_author_is_not_trainable():
    """5 of 9 paired a refutation with an author entry whose `changed` was the
    generic 'model proposed from N evidence run(s)' — i.e. not the fix for that
    bug at all. This is the pairing bug that once taught 'the fix is to do
    nothing', in a new costume."""
    bad = {"type": "repair",
           "input": {"bug": "step 4 after ACTION4: 1094 cells mispredicted",
                     "cells": [[1, 2, 3, 4]], "model_source_before": "x" * 200},
           "target": {"model_source_after": "y" * 200,
                      "changed": "model proposed from 16 evidence run(s)"}}
    assert not ex.is_trainable(bad)


def test_a_real_repair_pair_is_trainable():
    good = {"type": "repair",
            "input": {"bug": "step 4 after ACTION4: 1094 cells mispredicted",
                      "cells": [[1, 2, 3, 4]], "model_source_before": "x" * 200},
            "target": {"model_source_after": "y" * 200,
                       "changed": "the pursuer rule moved one step too far"}}
    assert ex.is_trainable(good)


def test_identical_probes_collapse_to_one():
    """1,645 probe pairs came from 35 distinct questions; the commonest appeared
    267 times. Repetition at that ratio is weight on one sentence, not data."""
    p = {"type": "probe", "input": {"frame": [[0]], "question": "does the coordinate action do anything on value 9?"},
         "target": {"actions": ["ACTION6@1:1"], "observed": "46 cells", "died": False}}
    same = dict(p)
    other = {"type": "probe", "input": {"frame": [[0]], "question": "is ACTION3 inert?"},
             "target": {"actions": ["ACTION3"], "observed": "0 cells", "died": False}}
    kept = ex.dedupe([p, same, other])
    assert len(kept) == 2, f"expected the duplicate to collapse, got {len(kept)}"
