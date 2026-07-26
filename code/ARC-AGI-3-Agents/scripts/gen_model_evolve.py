"""How the model's code evolved, measured rather than narrated.

Two things go into artifacts/wm_viz/model_evolve.json:

  1. THE TIMELINE. Every `author` and `refute` entry in every journal, in order:
     which version, which rule moved, which counterexample forced it. Straight
     from the append-only record — no prose written here.

  2. THE FIDELITY MATRIX. Each earlier model version is RECONSTRUCTED (via the
     `legacy` switches in tu93_model) and replayed against all nine levels along
     their own solutions, reporting the first step it gets wrong and by how many
     cells. This is the part that cannot be faked: a version that "worked at the
     time" is shown failing on the levels that came after it, and — for the two
     levels whose bug was found late — failing on levels it had supposedly
     already certified.

Also carries the current source of the rules, so the page can show the code that
each version is talking about.

Writes artifacts/wm_viz/model_evolve.json.
"""
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)
from arc_agi import Arcade, OperationMode  # noqa: E402
from arcengine import GameAction  # noqa: E402

from agents.wm.core import Action, diff_cells, ignored_cells  # noqa: E402
from agents.wm.journal import load as load_journal  # noqa: E402
from agents.wm.tu93_model import tu93_world_model  # noqa: E402

OUT = Path("artifacts/wm_viz/model_evolve.json")
SRC = Path("agents/wm/tu93_model.py")
SOLS = {int(k): v for k, v in
        json.loads(Path("artifacts/wm_journal/solutions.json").read_text()).items()}

# Versions that can be reconstructed today from the legacy switches. Earlier ones
# (v0-v8) existed only as edits to this file before the switches were added; they
# live in the journals as record, not as runnable code, and are marked as such.
VARIANTS = [
    ("v9", ["drive_all_players", "no_pursuer", "type_render", "no_crossing"],
     "every 3x3 block of 9 is a player; value 13 is scenery"),
    ("v10", ["no_pursuer", "type_render", "no_crossing"],
     "+ the inert look-alike: only the block that responds is a player"),
    ("v11", ["type_render", "no_crossing"],
     "+ the pursuer and its trail"),
    ("v12", [],
     "+ overlap draw order by axis, and a crossed patroller is destroyed"),
]


def g(raw):
    return [a.tolist() for a in raw.frame][-1] if raw.frame else None


def measure(legacy, arc, gid):
    """Replay every level's own solution under one model variant."""
    env = arc.make(gid)
    raw = env.step(GameAction.RESET, data=GameAction.RESET.action_data.model_dump(),
                   reasoning={})
    rows = []
    for level in sorted(SOLS):
        model = tu93_world_model(version=0, legacy=legacy)
        state = model.reconstruct(g(raw))
        hud = ignored_cells(model, g(raw)) or set()
        lv0 = raw.levels_completed
        exact = terminal = 0
        first = None
        for i, n in enumerate(SOLS[level], start=1):
            a = GameAction.from_name(n)
            raw = env.step(a, data=a.action_data.model_dump(), reasoning={})
            try:
                state, _ = model.step(state, Action(n))
                off = diff_cells(model.render(state), g(raw), hud)
            except Exception as exc:              # noqa: BLE001 - a crash is a failure
                first = first or {"step": i, "action": n, "cells": None,
                                  "error": repr(exc)}
                break
            if raw.levels_completed > lv0:
                terminal += 1
            elif off == 0:
                exact += 1
            elif first is None:
                first = {"step": i, "action": n, "cells": off}
        rows.append({"level": level, "exact": exact,
                     "checked": len(SOLS[level]) - terminal,
                     "terminal": terminal, "first_bug": first})
    return rows


def rule_blocks():
    """The current source, split at the numbered rule comments in step()."""
    src = SRC.read_text().splitlines()
    marks = []
    for i, line in enumerate(src):
        t = line.strip()
        if t.startswith("# ") and len(t) > 4 and t[2].isdigit() and "." in t[:6]:
            marks.append(i)
    blocks = []
    for j, start in enumerate(marks):
        end = marks[j + 1] if j + 1 < len(marks) else min(start + 30, len(src))
        blocks.append({"title": src[start].strip().lstrip("# "),
                       "code": "\n".join(src[start:end]).rstrip()})
    return blocks


def main():
    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    gid = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))

    timeline = []
    for level in sorted(SOLS):
        for e in load_journal("tu93", level):
            if e["kind"] in ("author", "refute"):
                timeline.append({k: v for k, v in e.items()
                                 if k not in ("predicted_frame", "actual_frame")})

    matrix = []
    for name, legacy, note in VARIANTS:
        rows = measure(legacy, arc, gid)
        broken = [r["level"] for r in rows if r["first_bug"]]
        matrix.append({"version": name, "legacy": legacy, "note": note,
                       "rows": rows, "levels_broken": broken})
        print(f"{name}: exact on "
              f"{[r['level'] for r in rows if not r['first_bug']]}, "
              f"breaks on {broken}")

    data = {
        "timeline": timeline,
        "matrix": matrix,
        "blocks": rule_blocks(),
        "source_lines": len(SRC.read_text().splitlines()),
        "journal_gap": [lvl for lvl in sorted(SOLS) if not load_journal("tu93", lvl)],
    }
    OUT.write_text(json.dumps(data))
    print(f"\nwrote {OUT} ({OUT.stat().st_size} bytes); "
          f"{len(timeline)} timeline entries, {len(data['blocks'])} rule blocks; "
          f"levels with no journal at all: {data['journal_gap']}")


if __name__ == "__main__":
    main()
