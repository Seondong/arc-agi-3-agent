"""Build one game's page data. Works for any game with a model — no per-game code.

Writes artifacts/wm_viz/<game>/data/:

  index.json          per-level summary + totals, with the caveat on what the
                      totals can and cannot count
  level_<n>.json      for every level: the saved solution replayed for real with
                      the model's prediction beside it, the FULL in-model search
                      that produced the plan, the cost ledger, the journal
  model_evolve.json   the refute/author timeline from the journals, plus every
                      retired model version reconstructed and re-run against
                      every level

and refreshes artifacts/wm_viz/games.json, the root index of games.

Game-specific facts (level mechanics, version labels, legacy switches) come from
the game's own model module, so this file never grows a per-game branch.

Usage: gen_site.py --game tu93 [--skip-matrix]
"""
import json
from collections import deque

import _cli
from agents.wm.core import Action, Status, diff_cells, ignored_cells
from agents.wm.harness import (Session, bounds, data_dir, load_solutions,
                               journal_dir, viz_dir)
from agents.wm.journal import load as load_journal
from agents.wm.journal import summary
from agents.wm.models import MODELS, has_model, meta_for, model_for, short_id
from agents.wm.planner import run_bfs

MOVES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]
MAX_LOG = 20000            # log everything below this; above it, say what was dropped
def _first(state):
    """The position the search log draws — the first entity group's first member.

    Some games have no entity groups at all: sk48's state is two integers, so
    there is nothing on a grid to draw. The log still records the transition;
    only the position is absent.
    """
    for group in ents(state).values():
        if group:
            return list(group[0][:2])
    import dataclasses
    nums = [getattr(state, f.name) for f in dataclasses.fields(state)
            if isinstance(getattr(state, f.name), int)]
    return nums[:2] if len(nums) >= 2 else None


def ents(state):
    """Whatever entity groups this game's state carries — no per-game field names."""
    import dataclasses
    out = {}
    for fld in dataclasses.fields(state):
        v = getattr(state, fld.name)
        if isinstance(v, tuple) and v and all(isinstance(x, tuple) for x in v):
            out[fld.name] = [list(e[:3]) for e in v]
    return out


def logged_bfs(model, start, max_depth=120):
    """planner.run_bfs, mirrored, logging every simulated interaction.

    Kept honest by comparing its plan with the real planner's; a mismatch means
    this log is lying and must be fixed, not silenced.
    """
    log, n, deaths, revisits, frontier, blocked = [], 0, 0, 0, 0, 0
    stats = lambda expanded: {"nodes": expanded, "sims": n, "deaths": deaths,  # noqa: E731
                              "revisits": revisits, "frontier": frontier,
                              "blocked": blocked}
    if model.is_goal(start):
        return [], log, stats(0)
    visited = {model.fingerprint(start)}
    q = deque([(start, [])])
    expanded = 0
    while q:
        state, path = q.popleft()
        if len(path) >= max_depth:
            continue
        expanded += 1
        for ai, a in enumerate(MOVES):
            n += 1
            nxt, status = model.step(state, Action(a))
            here, there = _first(state), _first(nxt)
            rec = {"n": n, "d": len(path) + 1, "a": ai,
                   "f": list(here) if here is not None else None}
            if status == Status.GAME_OVER:
                deaths += 1
                rec.update(o="death", t=None)
            elif status == Status.LEVEL_COMPLETED or model.is_goal(nxt):
                rec.update(o="goal", t=list(there) if there is not None else None)
                if len(log) < MAX_LOG:
                    log.append(rec)
                return path + [Action(a)], log, stats(expanded)
            else:
                key = model.fingerprint(nxt)
                if key in visited:
                    if here == there:
                        blocked += 1
                        rec.update(o="blocked", t=list(there) if there is not None else None)
                    else:
                        revisits += 1
                        rec.update(o="revisit", t=list(there) if there is not None else None)
                else:
                    visited.add(key)
                    q.append((nxt, path + [Action(a)]))
                    frontier += 1
                    rec.update(o="frontier", t=list(there) if there is not None else None)
            if len(log) < MAX_LOG:
                log.append(rec)
    return [], log, stats(expanded)


