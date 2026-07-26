"""Probe -> certify -> plan in-model (0 real actions) -> execute -> save, journaling live.

Usage: solve_level.py --game tu93 --level 6 "ACTION4,ACTION4"

Stops at a refutation and refuses to plan. That is by design: an uncertified
model produced a confident plan on tu93 L2 that killed the player.
"""
import _cli
from agents.wm.backtest import run_backtest
from agents.wm.core import Action, Status, Timeline, Transition
from agents.wm.harness import Session, save_solution
from agents.wm.journal import Journal, summary
from agents.wm.models import model_for
from agents.wm.planner import run_bfs

MOVES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]


def entities(state):
    return {k: getattr(state, k) for k in ("players", "guards", "patrols", "pursuers")
            if getattr(state, k, ())}


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    _cli.actions_arg(p)
    p.add_argument("--version", default="v0", help="model label for the journal")
    p.add_argument("--reset", action="store_true",
                   help="erase this level's journal first (rarely what you want)")
    p.add_argument("--max-depth", type=int, default=120)
    a = p.parse_args()

    J = Journal(a.game, a.level, reset=a.reset)
    s = Session.open(a.game, a.level)
    init, lv = s.grid, s.raw.levels_completed
    if lv != a.level:
        print(f"WARNING: expected L{a.level} but levels_completed={lv}")

    model = model_for(a.game, version=0)
    s0 = model.reconstruct(init)
    J.observe(note=f"L{a.level} initial frame; levels_completed={lv}; "
                   f"entities={entities(s0)}", entities={k: list(map(list, v))
                                                         for k, v in entities(s0).items()})
    print(f"L{a.level} init: {entities(s0)}")

    # ---- probe -------------------------------------------------------------
    tl, prev = Timeline(init), init
    for i, n in enumerate(_cli.actions(a.actions), start=1):
        before = s.steps
        s.act(n)
        if s.dead:
            tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                                 after_frame=None, status=Status.GAME_OVER))
            J.probe(actions=[n], hypothesis="does the carried model predict this move?",
                    observed="GAME_OVER", died=True, env_steps=s.steps - before)
            break
        cur = s.grid
        st = Status.LEVEL_COMPLETED if s.raw.levels_completed > lv else Status.RUNNING
        tl.record(Transition(step_index=i, action=Action(n), before_frame=prev,
                             after_frame=cur, status=st))
        J.probe(actions=[n], hypothesis="does the carried model predict this move?",
                observed=str(entities(model.reconstruct(cur))), died=False,
                env_steps=s.steps - before)
        prev = cur

    # ---- certify -----------------------------------------------------------
    rep = run_backtest(model, tl)
    print(f"  backtest: {rep.summary()}")
    if not rep.ok:
        m = rep.first_mismatch
        J.refute(version=a.version, bug=m.summary(), step_index=m.step_index,
                 action=m.action, cells_off=m.changed_cells)
        J.note(text=f"L{a.level}: carried model refuted — investigate before planning.")
        print("  MODEL REFUTED — stopping before planning "
              "(uncertified models must not plan).")
        print("summary:", summary(J.entries()))
        return 1
    J.author(version=a.version, rules=["carried model"], code="see agents/wm/models/",
             changed="none",
             because=f"backtest {rep.matched}/{rep.total} exact on L{a.level} probes",
             backtest={"matched": rep.matched, "total": rep.total, "ok": True})

    # ---- plan in-model (0 real actions) ------------------------------------
    s2 = Session.open(a.game, a.level)
    model2 = model_for(a.game, version=0)
    st0 = model2.reconstruct(s2.grid)
    sims, deaths, inner = [0], [0], model2.step

    def counting(state, act):
        ns, status = inner(state, act)
        sims[0] += 1
        if status == Status.GAME_OVER:
            deaths[0] += 1
        return ns, status

    model2.step = counting
    plan = run_bfs(model2, st0, [Action(x) for x in MOVES], max_depth=a.max_depth)
    model2.step = inner
    names = [x.name for x in (plan.actions or [])]
    J.plan(version=a.version, actions=names,
           stats={"sims": sims[0], "nodes": plan.nodes_expanded, "deaths": deaths[0],
                  "found": plan.found, "plan_len": len(names)})
    print(f"  in-model plan: found={plan.found} len={len(names)} sims={sims[0]} "
          f"nodes={plan.nodes_expanded} imagined_deaths={deaths[0]}")
    if not names:
        J.note(text=f"L{a.level}: no plan found in-model.")
        print("  NO PLAN")
        return 1

    # ---- execute -----------------------------------------------------------
    before, lv2 = s2.steps, s2.raw.levels_completed
    died = False
    for n in names:
        s2.act(n)
        if s2.dead:
            died = True
            break
    cleared = (not died) and s2.raw.levels_completed > lv2
    J.execute(actions=names, result=("DIED" if died else
                                     ("CLEARED" if cleared else "no clear")),
              cleared=cleared, died_at=(len(names) if died else None),
              env_steps=s2.steps - before)
    print(f"  execution: {'DIED' if died else ('L%d CLEARED' % a.level if cleared else 'no clear')}")
    if cleared:
        save_solution(a.game, a.level, names)
        print(f"  saved solution for L{a.level} ({len(names)} actions)")
    print("summary:", summary(J.entries()))
    return 0 if cleared else 1


if __name__ == "__main__":
    raise SystemExit(main())
