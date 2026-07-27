"""Play a game unattended: observe, propose, certify, plan, execute, advance.

This is the loop with nobody typing. `propose()` is a headless Claude Code process
(agents/wm/brain_claude.py) whose answer is only accepted if it replays every
recorded step exactly, so a wrong proposal costs a retry rather than an action.

Everything is bounded, because the published harnesses are and we were not:

  --budget-x      actions per level, as a multiple of the human baseline (5 is
                  the official leaderboard cutoff)
  --max-brain     brain calls per level; each is a full Claude Code session
  --minutes       wall-clock cap for the whole run
  --levels        stop after this many levels

Resumable by construction: solutions are saved per level as they are cleared, so
re-running continues from the first unsolved level instead of replaying work.

Every brain proposal is journaled — the accepted source with its sha as an
`author` entry, and each rejection with the error that killed it. Those are the
`repair` training pairs, which is the reason this exists: by hand they arrive one
per session, here one per refutation.

Usage:
  autosolve.py --game m0r0 --levels 2 --minutes 60
  autosolve.py --game m0r0 --levels 6 --minutes 480    # overnight
"""
import time
import traceback

import _cli
from agents.wm.backtest import run_backtest
from agents.wm.brain_claude import ClaudeCodeBrain
from agents.wm.core import Action, Status, Timeline, Transition
from agents.wm.harness import (BudgetExceeded, Session, engine_steps,
                               load_solutions, save_solution)
from agents.wm.journal import Journal, summary
from agents.wm.models import has_model, model_for, short_id
from agents.wm.planner import run_bfs
from execute_gated import execute_gated
from explore_level import explore, signature

DIRECTIONAL = ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION7"]
MAZE_ISH = {0, 5, 6}          # too common to be worth a click each


