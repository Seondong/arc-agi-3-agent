"""Per-step census of every moving thing on a level. Black box.

Usage: probe_movers.py --game tu93 --level 6 "ACTION4,ACTION4"

Counting CELLS is not counting entities: two entities on one square render as a
single block and one standing on the goal is hidden under it. That trap produced
a wrong "a patroller was destroyed" reading on tu93 L4, so this prints blocks,
with their facing and notch value, and flags any count that disagrees.

Unknown values are censused too, so a new mechanic shows up as an entity with a
position and a facing the first time it appears.
"""
import _cli
from agents.wm.harness import Session
from agents.wm.journal import Journal

NOTCHES = (15, 11)
MAZE = {0, 2, 5, 6}
PLAYER, GOAL, PLAYER_NOTCH = 9, 14, 4
NOTCH_OFF = {"U": (0, 1), "D": (2, 1), "L": (1, 0), "R": (1, 2)}


def blocks(grid, body, notch_vals):
    cells = {(r, c) for r in range(64) for c in range(64)
             if grid[r][c] == body or grid[r][c] in notch_vals}
    found, claimed = [], set()
    for r, c in sorted(cells):
        if (r, c) in claimed:
            continue
        blk = {(r + i, c + j) for i in range(3) for j in range(3)}
        if not blk <= cells or not any(grid[rr][cc] == body for rr, cc in blk):
            continue
        claimed |= blk
        facing, notch = "?", None
        for rr, cc in blk:
            if grid[rr][cc] in notch_vals:
                notch = grid[rr][cc]
                for f, o in NOTCH_OFF.items():
                    if o == (rr - r, cc - c):
                        facing = f
        found.append((r, c, facing, notch))
    return found


def census(grid):
    present = {v for row in grid for v in row} - MAZE - {GOAL, PLAYER_NOTCH} - set(NOTCHES)
    ents, counts = {}, {}
    for v in sorted(present | {PLAYER}):
        notch = (PLAYER_NOTCH,) if v == PLAYER else NOTCHES
        ents[v] = blocks(grid, v, notch)
        counts[v] = sum(1 for r in range(64) for c in range(64) if grid[r][c] == v)
    hud = sum(1 for c in range(64) if grid[63][c] != 0)
    return {"ents": ents, "counts": counts, "hud": hud}


def fmt(cs):
    out = []
    for v, blks in cs["ents"].items():
        body = " ".join(f"({r},{c},{f}" + (f",notch{n})" if n not in (15, 4, None) else ")")
                        for r, c, f, n in blks)
        tag = "" if cs["counts"][v] == 8 * len(blks) else f"[{cs['counts'][v]}cells]"
        out.append(f"{v}x{len(blks)}{tag}: {body or '-'}")
    return "   ".join(out) + f"   hud={cs['hud']}"


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    _cli.actions_arg(p)
    p.add_argument("--quiet-journal", action="store_true",
                   help="do not record this run (use sparingly: an unlogged probe "
                        "has to be paid for twice if it turns out to matter)")
    a = p.parse_args()

    s = Session.open(a.game, a.level)
    J = None if a.quiet_journal else Journal(a.game, a.level)
    cs = census(s.grid)
    print(f"{a.game} L{a.level} step 0:\n    {fmt(cs)}")

    for i, n in enumerate(_cli.actions(a.actions), start=1):
        at = list(s.actions)
        s.act(n)
        if s.dead:
            print(f"  step {i} {n}: GAME_OVER")
            if J:
                J.probe(actions=[n], hypothesis="per-step census of every mover",
                        observed="GAME_OVER", died=True, env_steps=1, at=at)
            return
        cs = census(s.grid)
        print(f"  step {i} {n} (levels_completed={s.raw.levels_completed}):\n    {fmt(cs)}")
        if J:
            J.probe(actions=[n],
                    hypothesis="how does every moving entity respond to this action?",
                    observed=fmt(cs), died=False, env_steps=1,
                    entities={str(v): b for v, b in cs["ents"].items()}, at=at)


if __name__ == "__main__":
    main()
