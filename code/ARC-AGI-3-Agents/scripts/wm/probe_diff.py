"""First tool for a game with no theory: what does each action actually change?

Usage: probe_diff.py --game ls20 --level 0 --each        # try every action once
       probe_diff.py --game ls20 --level 0 "ACTION3,ACTION3"

For every step it reports how many cells changed, where they are, and which
values appeared and disappeared. That is enough to tell "nothing happened" from
"an object moved" from "the whole screen redrew" before anything is known about
the game, and it is how tu93's player block and 6px step were first found.

`--each` resets between actions so each one is measured from the same frame,
which is the only way the comparison means anything.
"""
from collections import Counter

import _cli
from agents.wm.harness import engine_steps, Session
from agents.wm.journal import Journal

MOVES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7"]


def diff(a, b):
    cells = [(r, c, a[r][c], b[r][c])
             for r in range(len(a)) for c in range(len(a[0])) if a[r][c] != b[r][c]]
    if not cells:
        return {"n": 0}
    rows = [c[0] for c in cells]
    cols = [c[1] for c in cells]
    return {
        "n": len(cells),
        "box": [min(rows), max(rows), min(cols), max(cols)],
        "from": dict(Counter(c[2] for c in cells).most_common()),
        "to": dict(Counter(c[3] for c in cells).most_common()),
    }


def describe(d):
    if not d["n"]:
        return "no change at all — the action did nothing here"
    r0, r1, c0, c1 = d["box"]
    return (f"{d['n']} cells changed in rows {r0}-{r1} cols {c0}-{c1} "
            f"({r1 - r0 + 1}x{c1 - c0 + 1}); values {d['from']} -> {d['to']}")


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    _cli.actions_arg(p)
    p.add_argument("--each", action="store_true",
                   help="reset before each action so all are measured from one frame")
    p.add_argument("--quiet-journal", action="store_true")
    a = p.parse_args()

    J = None if a.quiet_journal else Journal(a.game, a.level)
    if a.each:
        s = Session.open(a.game, a.level)
        base = s.grid
        avail = s.raw.available_actions
        print(f"{a.game} L{a.level}: available_actions={avail}")
        for name in MOVES:
            idx = int(name[-1])
            if idx not in avail:
                continue
            s.reset_to(a.level)
            at = list(s.actions)
            s.act(name)
            if s.dead:
                print(f"  {name}: GAME_OVER")
                if J:
                    J.probe(actions=[name], hypothesis="what does this action change?",
                            observed="GAME_OVER", died=True, env_steps=1, at=at)
                continue
            d = diff(base, s.grid)
            print(f"  {name}: {describe(d)}")
            if J:
                J.probe(actions=[name], hypothesis="what does this action change?",
                        observed=describe(d), died=False, env_steps=1, entities=d, at=at, engine_steps=engine_steps())
        return

    s = Session.open(a.game, a.level)
    prev = s.grid
    for i, n in enumerate(_cli.actions(a.actions), start=1):
        at = list(s.actions)
        s.act(n)
        if s.dead:
            print(f"  step {i} {n}: GAME_OVER")
            if J:
                J.probe(actions=[n], hypothesis="what does this action change?",
                        observed="GAME_OVER", died=True, env_steps=1, at=at)
            return
        d = diff(prev, s.grid)
        print(f"  step {i} {n}: {describe(d)}")
        if J:
            J.probe(actions=[n], hypothesis="what does this action change?",
                    observed=describe(d), died=False, env_steps=1, entities=d, at=at, engine_steps=engine_steps())
        prev = s.grid


def _footer():
    print(f"  ({engine_steps()} engine steps, replays included)")


if __name__ == "__main__":
    main()
    _footer()