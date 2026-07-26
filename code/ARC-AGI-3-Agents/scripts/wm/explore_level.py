"""When the planner finds nothing, go and interact — do not just stop.

`solve_level.py` ends at "NO PLAN" whenever the model's `is_goal` is never true in
the reachable space. That is the right thing to print and the wrong place to
stop: it means the model does not know what winning looks like here, and the only
cure for that is spending real actions to find out. Until this existed, that
search was done by hand, which quietly left the hardest part of the problem —
inferring the goal — outside the loop.

What this does, automatically:

  1. enumerates the model's reachable states (free) and notes what it can NOT
     reach, because a win the model cannot represent is the interesting case
  2. builds a candidate list of interactions the model treats as nothing:
     - every action the model has no dynamics for (ACTION5, ACTION7, ...)
     - ACTION6 on one representative square per distinct value on screen, and
       on every distinct value REGION, since a coordinate action's meaning is
       usually tied to what is under it
     - the same, from a few states deep in the reachable set, because a switch
       may only respond once you are somewhere
  3. runs each from a fresh replay so they are independent, and scores it by
     what actually happened: level cleared > new value appeared > the model
     mispredicted > cells changed at all > nothing
  4. journals every one with its hypothesis, and prints the ranked surprises

A run that finds nothing is still a result: it says these interactions are inert,
which is what lets the next hypothesis be about something else.

Usage: explore_level.py --game m0r0 --level 2 [--depth 6] [--budget 200]
"""
from collections import Counter, deque

import _cli
from agents.wm.core import Action, diff_cells, ignored_cells
from agents.wm.harness import Session, load_solutions
from agents.wm.journal import Journal
from agents.wm.models import has_model, model_for

MOVES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]
MAZE_ISH = {0, 5, 6}          # values too common to be worth clicking one-by-one


