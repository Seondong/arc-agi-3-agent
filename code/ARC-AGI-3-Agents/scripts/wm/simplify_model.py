"""Run the simplification pass for a game and report what the evidence forces.

Every rule a game's model carries behind a `legacy` switch is, by construction, a
candidate simplification: switching it off IS the simpler model. So the pass has
candidates for free, and the acceptance test is the one the loop already trusts —
replay every level's own solution and demand cell-exactness.

The output is the useful thing in both directions. A rule that survives being
switched off was never forced by anything we saw, and should go. A rule that
fails comes back with the counterexample that requires it, which is exactly the
(model, bug) half of a repair training pair — obtained without spending a single
environment action beyond the replays.

Usage: simplify_model.py --game tu93 [--journal]
"""
import json

import _cli
from agents.wm.core import Action, Status, Timeline, Transition
from agents.wm.harness import Session, engine_steps, load_solutions
from agents.wm.journal import Journal
from agents.wm.journal import load as load_journal
from agents.wm.models import meta_for, model_for, short_id
from agents.wm.simplify import Candidate, summarise, try_simplifications


def recorded_timelines(game, sols):
    """Every level's own solution, as replayable evidence."""
    out = []
    s = Session.open(game, 0)
    for level in sorted(sols):
        init = s.grid
        tl = Timeline(init)
        prev, lv0 = init, s.raw.levels_completed
        for i, n in enumerate(sols[level], start=1):
            s.act(n)
            if s.dead:
                tl.record(Transition(step_index=i, action=Action(n),
                                     before_frame=prev, after_frame=None,
                                     status=Status.GAME_OVER))
                break
            cur = s.grid
            cleared = s.raw.levels_completed > lv0
            st = Status.LEVEL_COMPLETED if cleared else Status.RUNNING
            # The frame after a level clears is the NEXT level's maze, which no
            # model here claims to predict. Recorded with no frame so the replay
            # checks the status only — otherwise every candidate fails at the
            # same artefact before its real difference is ever reached, which is
            # exactly what the first run of this pass did.
            tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                                 after_frame=None if cleared else cur, status=st))
            prev = cur
            if cleared:
                break
        out.append(tl)
    return out


def probe_timelines(game, levels):
    """Recorded PROBES as evidence, not just solutions.

    The first run of this pass reported that m0r0's hazard rule was unforced —
    correctly, because the saved solutions never walk into a hazard. The evidence
    that forces it lives in the probes, and probes only became replayable when
    the journal started storing `at`, the action prefix that reproduces the frame.
    A simplification pass judged on solutions alone will happily delete every rule
    that only a probe ever exercised.
    """
    out = []
    for level in levels:
        entries = [e for e in load_journal(game, level)
                   if e["kind"] == "probe" and e.get("at") is not None
                   and e.get("actions")]
        runs = {}
        for e in entries:
            runs.setdefault(e.get("run", "?"), []).append(e)
        for run, es in runs.items():
            es.sort(key=lambda x: x["seq"])
            try:
                s = Session.open(game, level)
            except SystemExit:
                continue
            for n in es[0]["at"]:
                s.act(n)
            init = s.grid
            if init is None:
                continue
            tl = Timeline(init)
            prev, lv0, i = init, s.raw.levels_completed, 0
            for e in es:
                for n in e["actions"]:
                    if "@" in n:            # coordinate actions are not modelled
                        prev = None
                        break
                    i += 1
                    s.act(n)
                    if s.dead:
                        tl.record(Transition(step_index=i, action=Action(n),
                                             before_frame=prev, after_frame=None,
                                             status=Status.GAME_OVER))
                        prev = None
                        break
                    cur = s.grid
                    cleared = s.raw.levels_completed > lv0
                    tl.record(Transition(
                        step_index=i, action=Action(n), before_frame=prev,
                        after_frame=None if cleared else cur,
                        status=Status.LEVEL_COMPLETED if cleared else Status.RUNNING))
                    prev = cur
                    if cleared:
                        break
                if prev is None:
                    break
            if len(tl):
                out.append(tl)
    return out


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--journal", action="store_true")
    a = p.parse_args()
    game = short_id(a.game)
    sols = load_solutions(game)
    if not sols:
        raise SystemExit(f"{game}: no solutions yet, so there is no evidence to "
                         f"test a simplification against")

    meta = meta_for(game)
    switches = []
    try:
        mod = __import__(f"agents.wm.models.{game}", fromlist=["x"])
        switches = list(getattr(mod, "LEGACY_SWITCHES", ()))
    except ImportError:
        pass
    if not switches:
        print(f"{game}: the model carries no retired rules behind switches, so "
              f"this pass has nothing to weaken. Add a `legacy` switch when a "
              f"rule is authored and it becomes testable for free.")
        return 0

    try:
        model_for(game, version=0, legacy=[switches[0]])
    except Exception as exc:                            # noqa: BLE001
        raise SystemExit(f"{game}: legacy switches are not usable: {exc!r}")

    print(f"{game}: {len(switches)} rule(s) to test against "
          f"{len(sols)} level(s) of recorded evidence\n")
    timelines = recorded_timelines(game, sols)
    probes = probe_timelines(game, sorted(sols) + [max(sols) + 1])
    timelines += probes
    print(f"evidence: {len(sols)} solution replay(s) + {len(probes)} recorded "
          f"probe run(s)")

    cands = [Candidate(name=f"drop `{sw}`",
                       why=f"is any recorded frame wrong without {sw}?",
                       build=(lambda sw=sw: model_for(game, version=0, legacy=[sw])))
             for sw in switches]
    # and the maximal weakening: everything off at once
    cands.append(Candidate(name="drop ALL retired rules",
                           why="is the earliest model already enough?",
                           build=lambda: model_for(game, version=0, legacy=switches)))

    outcomes = try_simplifications(cands, timelines)
    summary = summarise(outcomes)
    print(f"\n{len(summary['accepted'])} of {summary['tried']} weakenings survived "
          f"all evidence: {summary['accepted'] or 'none'}")
    if summary["accepted"]:
        print("  -> those rules are not forced by anything recorded. Either find "
              "the observation that needs them, or remove them.")
    else:
        print("  -> every rule is forced by a recorded observation; the model "
              "carries no unearned complexity that this pass can see.")
    print(f"({engine_steps()} engine steps, all of it replay)")

    if a.journal:
        J = Journal(game, 0)
        J.note(text=("Simplification pass (scripts/wm/simplify_model.py): each rule kept "
                     "behind a legacy switch was switched OFF and every level's own "
                     "solution replayed through the weaker model. "
                     + json.dumps(summary)[:1200]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