def action_set(grid, avail, max_coords=20):
    """The actions a planner may consider here.

    Some games (ft09, vc33) offer ONLY the coordinate action, so a planner
    restricted to ACTION1-4 cannot act at all — it would search an empty space
    and report "no plan" forever. Coordinates cannot be enumerated either: 64x64
    is 4096 branches per node. So the coordinate action is offered at one
    representative square per distinct value REGION, which is where a click has
    ever meant anything in the games seen so far.
    """
    acts = [Action(f"ACTION{i}") for i in avail if f"ACTION{i}" in DIRECTIONAL]
    if 6 in avail:
        from explore_level import regions
        values = sorted({v for row in grid for v in row} - MAZE_ISH)
        per = max(1, max_coords // max(1, len(values)))
        for v in values:
            for (r, c) in regions(grid, v, limit=per):
                acts.append(Action("ACTION6", x=c, y=r))
    return acts


def sweep_candidates(game, level, base, already, step=6, keep=10):
    """When value-regions miss, find where a click does ANYTHING by sweeping.

    ft09 offers only the coordinate action, and every square its value-regions
    nominated was inert: a brain given that evidence sees a game where nothing
    ever happens and — correctly — refuses to invent dynamics. A coarse sweep
    costs one session per square but answers the only question that matters
    first: where is this game even listening? On ft09 L0, 8 of 100 squares
    responded, all of them in one corner no region had nominated.
    """
    seen = {(a.x, a.y) for a in already}
    hits = []
    for y in range(2, len(base), step):
        for x in range(2, len(base[0]), step):
            if (x, y) in seen:
                continue
            try:
                t = Session.open(game, level)
                t.act("ACTION6", x=x, y=y)
            except Exception:                              # noqa: BLE001
                continue
            if t.dead or t.grid != base:
                hits.append(Action("ACTION6", x=x, y=y))
                if len(hits) >= keep:
                    return hits
    return hits


def gather_evidence(game, level, budget_x):
    """Spend a few real actions to have something to model: each action once from
    the opening frame, then a short walk. Deliberately small — the brain's job is
    to explain what is seen, and more probing is what the loop does after a
    refutation, not before the first model."""
    s = Session.open(game, level, budget_x=budget_x)
    avail = s.raw.available_actions
    acts = action_set(s.grid, avail)

    def probe_each(actions):
        got, live = [], 0
        for act in actions:
            s.reset_to(level)
            init = s.grid
            tl = Timeline(init)
            s.act(act.name, x=act.x, y=act.y)
            after = None if s.dead else s.grid
            tl.record(Transition(step_index=1, action=act, before_frame=init,
                                 after_frame=after,
                                 status=(Status.GAME_OVER if s.dead else Status.RUNNING)))
            got.append(tl)
            if after is None or after != init:
                live += 1
        return got, live

    tls, live = probe_each(acts)
    # A game where every nominated square is inert is not a game with no
    # dynamics; it is a game we are knocking on the wrong door of. Only then is
    # the sweep worth its one-session-per-square price.
    if live == 0 and 6 in avail:
        extra = sweep_candidates(game, level, s.grid, acts)
        if extra:
            more, live = probe_each(extra)
            tls += more
            acts += extra
    # a short walk, so consecutive dynamics are visible and not just single steps
    s.reset_to(level)
    init = s.grid
    tl = Timeline(init)
    prev, lv0 = init, s.raw.levels_completed
    avail_names = [f"ACTION{i}" for i in avail]
    walk = [a for a in ["ACTION1", "ACTION1", "ACTION4", "ACTION2", "ACTION3",
                        "ACTION4", "ACTION1", "ACTION3"] if a in avail_names]
    if not walk:                    # a coordinate-only game: walk the candidates
        walk = [a for a in acts if a.x is not None][:8]
    for i, n in enumerate(walk, start=1):
        n = n if isinstance(n, Action) else Action(n)
        s.act(n.name, x=n.x, y=n.y)
        if s.dead:
            tl.record(Transition(step_index=i, action=n, before_frame=prev,
                                 after_frame=None, status=Status.GAME_OVER))
            break
        cleared = s.raw.levels_completed > lv0
        tl.record(Transition(step_index=i, action=n, before_frame=prev,
                             after_frame=None if cleared else s.grid,
                             status=(Status.LEVEL_COMPLETED if cleared
                                     else Status.RUNNING)))
        prev = s.grid
        if cleared:
            break
    tls.append(tl)
    return tls, s.steps


def solve_level(game, level, brain, J, args, deadline):
    """One level: model it, plan it, run it. Returns True if cleared."""
    print(f"\n=== {game} L{level}")
    tls, spent = gather_evidence(game, level, args.budget_x or None)
    print(f"  evidence: {len(tls)} run(s), {spent} engine steps")
    J.observe(note=f"autosolve: gathered {len(tls)} evidence run(s) on L{level}",
              at=[])

    source = None
    model = None
    if has_model(game):
        try:
            model = model_for(game, version=0)
            reps = [run_backtest(model, tl) for tl in tls]
            bad = next((r for r in reps if not r.ok), None)
            if bad is None:
                print("  carried model already reproduces the evidence")
            else:
                print(f"  carried model refuted: {bad.summary()}")
                J.refute(version="carried", bug=bad.summary(),
                         step_index=getattr(bad.first_mismatch, "step_index", 0),
                         action=str(getattr(bad.first_mismatch, "action", "")),
                         cells_off=getattr(bad.first_mismatch, "changed_cells", 0))
                model = None
        except Exception:                                  # noqa: BLE001
            model = None

    calls = 0
    while model is None and calls < args.max_brain:
        if time.time() > deadline:
            print("  out of wall-clock time before a model was accepted")
            return False
        calls += 1
        print(f"  brain call {calls}/{args.max_brain} ...", flush=True)
        t0 = time.time()
        try:
            rep = None
            model, source, note = brain.propose(tls, source, rep)
            print(f"  accepted after {time.time() - t0:.0f}s: {note}")
            J.author(version=f"brain-{calls}",
                     rules=["proposed by headless Claude Code and verified by replay"],
                     code="proposed source stored with this entry",
                     changed=f"model proposed from {len(tls)} evidence run(s)",
                     because=note, backtest={"note": note})
            # the source itself, so this is a usable training target
            J.note(text=f"BRAIN SOURCE (accepted, {len(source)} chars):\n{source}")
        except Exception as exc:                           # noqa: BLE001
            print(f"  brain failed after {time.time() - t0:.0f}s: "
                  f"{str(exc)[:200]}")
            for pr in brain.log[-args.max_brain:]:
                if not pr.accepted and pr.error:
                    J.note(text=f"BRAIN REJECTED (attempt {pr.attempt}): "
                                f"{pr.error[:600]}")
            return False

    if model is None:
        return False

    s2 = Session.open(game, level, budget_x=args.budget_x or None)
    st0 = model.reconstruct(s2.grid)
    acts2 = action_set(s2.grid, s2.raw.available_actions)
    plan = run_bfs(model, st0, acts2, max_depth=args.max_depth)
    names = list(plan.actions or [])
    J.plan(version=f"brain-{calls}" if calls else "carried",
           actions=[str(x) for x in names],
           stats={"sims": plan.nodes_expanded * max(1, len(acts2)),
                  "nodes": plan.nodes_expanded, "found": plan.found,
                  "plan_len": len(names)})
    if not names:
        # NO PLAN almost always means the win condition is not modelled, not that
        # the level is impossible. Stopping here would strand an unattended run at
        # exactly our measured weakness, so: go and interact, then re-propose with
        # what the interaction found.
        print(f"  NO PLAN — is_goal never true in {plan.nodes_expanded} reachable "
              f"states; exploring for the win condition")
        J.note(text=f"L{level}: no plan; is_goal never true in "
                    f"{plan.nodes_expanded} reachable states. Exploring.")
        s3 = Session.open(game, level)
        results, spent = explore(game, level, [], 6, args.explore_budget, J, 0,
                                 {signature(s3.grid)})
        leads = [r for r in results if r[0] >= 50]
        print(f"  explored {len(results)} interaction(s) for {spent} action(s); "
              f"{len(leads)} lead(s)")
        if not leads or time.time() > deadline:
            J.note(text=f"L{level}: exploration found "
                        f"{len(leads)} lead(s); stopping.")
            return False
        # turn the best leads into evidence and ask again
        extra_tls = []
        for score, label, txt, name, xy, *_ in leads[:3]:
            s4 = Session.open(game, level)
            init4 = s4.grid
            tl4 = Timeline(init4)
            if xy:
                s4.act(name, x=xy[0], y=xy[1])
            else:
                s4.act(name)
            tl4.record(Transition(step_index=1, action=Action(label),
                                  before_frame=init4,
                                  after_frame=None if s4.dead else s4.grid,
                                  status=(Status.GAME_OVER if s4.dead
                                          else Status.RUNNING)))
            extra_tls.append(tl4)
        print(f"  re-proposing with {len(extra_tls)} lead(s) added to the evidence")
        try:
            model, source, note = brain.propose(
                tls + extra_tls, source, None,
                extra=("The planner found no state satisfying is_goal. The extra "
                       "runs at the end are interactions that changed something "
                       "the earlier evidence never showed - they are the best "
                       "candidates for the win condition or for a mechanic the "
                       "model is missing."))
            print(f"  accepted: {note}")
            J.author(version=f"brain-explore", rules=["re-proposed after exploration"],
                     code="proposed source stored with this entry",
                     changed="model re-proposed with exploration leads as evidence",
                     because=note, backtest={"note": note})
            J.note(text=f"BRAIN SOURCE (accepted after exploration, "
                        f"{len(source)} chars):\n{source}")
        except Exception as exc:                          # noqa: BLE001
            print(f"  re-propose failed: {str(exc)[:200]}")
            return False
        st0 = model.reconstruct(Session.open(game, level).grid)
        plan = run_bfs(model, st0, acts2, max_depth=args.max_depth)
        names = list(plan.actions or [])
        if not names:
            print("  still no plan after exploration")
            return False
        s2 = Session.open(game, level, budget_x=args.budget_x or None)
        st0 = model.reconstruct(s2.grid)
        print(f"  plan after exploration: {len(names)} actions")
    print(f"  plan: {len(names)} actions from {plan.nodes_expanded} nodes")

    try:
        res = execute_gated(s2, model, st0, names, journal=J,
                            version=f"brain-{calls}" if calls else "carried")
    except BudgetExceeded as exc:
        print(f"  {exc}")
        J.note(text=f"L{level}: {exc}")
        return False
    J.execute(actions=res["taken"],
              result=("CLEARED" if res["cleared"] else
                      f"aborted at {res['aborted_at']}" if res["aborted_at"]
                      else "no clear"),
              cleared=res["cleared"], env_steps=len(res["taken"]),
              engine_steps=s2.steps)
    if res["cleared"]:
        save_solution(game, level, res["taken"])
        print(f"  CLEARED in {len(res['taken'])} actions — saved")
        return True
    print(f"  not cleared ({len(res['taken'])}/{len(names)} actions spent"
          + (f", {res['saved']} saved by the gate" if res["saved"] else "") + ")")
    return False


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--levels", type=int, default=3)
    p.add_argument("--minutes", type=float, default=60)
    p.add_argument("--max-brain", type=int, default=2)
    p.add_argument("--budget-x", type=float, default=5.0)
    p.add_argument("--max-depth", type=int, default=120)
    p.add_argument("--brain-timeout", type=int, default=900)
    p.add_argument("--explore-budget", type=int, default=60,
                   help="real actions the explorer may spend when there is no plan")
    a = p.parse_args()
    game = short_id(a.game)
    deadline = time.time() + a.minutes * 60
    brain = ClaudeCodeBrain(game=game, max_attempts=2, timeout_s=a.brain_timeout)
    print(f"autosolve {game}: up to {a.levels} level(s), {a.minutes:.0f} min, "
          f"{a.max_brain} brain call(s)/level, {a.budget_x}x action budget")
    print(f"brain workdir: {brain.workdir}")

    start = len(load_solutions(game))
    cleared = 0
    for level in range(start, start + a.levels):
        if time.time() > deadline:
            print("\nwall-clock cap reached")
            break
        J = Journal(game, level)
        try:
            if solve_level(game, level, brain, J, a, deadline):
                cleared += 1
            else:
                print(f"  stopping: L{level} not cleared")
                break
        except Exception:                                  # noqa: BLE001
            print("  run error:\n" + traceback.format_exc(limit=4))
            J.note(text="autosolve aborted with an error:\n"
                        + traceback.format_exc(limit=4))
            break
        print(f"  ledger: {summary(J.entries())}")

    print(f"\ndone: {cleared} level(s) cleared this run, "
          f"{len(load_solutions(game))} total; {engine_steps()} engine steps; "
          f"{time.time() - (deadline - a.minutes * 60):.0f}s elapsed")


if __name__ == "__main__":
    main()
