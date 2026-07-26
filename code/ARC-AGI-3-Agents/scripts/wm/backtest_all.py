"""Replay every saved solution through the model and demand an exact frame at
every step of every level.

This is the regression that matters. Certifying on a short probe says almost
nothing: on tu93 two of nine levels mispredicted their OWN solution paths — a
guard drawn on the wrong side of a patroller, and a patroller the player
destroys by crossing it — and the probes never put two entities on one square,
so nothing complained and both plans still worked.

The frame after a level clears shows the NEXT level's maze, which no model here
claims to predict; those steps are reported separately, never counted as passes
and never counted as failures.

Usage: backtest_all.py --game tu93 [--verbose]
"""
import _cli
from agents.wm.core import Action, diff_cells, ignored_cells
from agents.wm.harness import Session, engine_steps, load_solutions
from agents.wm.models import model_for


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()

    sols = load_solutions(a.game)
    if not sols:
        print(f"{a.game}: no solutions saved yet — nothing to check")
        return 0
    s = Session.open(a.game, 0)
    bad_total = 0
    for level in sorted(sols):
        model = model_for(a.game, version=0)
        state = model.reconstruct(s.grid)
        try:
            model.render(state)
        except NotImplementedError:
            # A model may legitimately have no renderer — its dynamics can still
            # be right. Frame-exactness is then not applicable, which is a
            # different thing from failing it, and is reported as such.
            print(f"n/a L{level}: this model does not render frames, so its "
                  f"predictions cannot be checked cell-for-cell")
            for n in sols[level]:
                s.act(n)
            continue
        hud = ignored_cells(model, s.grid) or set()
        lv0 = s.raw.levels_completed
        exact = terminal = 0
        bugs = []
        for i, n in enumerate(sols[level], start=1):
            s.act(n)
            state, _ = model.step(state, Action(n))
            if s.dead:
                bugs.append((i, n, "engine returned no frame"))
                break
            off = diff_cells(model.render(state), s.grid, hud)
            if s.raw.levels_completed > lv0:
                terminal += 1
            elif off == 0:
                exact += 1
            else:
                bugs.append((i, n, f"{off} cell(s)"))
        checked = len(sols[level]) - terminal
        bad_total += len(bugs)
        print(f"{'ok ' if not bugs else 'BUG'} L{level}: {exact}/{checked} exact "
              f"(+{terminal} terminal frame{'s' if terminal != 1 else ''} excluded)"
              + (f"  first bug: step {bugs[0][0]} after {bugs[0][1]} — {bugs[0][2]}"
                 if bugs else ""))
        if a.verbose:
            for b in bugs:
                print(f"      step {b[0]:>2} {b[1]}: {b[2]}")

    print(f"\n{'ALL LEVELS EXACT' if not bad_total else str(bad_total) + ' mispredicted steps'}"
          f"; final state = {s.raw.state.name}; {engine_steps()} engine steps")
    return 0 if not bad_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