def build_level(game, level, sols, meta):
    s = Session.open(game, level)
    init = s.grid
    r0, r1, c0, c1 = bounds(init)
    crop = lambda gr: [row[c0:c1 + 1] for row in gr[r0:r1 + 1]]  # noqa: E731
    lv0 = s.raw.levels_completed

    model = model_for(game, version=0)
    state = model.reconstruct(init)
    hud = ignored_cells(model, init) or set()

    replay = [{"k": 0, "action": None, "grid": crop(init), "pred_diff": [],
               "cells_off": 0, "status": "RUNNING", "terminal": False,
               "ents": ents(state)}]
    # A model may legitimately not render — sk48's dynamics are enough to plan
    # with but its frame is not reconstructed pixel-for-pixel. Then the replay
    # still shows what happened, with the prediction column marked unavailable
    # rather than the whole page failing to build.
    renders = True
    try:
        model.render(state)
    except NotImplementedError:
        renders = False

    for i, n in enumerate(sols[level], start=1):
        s.act(n)
        state, _ = model.step(state, Action(n))
        actual = None if s.dead else s.grid
        pred = model.render(state) if renders else None
        cleared = (actual is not None) and s.raw.levels_completed > lv0
        diff = []
        if actual is not None and pred is not None:
            for r in range(len(actual)):
                for c in range(len(actual[0])):
                    if (r, c) not in hud and pred[r][c] != actual[r][c]:
                        diff.append([r - r0, c - c0, pred[r][c]])
        replay.append({
            "k": i, "action": n,
            "grid": crop(actual) if actual is not None else None,
            "pred_diff": [d for d in diff
                          if 0 <= d[0] <= r1 - r0 and 0 <= d[1] <= c1 - c0],
            "cells_off": len(diff) if renders else None,
            "status": ("GAME_OVER" if actual is None
                       else "LEVEL_COMPLETED" if cleared else "RUNNING"),
            # The frame after a level clears is the NEXT level's maze, which this
            # model does not claim to predict. Flagged, not hidden, not scored.
            "terminal": bool(cleared),
            "ents": ents(state),
        })

    s2 = Session.open(game, level)
    m2 = model_for(game, version=0)
    plan, log, stats = logged_bfs(m2, m2.reconstruct(s2.grid))
    names = [a.name for a in plan]
    ref_model = model_for(game, version=0)
    ref = run_bfs(ref_model, ref_model.reconstruct(s2.grid),
                  [Action(x) for x in MOVES], max_depth=120)
    j = load_journal(short_id(game), level)
    return {
        "game": short_id(game), "level": level, "origin": [r0, c0],
        "version": meta.get("versions", {}).get(level, "—"),
        "mechanic": meta.get("mechanics", {}).get(level, ""),
        "solution": sols[level], "solution_len": len(sols[level]),
        "replay": replay,
        "search": log, "search_stats": stats,
        "search_truncated": stats["sims"] > MAX_LOG,
        "search_plan": names,
        "mirror_ok": names == [a.name for a in ref.actions],
        "ledger": summary(j) if j else {},
        "journal": [{k: v for k, v in e.items()
                     if k not in ("frame", "predicted_frame", "actual_frame",
                                  "search_log")} for e in j],
        "renders": renders,
        "fidelity": {
            "steps": len(replay) - 1,
            "exact": sum(1 for f in replay[1:]
                         if f["cells_off"] == 0 and not f["terminal"]),
            "terminal_excluded": sum(1 for f in replay[1:] if f["terminal"]),
            # A model with no renderer cannot be frame-checked at all; saying
            # "0 exact" would read as a failure rather than as not applicable.
            "checkable": renders,
        },
    }


def build_matrix(game, sols, meta):
    """Every retired model version, re-run against every level's own solution."""
    rows_by_version = []
    for name, legacy, note in meta.get("legacy_variants", []):
        s = Session.open(game, 0)
        rows = []
        for level in sorted(sols):
            model = model_for(game, version=0, legacy=legacy)
            state = model.reconstruct(s.grid)
            try:
                model.render(state)
            except NotImplementedError:
                rows.append({"level": level, "exact": 0, "checked": 0,
                             "terminal": 0, "first_bug": None})
                for n in sols[level]:
                    s.act(n)
                continue
            hud = ignored_cells(model, s.grid) or set()
            lv0 = s.raw.levels_completed
            exact = terminal = 0
            first = None
            for i, n in enumerate(sols[level], start=1):
                s.act(n)
                try:
                    state, _ = model.step(state, Action(n))
                    off = diff_cells(model.render(state), s.grid, hud)
                except Exception as exc:            # noqa: BLE001 - a crash is a failure
                    first = first or {"step": i, "action": n, "cells": None,
                                      "error": repr(exc)}
                    break
                if s.raw.levels_completed > lv0:
                    terminal += 1
                elif off == 0:
                    exact += 1
                elif first is None:
                    first = {"step": i, "action": n, "cells": off}
            rows.append({"level": level, "exact": exact,
                         "checked": len(sols[level]) - terminal,
                         "terminal": terminal, "first_bug": first})
        broken = [r["level"] for r in rows if r["first_bug"]]
        rows_by_version.append({"version": name, "legacy": legacy, "note": note,
                                "rows": rows, "levels_broken": broken})
        print(f"  {name}: breaks on {broken or 'nothing'}")
    return rows_by_version


def rule_blocks(meta):
    """The model's source, split at the numbered rule comments in step()."""
    from pathlib import Path
    src_path = Path(meta.get("source", ""))
    if not src_path.exists():
        return []
    src = src_path.read_text().splitlines()
    marks = [i for i, line in enumerate(src)
             if (t := line.strip()).startswith("# ") and len(t) > 4
             and t[2].isdigit() and "." in t[:6]]
    blocks = []
    for j, start in enumerate(marks):
        end = marks[j + 1] if j + 1 < len(marks) else min(start + 30, len(src))
        blocks.append({"title": src[start].strip().lstrip("# "),
                       "code": "\n".join(src[start:end]).rstrip()})
    return blocks


