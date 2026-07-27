"""Recover a brain-written world model from the journal into agents/wm/models/.

The brain returns SOURCE TEXT and never writes files — deliberately, since a
subprocess that edits the repository is harder to sandbox, harder to retry, and
leaves no clean record of what it actually proposed. The cost of that choice is
that a model lives only in memory for the length of one run, and afterwards only
as a line of JSONL. `agents/wm/models/ft09.py` did not exist even at the moment
ft09 L0 was cleared.

That is not acceptable for a model that WON. It cannot be carried into the next
session, cannot be re-run against later levels, cannot be simplified, and
`gen_site.py` cannot build the game a page because it imports the module. So this
lifts the source back out.

Where the source actually is, in order of preference:

  1. an `author` entry's `code`, when it holds real source. Early entries store
     the string "proposed source stored with this entry" instead — the same
     placeholder that made tu93's early models unrecoverable. Anything that short
     is a placeholder, not a model.
  2. the `BRAIN SOURCE` note written beside it, which always held the real text.

By default it takes the model that was in force when the level CLEARED, because
that is the one known to be right. `--seq` overrides for post-mortems on models
that lost.

Usage:
  extract_model.py --game ft09                    # the model that cleared a level
  extract_model.py --game ft09 --level 0 --seq 62 # a specific one
  extract_model.py --game ft09 --stdout           # look without writing
"""
import re
from pathlib import Path

import _cli
from agents.wm.journal import load as load_journal
from agents.wm.models import short_id

SHIM = '''

# ---------------------------------------------------------------------------
# Registry adapter, added by this script.
# The brain writes `build(version)`; the registry calls
# `<game>_world_model(**kwargs)` and passes keywords a brain-written model has
# never heard of (`legacy=[...]`, used by the simplification pass). Swallowing
# them keeps the game-agnostic tools working against a recovered model.
# ---------------------------------------------------------------------------
def {g}_world_model(version: int = 1, **_ignored):
    return build(version)
'''

PLACEHOLDER_MAX = 80          # "proposed source stored with this entry" is 38
NOTE_PREFIX = re.compile(r"^BRAIN SOURCE[^\n]*\n", re.M)


def entries(game, levels=8):
    out = []
    for lv in range(levels):
        for e in load_journal(game, lv):
            out.append(e)
    return out


def source_at(ents, seq, run):
    """The model source recorded at `seq`, from the author entry or its note."""
    au = next((e for e in ents if e["seq"] == seq and e["kind"] == "author"), None)
    if au and len((au.get("code") or "")) > PLACEHOLDER_MAX:
        return au["code"], f"author seq={seq}"
    # the note sits immediately after the author entry in the same run
    for e in ents:
        if (e["kind"] == "note" and e.get("run") == run and e["seq"] > seq
                and "BRAIN SOURCE" in (e.get("text") or "")):
            return NOTE_PREFIX.sub("", e["text"], count=1), f"note seq={e['seq']}"
    return None, None


def winning_seq(ents):
    """The model in force when a level cleared: the last author before it."""
    wins = [e for e in ents if e["kind"] == "execute" and e.get("cleared")]
    if not wins:
        return None, None, None
    win = max(wins, key=lambda e: e["seq"])
    au = [e for e in ents if e["kind"] == "author" and e.get("run") == win["run"]
          and e["seq"] < win["seq"]]
    if not au:
        return None, None, win
    last = max(au, key=lambda e: e["seq"])
    return last["seq"], last.get("run"), win


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--seq", type=int, default=None)
    p.add_argument("--stdout", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing agents/wm/models/<game>.py")
    a = p.parse_args()
    game = short_id(a.game)
    ents = entries(game)
    if not ents:
        raise SystemExit(f"{game}: no journal to recover from")

    if a.seq is not None:
        au = next((e for e in ents if e["seq"] == a.seq), None)
        if au is None:
            raise SystemExit(f"{game}: no entry at seq {a.seq}")
        seq, run, win = a.seq, au.get("run"), None
    else:
        seq, run, win = winning_seq(ents)
        if seq is None:
            raise SystemExit(
                f"{game}: no level has cleared, so no model is known to be "
                f"right. Pick one explicitly with --seq; list them with\n"
                f"  grep -o '\"version\": \"[^\"]*\"' "
                f"artifacts/wm_journal/{game}/L*.jsonl")
        print(f"{game}: level cleared in {win['env_steps']} action(s) "
              f"({', '.join(win['actions'])})")

    src, where = source_at(ents, seq, run)
    if src is None:
        raise SystemExit(
            f"{game}: the model at seq {seq} is unrecoverable — its author entry "
            f"holds only the placeholder and no BRAIN SOURCE note follows it. "
            f"This is what made tu93's early models unrecoverable.")
    print(f"{game}: recovered {len(src)} chars from {where}")

    if a.stdout:
        print("\n" + src)
        return 0

    out = Path("agents/wm/models") / f"{game}.py"
    if out.exists() and not a.force:
        raise SystemExit(f"{out} exists; pass --force to overwrite")
    header = (f'"""Recovered from the journal by scripts/wm/extract_model.py.\n\n'
              f'Written by a headless Claude Code brain during an autosolve run '
              f'and\nverified there by replay; this file is a copy of that '
              f'source, taken from\n{where}. It is not hand-written and has not '
              f'been hand-edited.\n"""\n')
    out.write_text(header + src + SHIM.replace("{g}", game))
    print(f"wrote {out}")
    print(f"register it by adding {game!r} to MODELS in agents/wm/models/__init__.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
