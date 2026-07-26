"""Turn the journals into training pairs for distilling this loop into a small model.

The journals are an audit trail first and a dataset second. This script reads
them, replays the engine to recover the frames they refer to, and emits typed
examples — and, just as importantly, it reports every example it could NOT build
and why. A silent exporter would make a record with holes look like a dataset
without them.

Pair types (each is one capability the small model has to learn):

  analyse   frame                      -> what is on screen: entities, values, structure
  probe     frame + open question      -> which actions to spend, and the hypothesis
  predict   frame + action             -> the next frame (as a cell diff)
  repair    model source + pointed bug -> the rewritten source and why
  plan      frame + certified model    -> the action sequence that clears the level

`predict` is recoverable for free from solutions.json because the engine is
deterministic, so it is the bulk. `repair` is the scarce, valuable one: it needs
the model's source as it was at the time, which only entries written after that
was instrumented actually carry.

Usage: export_dataset.py --game tu93 [--out artifacts/wm_dataset] [--all-games]
"""
import json
from pathlib import Path

import _cli
from agents.wm.core import Action
from agents.wm.harness import (JOURNAL_ROOT, Session, load_solutions, prefix_for)
from agents.wm.journal import load as load_journal
from agents.wm.models import has_model, model_for, short_id

OUT_ROOT = Path("artifacts/wm_dataset")


def grid_diff(a, b):
    return [[r, c, b[r][c]] for r in range(len(a)) for c in range(len(a[0]))
            if a[r][c] != b[r][c]]


def replay(game, level, actions):
    """The frame reached by `actions` from the start of `level`. Deterministic."""
    s = Session.open(game, level)
    frames = [s.grid]
    for n in actions:
        s.act(n)
        frames.append(None if s.dead else s.grid)
    return frames


def verify(entry, grid, game):
    """Does `grid` match what this entry recorded? Used to RECONSTRUCT the replay
    key of entries written before the journal stored one.

    The journal is append-only, so nothing is rewritten: the reconstruction lives
    here, and an example built this way is labelled `derived` rather than passed
    off as recorded. A candidate is accepted only on an exact match, so a wrong
    guess becomes a gap instead of a lie.
    """
    if grid is None:
        return False
    ents = entry.get("entities") or {}
    checked = False
    for key, val in ents.items():
        if not str(key).lstrip("-").isdigit():
            continue                       # not the {value: [[r,c,...]]} shape
        v = int(key)
        for blk in val:
            if not isinstance(blk, (list, tuple)) or len(blk) < 2:
                continue
            r, c = blk[0], blk[1]
            if not (0 <= r < len(grid) and 0 <= c < len(grid[0])):
                return False
            if grid[r][c] != v:
                return False
            checked = True
    if checked:
        return True
    # observe entries name their entities ({"player": [r, c]}) instead of keying
    # by value. They are written the moment a level is opened, so the only
    # candidate frame is the level's first — check that every coordinate given is
    # the top-left of a real 3x3 block there, which a wrong frame would fail.
    if entry["kind"] == "observe" and ents:
        coords = [v for v in ents.values()
                  if isinstance(v, (list, tuple)) and len(v) == 2
                  and all(isinstance(x, int) for x in v)]
        if coords:
            for r, c in coords:
                if not (0 <= r < len(grid) - 2 and 0 <= c < len(grid[0]) - 2):
                    return False
                blk = {grid[r + i][c + j] for i in range(3) for j in range(3)}
                if len(blk) > 2 or blk <= {0, 2, 5, 6}:
                    return False           # not a solid entity block
            return True
    # fall back: the entry recorded the model's own view as a string
    obs = entry.get("observed") or ""
    if obs and has_model(game):
        st = model_for(game, version=0).reconstruct(grid)
        seen = {k: getattr(st, k, ()) for k in
                ("players", "guards", "patrols", "pursuers")}
        return str({k: v for k, v in seen.items() if v}) == obs
    return False


def reconstruct_keys(game, level, entries):
    """Infer each entry's replay key by replaying candidates and checking them.

    Entries from several script runs are interleaved in one file with no run
    marker (that is the gap this exists to close). Walk them in order, extend the
    current run's prefix, and when the replay stops matching what was recorded,
    assume a new run started and try again from empty.
    """
    keys, prefix = {}, []
    for e in entries:
        if e.get("at") is not None or e["kind"] not in ("probe", "observe"):
            continue
        acts = e.get("actions") or []
        for candidate in (prefix, []):
            try:
                frames = replay(game, level, list(candidate) + list(acts))
            except SystemExit:
                continue
            if verify(e, frames[-1], game):
                keys[e["seq"]] = list(candidate)
                prefix = list(candidate) + list(acts)
                break
        else:
            prefix = []                    # lost the thread; later entries retry
    return keys


def entity_summary(game, grid):
    """What a model would say is on screen — only if the game has a model."""
    if not has_model(game) or grid is None:
        return None
    st = model_for(game, version=0).reconstruct(grid)
    return {k: [list(e) for e in getattr(st, k, ())]
            for k in ("players", "guards", "patrols", "pursuers")
            if getattr(st, k, ())}