def refresh_games_index():
    """The root index: every game with a model OR a journal, and how far it got.

    A game that has been opened but not yet modelled belongs here too — leaving it
    out would make the site look like every game attempted was a game solved.
    """
    from agents.wm.harness import JOURNAL_ROOT
    started = {d.name for d in JOURNAL_ROOT.iterdir() if d.is_dir()} if \
        JOURNAL_ROOT.exists() else set()
    out = []
    for key in sorted(set(MODELS) | started):
        sols = load_solutions(key)
        meta = meta_for(key)
        idx_path = data_dir(key) / "index.json"
        idx = json.loads(idx_path.read_text()) if idx_path.exists() else {}
        out.append({
            "game": key, "title": meta.get("title", key), "blurb": meta.get("blurb", ""),
            "levels_solved": len(sols),
            "total_actions": sum(len(v) for v in sols.values()),
            "real_deaths": idx.get("total_real_deaths"),
            "probe_steps": idx.get("total_probe_steps"),
            "sims": idx.get("total_sims"),
            "imagined_deaths": idx.get("total_imagined_deaths"),
            "journal_files": len(list(journal_dir(key).glob("L*.jsonl"))),
            "deep_dives": [{"href": h, "level": lv, "title": t}
                           for h, lv, t in meta.get("deep_dives", [])],
            "has_pages": (viz_dir(key) / "paper.html").exists(),
            "has_model": key in MODELS,
        })
    (viz_dir("").parent / "wm_viz" / "games.json").write_text(json.dumps({"games": out}))
    return out


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--skip-matrix", action="store_true")
    a = p.parse_args()
    game = short_id(a.game)
    if not has_model(game):
        raise SystemExit(f"no model for {game}; nothing to build")
    sols = load_solutions(game)
    meta = meta_for(game)
    out = data_dir(game)
    out.mkdir(parents=True, exist_ok=True)

    index = []
    for level in sorted(sols):
        d = build_level(game, level, sols, meta)
        path = out / f"level_{level}.json"
        path.write_text(json.dumps(d))
        f = d["fidelity"]
        index.append({
            "level": level, "version": d["version"], "mechanic": d["mechanic"],
            "solution_len": d["solution_len"], "ledger": d["ledger"],
            "search_stats": d["search_stats"], "fidelity": f,
            "journal_entries": len(d["journal"]), "bytes": path.stat().st_size,
        })
        print(f"L{level}: {d['version']:>3}  solve {d['solution_len']:>2}  "
              f"fidelity {f['exact']}/{f['steps'] - f['terminal_excluded']} exact  "
              f"search {d['search_stats']['sims']:>5} sims / "
              f"{d['search_stats']['deaths']:>3} imagined deaths  "
              f"mirror={'ok' if d['mirror_ok'] else 'DIVERGED'}  "
              f"journal {len(d['journal']):>2}")

    gap = [i["level"] for i in index if i["journal_entries"] == 0]
    (out / "index.json").write_text(json.dumps({
        "game": game, "title": meta.get("title", game), "blurb": meta.get("blurb", ""),
        "levels": index,
        "journal_gap": gap,
        # Cost totals are summed from the journals, so levels that predate the
        # journal contribute nothing. Saying the sum without saying that would
        # under-count real deaths that were genuinely paid.
        "totals_caveat": (
            f"probe steps and real deaths are summed from the journals; "
            f"level(s) {gap} predate the journal and contribute 0 to those totals"
            if gap else
            "probe steps and real deaths are summed from the journals, which cover "
            "every level of this game"),
        "total_actions": sum(i["solution_len"] for i in index),
        "total_real_deaths": sum(i["ledger"].get("real_deaths", 0) for i in index),
        "total_probe_steps": sum(i["ledger"].get("probe_env_steps", 0) for i in index),
        "total_sims": sum(i["search_stats"]["sims"] for i in index),
        "total_imagined_deaths": sum(i["search_stats"]["deaths"] for i in index),
    }))

    timeline = []
    for level in sorted(sols):
        for e in load_journal(game, level):
            if e["kind"] in ("author", "refute"):
                timeline.append({k: v for k, v in e.items()
                                 if k not in ("predicted_frame", "actual_frame")})
    matrix = [] if a.skip_matrix else build_matrix(game, sols, meta)
    (out / "model_evolve.json").write_text(json.dumps({
        "game": game, "timeline": timeline, "matrix": matrix,
        "blocks": rule_blocks(meta), "journal_gap": gap,
        "source": meta.get("source", ""),
    }))

    games = refresh_games_index()
    print(f"\nwrote {out}/ ({len(index)} levels) and games.json "
          f"({len(games)} game(s) with a model)")


if __name__ == "__main__":
    main()
