"""What has NOT been tried on this level.

The published harness handles being stuck with a prompt: after a level has eaten
enough actions it asks the agent whether it is missing a simple visual cue. That
is the right instinct and the wrong mechanism for us — a prompt asks the same
mind that is already stuck. Everything that question wants is computable from the
journal and the model, so this computes it instead of asking.

It reports, for one level:
  actions never taken at all
  values on screen never clicked with the coordinate action
  squares the model says are reachable that no probe ever visited
  rules the model itself marks UNDER-DETERMINED in its own docstring
  what the journal's open notes say

Written after two demonstrated tunnel-vision failures: on m0r0 L2 the answer was
an action already written off as inert, and on sk48 L1 the search kept re-testing
extension after extension had been ruled out at every row.

Usage: stuck_report.py --game m0r0 --level 2
"""
import re
from collections import deque

import _cli
from agents.wm.core import Action
from agents.wm.harness import Session
from agents.wm.journal import load as load_journal
from agents.wm.models import MODELS, has_model, meta_for, model_for, short_id

MOVES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]


def tried_actions(entries):
    out = set()
    for e in entries:
        for a in (e.get("actions") or []):
            out.add(a.split("@")[0])
    return out


def clicked_values(entries, grid):
    """Which values a coordinate action has actually been aimed at."""
    hit = set()
    for e in entries:
        for a in (e.get("actions") or []):
            if "@" not in a:
                continue
            try:
                x, y = (int(v) for v in a.split("@", 1)[1].split(":"))
            except ValueError:
                continue
            if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
                hit.add(grid[y][x])
    return hit


def visited(entries):
    out = set()
    for e in entries:
        for group in (e.get("entities") or {}).values():
            if isinstance(group, list):
                for b in group:
                    if isinstance(b, list) and len(b) >= 2 and all(
                            isinstance(v, int) for v in b[:2]):
                        out.add((b[0], b[1]))
    return out


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    a = p.parse_args()
    game = short_id(a.game)

    s = Session.open(game, a.level)
    grid = s.grid
    avail = [f"ACTION{i}" for i in s.raw.available_actions]
    entries = load_journal(game, a.level)
    print(f"{game} L{a.level}: {len(entries)} journal entries, "
          f"available actions {avail}\n")

    used = tried_actions(entries)
    never = [x for x in avail if x not in used]
    print(f"actions never taken here: {never or 'none — all have been tried'}")

    if "ACTION6" in avail:
        aimed = clicked_values(entries, grid)
        values = sorted({v for row in grid for v in row})
        unaimed = [v for v in values if v not in aimed]
        print(f"values never clicked with ACTION6: {unaimed}")
        print(f"   (values on screen: {values}; already aimed at: {sorted(aimed)})")

    if has_model(game):
        m = model_for(game, version=0)
        st0 = m.reconstruct(grid)
        seen = {m.fingerprint(st0): []}
        q = deque([st0])
        while q and len(seen) < 20000:
            st = q.popleft()
            for act in MOVES:
                nx, _ = m.step(st, Action(act))
                k = m.fingerprint(nx)
                if k not in seen:
                    seen[k] = seen[m.fingerprint(st)] + [act]
                    q.append(nx)
        squares = set()
        for k in seen:
            for e in (k if isinstance(k, tuple) else ()):
                if isinstance(e, tuple) and len(e) >= 2 and all(
                        isinstance(v, int) for v in e[:2]):
                    squares.add(e[:2])
        been = visited(entries)
        unvisited = sorted(squares - been)
        print(f"\nmodel says {len(seen)} states are reachable; of the "
              f"{len(squares)} squares they cover, {len(unvisited)} were never "
              f"in any recorded observation")
        if unvisited:
            print(f"   first few: {unvisited[:10]}")
        print(f"is_goal true in {sum(1 for k in seen if m.is_goal(_rebuild(m, grid, seen[k])))}"
              f" of them")

        src = meta_for(game).get("source", "")
        try:
            text = open(src).read()
        except OSError:
            text = ""
        flags = [ln.strip() for ln in text.splitlines() if "UNDER-DETERMINED" in ln
                 or "UNDERIVED" in ln]
        if flags:
            print("\nrules the model itself flags as not pinned down:")
            for f in flags:
                print("   -", f.lstrip("# "))
    else:
        print("\n(no model for this game yet)")

    opens = [e for e in entries if e["kind"] == "note"
             and re.search(r"OPEN|open question|unsolved|NOT solved|blocked",
                           e.get("text", ""), re.I)]
    if opens:
        print(f"\nopen notes in the journal ({len(opens)}):")
        for e in opens[-3:]:
            print("   -", e["text"][:220].replace("\n", " "))


def _rebuild(model, grid, path):
    st = model.reconstruct(grid)
    for n in path:
        st, _ = model.step(st, Action(n))
    return st


if __name__ == "__main__":
    main()
