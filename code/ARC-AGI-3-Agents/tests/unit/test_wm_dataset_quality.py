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


# ---------------------------------------------------------------------------
# The pointed cells have to reach the journal, or no repair pair can ever pass.
# ---------------------------------------------------------------------------

def test_pointed_cells_are_computed_from_two_frames():
    """Every repair pair failed the `cells` check because the journal held none.
    refute() has always accepted a `diff`, and no caller ever passed one, so the
    single most useful part of a counterexample -- which cells, predicted what,
    actually what -- was computed and dropped."""
    import execute_gated as eg
    predicted = [[1, 2], [3, 4]]
    actual = [[1, 9], [3, 4]]
    assert eg.pointed_cells(predicted, actual) == [[0, 1, 2, 9]]


def test_pointed_cells_respects_the_ignore_mask():
    """A cell the model declared unpredictable is debt, not a counterexample."""
    import execute_gated as eg
    predicted = [[1, 2], [3, 4]]
    actual = [[1, 9], [3, 8]]
    assert eg.pointed_cells(predicted, actual, ignore={(0, 1)}) == [[1, 1, 4, 8]]


def test_pointed_cells_is_empty_when_a_frame_is_missing():
    """A death often returns no frame; there is nothing to point at."""
    import execute_gated as eg
    assert eg.pointed_cells(None, [[1]]) == []
    assert eg.pointed_cells([[1]], None) == []


def test_a_status_only_refutation_is_trainable():
    """The model said it had won and it had not. No cell is wrong, so `cells` is
    correctly empty -- and the quality gate threw all four of KA59's away.

    This is the most informative counterexample the loop produces: it means the
    dynamics are right and is_goal is wrong, which is a much sharper instruction
    than "some cells differ". Requiring pointed cells was right for a frame
    mismatch and wrong for this."""
    good = {"type": "repair",
            "input": {"bug": "gated execution stopped at step 9 after ACTION3: "
                             "status predicted=LEVEL_COMPLETED actual=RUNNING",
                      "cells": [], "model_source_before": "x" * 200},
            "target": {"model_source_after": "y" * 200,
                       "changed": "is_goal fired on a state that is not a win"}}
    assert ex.is_trainable(good)


def test_a_repair_with_neither_cells_nor_a_status_mismatch_is_not_trainable():
    """A complaint with nothing pointed in it is still not a counterexample."""
    bad = {"type": "repair",
           "input": {"bug": "the model did not work", "cells": [],
                     "model_source_before": "x" * 200},
           "target": {"model_source_after": "y" * 200, "changed": "rewrote it"}}
    assert not ex.is_trainable(bad)


def test_a_rejection_becomes_a_repair_pair():
    """A refused proposal is (source, exact verifier complaint) and the next
    accepted proposal is the answer -- the same triple a refutation gives, from
    a different place. Twelve of them sat unused in the journal while the corpus
    had six repair pairs total."""
    import export_dataset as ex
    entries = [
        {"kind": "note", "seq": 10, "run": "r1",
         "text": "BRAIN REJECTED (attempt 1): ValueError: replay failed: backtest 0/1 "
                 "then pointed bug at step 1 after ACTION3: 18 cell(s) mispredicted"
                 "\n---REJECTED SOURCE---\ndef build(v=1):\n    return WRONG"},
        {"kind": "note", "seq": 11, "run": "r1",
         "text": "BRAIN SOURCE (accepted, 20 chars):\ndef build(v=1):\n    return RIGHT"},
    ]
    pairs = ex.rejection_pairs("ka59", 0, entries)
    assert len(pairs) == 1, f"expected one pair, got {len(pairs)}"
    p = pairs[0]
    assert "18 cell(s) mispredicted" in p["input"]["bug"]
    assert "WRONG" in p["input"]["model_source_before"]
    assert "RIGHT" in p["target"]["model_source_after"]


def test_a_rejection_with_no_following_acceptance_yields_nothing():
    """Without the corrected source there is no pair, only half of one."""
    import export_dataset as ex
    entries = [{"kind": "note", "seq": 10, "run": "r1",
                "text": "BRAIN REJECTED (attempt 1): boom\n---REJECTED SOURCE---\nx = 1"}]
    assert ex.rejection_pairs("ka59", 0, entries) == []


def test_a_verifier_error_that_names_a_step_is_pointed_enough():
    """A rejection reports the failure as prose: 'backtest 0/1 then pointed bug
    at step 1 after ACTION6(23,16): 38 cell(s) mispredicted'. It names the step,
    the action and the count, so it points at something specific even though the
    cell list is not carried. Requiring the list discarded all twelve."""
    good = {"type": "repair", "source": "journal L0 seq 9 (rejected proposal)",
            "input": {"bug": "ValueError: replay failed: backtest 0/1 then pointed bug "
                             "at step 1 after ACTION6(23,16): 38 cell(s) mispredicted",
                      "cells": [], "model_source_before": "x" * 200},
            "target": {"model_source_after": "y" * 200,
                       "changed": "the click rule was wrong"}}
    assert ex.is_trainable(good)


def test_a_bug_naming_no_step_is_still_not_pointed():
    bad = {"type": "repair", "source": "journal L0 seq 9 (rejected proposal)",
           "input": {"bug": "it did not work", "cells": [],
                     "model_source_before": "x" * 200},
           "target": {"model_source_after": "y" * 200, "changed": "rewrote"}}
    assert not ex.is_trainable(bad)
