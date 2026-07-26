"""Look at a level's opening frame without acting on it. Black box.

Usage: observe_level.py --game tu93 --level 4

Prints the value inventory, flags values never seen before in this game, finds
every 3x3 block, and draws the interesting rectangle. For a game with no model
yet this is the only thing that works, and it is where every game starts.
"""
from collections import Counter

import _cli
from agents.wm.harness import Session, bounds
from agents.wm.models import has_model, model_for

CH = {0: '·', 1: '░', 2: '▒', 3: '▓', 4: '◆', 5: '█', 6: '.', 7: '◇', 8: '♥',
      9: '@', 10: '◈', 11: '♠', 12: '◘', 13: '?', 14: '⊕', 15: '♢'}
MAZE = {0, 2, 5, 6}


def blocks(grid, val):
    cells = {(r, c) for r in range(len(grid)) for c in range(len(grid[0]))
             if grid[r][c] == val}
    tls, claimed = [], set()
    for r, c in sorted(cells):
        if (r, c) in claimed:
            continue
        b = {(r + i, c + j) for i in range(3) for j in range(3)}
        if b <= cells:
            claimed |= b
            tls.append((r, c))
    return tls, len(cells)


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    a = p.parse_args()

    s = Session.open(a.game, a.level)
    print(f"{a.game} L{a.level}: levels_completed={s.raw.levels_completed} "
          f"state={s.raw.state.name} available_actions={s.raw.available_actions}")
    grid = s.grid
    if grid is None:
        print("no frame returned")
        return
    inv = Counter(v for row in grid for v in row)
    print("inventory:", dict(sorted(inv.items())))

    if has_model(a.game):
        st = model_for(a.game, version=0).reconstruct(grid)
        print("model sees:", {k: getattr(st, k) for k in
                              ("players", "guards", "patrols", "pursuers")
                              if getattr(st, k, ())})
    else:
        print("no world model for this game yet — everything below is raw observation")

    for v in sorted(inv):
        if v in MAZE:
            continue
        tls, n = blocks(grid, v)
        print(f"  value {v:>2}: {n:>4} cells, 3x3 blocks at {tls}")

    r0, r1, c0, c1 = bounds(grid)
    print(f"\nregion rows {r0}-{r1} cols {c0}-{c1}:")
    print("     " + "".join(f"{c % 10}" for c in range(c0, c1 + 1)))
    for r in range(r0, r1 + 1):
        print(f"R{r:02d}  " + "".join(CH.get(grid[r][c], '?') for c in range(c0, c1 + 1)))


if __name__ == "__main__":
    main()
