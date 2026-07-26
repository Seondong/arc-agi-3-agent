"""Replay every saved solution from RESET and report the result.

No model, no planning — just the stored action sequences against a fresh engine,
so "this game is solved" is something a reader can re-run instead of trust.

Usage: verify_game.py --game tu93
"""
import _cli
from agents.wm.harness import Session, engine_steps, load_solutions


def main():
    p = _cli.parser(__doc__)
    a = p.parse_args()
    sols = load_solutions(a.game)
    if not sols:
        print(f"{a.game}: no solutions saved yet")
        return 1
    s = Session.open(a.game, 0)
    total = 0
    for level in sorted(sols):
        before = s.raw.levels_completed
        for n in sols[level]:
            s.act(n)
            total += 1
            if s.dead:
                print(f"L{level}: DIED after {len(sols[level])} actions")
                return 1
        ok = s.raw.levels_completed > before
        print(f"L{level}: {len(sols[level]):3d} actions -> "
              f"{'CLEARED' if ok else 'NOT CLEARED'} "
              f"(levels_completed={s.raw.levels_completed}, state={s.raw.state.name})")
    print(f"\ntotal {total} actions across {len(sols)} levels; "
          f"final state = {s.raw.state.name}; {engine_steps()} engine steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