def regions(grid, value, limit=4):
    """A few representative squares of one value: one per connected region."""
    seen, out = set(), []
    rows, cols = len(grid), len(grid[0])
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] != value or (r, c) in seen:
                continue
            comp, q = [], deque([(r, c)])
            seen.add((r, c))
            while q:
                cr, cc = q.popleft()
                comp.append((cr, cc))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = cr + dr, cc + dc
                    if (0 <= nr < rows and 0 <= nc < cols and (nr, nc) not in seen
                            and grid[nr][nc] == value):
                        seen.add((nr, nc))
                        q.append((nr, nc))
            out.append(comp[len(comp) // 2])
            if len(out) >= limit:
                return out
    return out


def reachable(model, state, max_states=5000):
    seen = {model.fingerprint(state): []}
    q = deque([state])
    while q and len(seen) < max_states:
        st = q.popleft()
        path = seen[model.fingerprint(st)]
        for a in MOVES:
            nxt, _ = model.step(st, Action(a))
            k = model.fingerprint(nxt)
            if k not in seen:
                seen[k] = path + [a]
                q.append(nxt)
    return seen


def describe(before, after, lv_before, lv_after, dead):
    if dead:
        return "GAME_OVER", 3
    if lv_after > lv_before:
        return "LEVEL CLEARED", 100
    if after is None:
        return "no frame", 0
    d = [(r, c, before[r][c], after[r][c])
         for r in range(len(before)) for c in range(len(before[0]))
         if before[r][c] != after[r][c]]
    if not d:
        return "no change", 0
    # The step counters tick on almost every action and their cells turn to a
    # value that appears nowhere else, so they will masquerade as a discovery
    # unless they are removed BEFORE anything is scored. This ordering is the
    # whole difference between a useful ranking and a list of counter ticks.
    last = len(before) - 1
    body = [x for x in d if x[0] not in (0, last)]
    if not body:
        return f"counter only ({len(d)} cells)", 1
    gone = Counter(x[2] for x in body)
    came = Counter(x[3] for x in body)
    seen_before = {v for row in before for v in row}
    new_values = set(came) - seen_before
    rows = [x[0] for x in body]
    cols = [x[1] for x in body]
    txt = (f"{len(body)} cells rows {min(rows)}-{max(rows)} cols {min(cols)}-{max(cols)}; "
           f"{dict(gone)} -> {dict(came)}")
    if new_values:
        return f"NEW VALUE {sorted(new_values)}: " + txt, 50
    return txt, 10


def signature(grid):
    """A coarse fingerprint of a situation: which values are present, how many of
    each, and where each non-background value sits. Two frames with the same
    signature are the same situation for exploration purposes."""
    if grid is None:
        return ("dead",)
    last = len(grid) - 1
    out = []
    for v in sorted({x for r, row in enumerate(grid) if r not in (0, last) for x in row}):
        cells = [(r, c) for r in range(1, last) for c in range(len(grid[0]))
                 if grid[r][c] == v]
        out.append((v, len(cells), min(cells), max(cells)))
    return tuple(out)


def explore(game, level, prefix, depth, budget, J, round_no, seen_sigs):
    """One round of exploration, starting from `prefix` actions into the level."""
    s = Session.open(game, level)
    for n in prefix:
        s.act(n)
    grid0 = s.grid
    if grid0 is None:
        print("  (dead at the start of this round)")
        return [], 0
    avail = list(s.raw.available_actions)

    modelled_actions, states = set(), {}
    if has_model(game) and not prefix:
        m = model_for(game, version=0)
        st0 = m.reconstruct(grid0)
        for act in MOVES:
            nxt, _ = m.step(st0, Action(act))
            if m.fingerprint(nxt) != m.fingerprint(st0):
                modelled_actions.add(act)
        states = reachable(m, st0)
        goals = sum(1 for k in states if m.is_goal(_rebuild(m, grid0, states[k])))
        print(f"model reaches {len(states)} states with {sorted(modelled_actions)}; "
              f"is_goal true in {goals} of them")
    elif prefix:
        print(f"round {round_no}: exploring from {len(prefix)} actions in "
              f"({' '.join(prefix[-3:])}...)")

    values = sorted({v for row in grid0 for v in row})
    cands = []
    for idx in avail:
        name = f"ACTION{idx}"
        if name in modelled_actions or name == "ACTION6":
            continue
        cands.append((name, None, f"is {name} inert in this state?"))
    if 6 in avail:
        for v in values:
            if v in MAZE_ISH:
                continue
            for (r, c) in regions(grid0, v):
                cands.append(("ACTION6", (c, r),
                              f"does the coordinate action do anything on value {v}?"))
        for (r, c) in [(1, 1), (len(grid0) // 2, len(grid0[0]) // 2)]:
            cands.append(("ACTION6", (c, r), "coordinate action on plain background?"))
    if not prefix:
        for pth in [q for q in states.values() if len(q) == depth][:3]:
            for v in values:
                if v in MAZE_ISH or 6 not in avail:
                    continue
                for (r, c) in regions(grid0, v, limit=1):
                    cands.append(("ACTION6", (c, r),
                                  f"does value {v} respond differently after moving?",
                                  ))

    results, spent = [], 0
    for cand in cands:
        name, xy, hyp = cand[0], cand[1], cand[2]
        if spent + 1 > budget:
            print(f"  (budget reached; {len(cands) - len(results)} candidates not tried)")
            break
        s2 = Session.open(game, level)
        for n in prefix:
            s2.act(n)
        before, lv_before = s2.grid, s2.raw.levels_completed
        if xy is None:
            s2.act(name)
        else:
            s2.act(name, x=xy[0], y=xy[1])
        spent += 1
        after = None if s2.dead else s2.grid
        txt, score = describe(before, after, lv_before, s2.raw.levels_completed, s2.dead)
        # Novelty against everything seen so far in this run, not just against the
        # previous frame — otherwise flipping a switch on and off scores as a
        # discovery twice and the search oscillates instead of going deeper.
        sig = signature(after)
        if sig in seen_sigs and score < 100:
            score = min(score, 2)
            txt = "already seen: " + txt
        label = name + (f"@{xy[0]}:{xy[1]}" if xy else "")
        results.append((score, label, txt, name, xy, sig))
        if J:
            J.probe(actions=prefix + [label], hypothesis=hyp, observed=txt,
                    died=s2.dead, env_steps=1, at=list(prefix))
    results.sort(key=lambda t: -t[0])
    return results, spent


def main():
    p = _cli.parser(__doc__)
    _cli.level_arg(p, default=0)
    p.add_argument("--follow", type=int, default=0,
                   help="rounds to follow the best lead into the state it opens")
    p.add_argument("--depth", type=int, default=6,
                   help="how deep into the reachable set to try interactions from")
    p.add_argument("--budget", type=int, default=200,
                   help="maximum real actions to spend")
    p.add_argument("--quiet-journal", action="store_true")
    a = p.parse_args()

    J = None if a.quiet_journal else Journal(a.game, a.level)
    prefix, total, best_overall = [], 0, None
    s_init = Session.open(a.game, a.level)
    seen_sigs = {signature(s_init.grid)}
    for rnd in range(a.follow + 1):
        results, spent = explore(a.game, a.level, prefix, a.depth,
                                 a.budget - total, J, rnd, seen_sigs)
        total += spent
        if not results:
            break
        print(f"round {rnd}: most surprising first")
        for score, label, txt, *_ in results[:8]:
            mark = "***" if score >= 50 else ("  *" if score >= 10 else "   ")
            print(f" {mark} {label:<22} {txt[:104]}")
        inert = sum(1 for r in results if r[0] <= 1)
        print(f"  {len(results)} tried, {spent} real actions, {inert} inert\n")
        for r in results:
            seen_sigs.add(r[5])
        best = results[0]
        if best[0] >= 100:
            print(f"CLEARED by {best[1]}")
            best_overall = best
            break
        if best[0] < 50 or rnd == a.follow:
            best_overall = best_overall or best
            break
        # follow the lead: everything after this round starts from it
        prefix = prefix + [best[1]]
        best_overall = best

    print(f"total {total} real actions spent")
    if best_overall:
        print(f"BEST LEAD: {' -> '.join(prefix) or best_overall[1]}  ::  {best_overall[2]}")
    if J:
        J.note(text=(f"Automatic exploration of L{a.level}: {total} real actions across "
                     f"{a.follow + 1} round(s). "
                     + (f"Best lead: {best_overall[1]} -> {best_overall[2]}"
                        if best_overall else "nothing tried.")))


def _rebuild(model, grid, path):
    st = model.reconstruct(grid)
    for n in path:
        st, _ = model.step(st, Action(n))
    return st


if __name__ == "__main__":
    main()