def export(game, out_dir):
    game = short_id(game)
    sols = load_solutions(game)
    examples, gaps = [], []

    # ---- predict: every recorded solution step, free and deterministic -------
    for level in sorted(sols):
        s = Session.open(game, level)
        prev = s.grid
        for i, n in enumerate(sols[level], start=1):
            s.act(n)
            cur = None if s.dead else s.grid
            examples.append({
                "type": "predict", "game": game, "level": level, "step": i,
                "source": "solutions.json",
                "input": {"frame": prev, "action": n,
                          "entities": entity_summary(game, prev)},
                "target": {"dead": cur is None,
                           "cell_diff": grid_diff(prev, cur) if cur is not None else None},
            })
            if cur is None:
                break
            prev = cur

    # ---- from the journals ---------------------------------------------------
    for level in sorted({int(p.stem[1:]) for p in
                         (JOURNAL_ROOT / game).glob("L*.jsonl")}):
        entries = load_journal(game, level)
        derived = reconstruct_keys(game, level, entries)
        # frames per (run, prefix) are replayed once and shared
        cache = {}

        def frame_at(at):
            key = tuple(at)
            if key not in cache:
                try:
                    cache[key] = replay(game, level, list(at))[-1]
                except SystemExit:
                    cache[key] = None
            return cache[key]

        for e in entries:
            kind = e["kind"]
            at = e.get("at")
            recorded = at is not None
            if at is None and e["seq"] in derived:
                at = derived[e["seq"]]
            if kind == "observe":
                frame = frame_at(at) if at is not None else None
                if frame is None:
                    gaps.append({"type": "analyse", "level": level, "seq": e["seq"],
                                 "why": "no replay key ('at') on this entry, and no "
                                        "frame stored — written before the journal "
                                        "recorded either"})
                    continue
                examples.append({
                    "type": "analyse", "game": game, "level": level, "seq": e["seq"],
                    "provenance": "recorded" if recorded else "derived",
                    "source": f"journal L{level} seq {e['seq']}",
                    "input": {"frame": frame},
                    "target": {"note": e.get("note", ""),
                               "entities": e.get("entities", {})},
                })
            elif kind == "probe":
                frame = frame_at(at) if at is not None else None
                if frame is None:
                    gaps.append({"type": "probe", "level": level, "seq": e["seq"],
                                 "why": "no replay key ('at'); the frame this probe "
                                        "was looking at cannot be identified because "
                                        "several runs are interleaved in one file"})
                    continue
                examples.append({
                    "type": "probe", "game": game, "level": level, "seq": e["seq"],
                    "provenance": "recorded" if recorded else "derived",
                    "source": f"journal L{level} seq {e['seq']}",
                    "input": {"frame": frame, "question": e.get("hypothesis", "")},
                    "target": {"actions": e.get("actions", []),
                               "observed": e.get("observed", ""),
                               "died": e.get("died", False)},
                })
            elif kind == "refute":
                nxt = next((x for x in entries
                            if x["kind"] == "author" and x["seq"] > e["seq"]), None)
                before = e.get("source")          # not stored on refute; see below
                after = nxt.get("source") if nxt else None
                if not after:
                    gaps.append({"type": "repair", "level": level, "seq": e["seq"],
                                 "why": "the author entry that answered this refutation "
                                        "stores no model source — it predates source "
                                        "capture, and the file today is a later version"})
                    continue
                examples.append({
                    "type": "repair", "game": game, "level": level, "seq": e["seq"],
                    "source": f"journal L{level} seq {e['seq']}->{nxt['seq']}",
                    "input": {"bug": e.get("bug", ""), "action": e.get("action"),
                              "step_index": e.get("step_index"),
                              "cells": e.get("diff", []),
                              "model_source_before": before},
                    "target": {"rules": nxt.get("rules", []),
                               "changed": nxt.get("changed", ""),
                               "because": nxt.get("because", ""),
                               "model_source_after": after,
                               "source_sha": nxt.get("source_sha")},
                })
            elif kind == "plan":
                examples.append({
                    "type": "plan", "game": game, "level": level, "seq": e["seq"],
                    "source": f"journal L{level} seq {e['seq']}",
                    "input": {"level": level,
                              "frame": frame_at([]) if sols.get(level) else None},
                    "target": {"actions": e.get("actions", []),
                               "stats": e.get("stats", {})},
                })

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{game}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
    gap_path = out_dir / f"{game}.gaps.json"
    gap_path.write_text(json.dumps({"game": game, "gaps": gaps}, indent=1))
    return examples, gaps, path, gap_path


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--out", default=str(OUT_ROOT))
    p.add_argument("--all-games", action="store_true")
    a = p.parse_args()
    out = Path(a.out)
    games = ([d.name for d in JOURNAL_ROOT.iterdir() if d.is_dir()]
             if a.all_games else [short_id(a.game)])

    for game in sorted(games):
        examples, gaps, path, gap_path = export(game, out)
        by_type = {}
        for e in examples:
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        gap_type = {}
        for g in gaps:
            gap_type[g["type"]] = gap_type.get(g["type"], 0) + 1
        print(f"\n=== {game} ===")
        print(f"  wrote {len(examples)} examples -> {path} "
              f"({path.stat().st_size // 1024} KB)")
        for t in ("analyse", "probe", "predict", "repair", "plan"):
            got, missed = by_type.get(t, 0), gap_type.get(t, 0)
            flag = "" if not missed else f"   <-- {missed} NOT extractable"
            print(f"    {t:<9} {got:>5}{flag}")
        if gaps:
            print(f"  gaps written to {gap_path}")
            seen = set()
            for g in gaps:
                if g["why"] not in seen:
                    seen.add(g["why"])
                    print(f"    - {g['why']}")


if __name__ == "__main__":
    main()
