"""Score a model on repair tasks with the verifier, not with a judge.

The whole reason this capability is worth distilling is that it can be graded
objectively and locally. A repair is right if the corrected module replays the
recorded history exactly, and `run_backtest` decides that -- no rubric, no
second model, no game API beyond replaying what is already saved.

Four things are measured, in descending order of how much they mean:

  replays   the module loads AND reproduces every recorded step cell-exactly
  loads     the module at least imports and constructs (a 4-bit model that
            cannot emit valid Python is unusable regardless of its ideas)
  fenced    the reply contains a python block at all
  tokens    output length, because SFT drift toward rambling is a known failure

Usage:
  eval_repair.py --model <path> [--adapter <path>] [--limit 5]
"""
import json
import re
import tempfile
import time
from pathlib import Path

import _cli

CODE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)
SFT = Path("artifacts/wm_sft")


def build_prompt(task, system):
    parts = [f"GAME: {task['game']}, level {task['level']}.", "", "COUNTEREXAMPLE:",
             task["bug"], "", "THE MODEL AS IT STANDS:", "```python",
             task["before"], "```", "", "Return the corrected module."]
    return system, "\n".join(parts)


def load_module(source):
    import importlib.util
    import uuid
    path = Path(tempfile.mkdtemp()) / f"cand_{uuid.uuid4().hex[:8]}.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(1)


def evidence_timelines(game, level=0):
    """One recorded step per available action, gathered fresh.

    Solutions only exist for games we have solved, and the games that produce
    the most repair pairs are exactly the ones we have NOT solved -- cd82 has
    thirteen refutations and no cleared level. Probing each action once from the
    opening frame gives a replayable, deterministic history for any game.
    """
    from agents.wm.core import Action, Status, Timeline, Transition
    from agents.wm.harness import Session
    import sys as _sys
    _sys.path.insert(0, "scripts/wm")
    from autosolve import action_set
    s = Session.open(game, level)
    out = []
    for act in action_set(s.grid, s.raw.available_actions)[:12]:
        s.reset_to(level)
        init = s.grid
        tl = Timeline(init)
        s.act(act.name, x=act.x, y=act.y)
        tl.record(Transition(step_index=1, action=act, before_frame=init,
                             after_frame=None if s.dead else s.grid,
                             status=(Status.GAME_OVER if s.dead else Status.RUNNING)))
        out.append(tl)
    return out


def timelines_for(game):
    """Recorded evidence to replay against: the game's own saved solutions."""
    from agents.wm.core import Action, Status, Timeline, Transition
    from agents.wm.harness import Session, load_solutions
    sols = load_solutions(game)
    out = []
    for level in sorted(sols):
        try:
            s = Session.open(game, level)
        except Exception:                                      # noqa: BLE001
            continue
        init = s.grid
        tl = Timeline(init)
        prev, lv0 = init, s.raw.levels_completed
        for i, n in enumerate(sols[level], start=1):
            base, x, y = n, None, None
            if "@" in n:
                base, co = n.split("@", 1)
                x, y = (int(v) for v in co.split(":"))
            s.act(base, x=x, y=y)
            cleared = (not s.dead) and s.raw.levels_completed > lv0
            tl.record(Transition(
                step_index=i, action=Action(base, x=x, y=y), before_frame=prev,
                after_frame=None if (s.dead or cleared) else s.grid,
                status=(Status.GAME_OVER if s.dead else
                        Status.LEVEL_COMPLETED if cleared else Status.RUNNING)))
            if s.dead or cleared:
                break
            prev = s.grid
        if len(tl):
            out.append(tl)
    if not out:
        out = evidence_timelines(game)
    return out


def score_one(source, game, cache):
    from agents.wm.backtest import run_backtest
    try:
        model = load_module(source)
    except Exception as exc:                                   # noqa: BLE001
        return {"loads": False, "replays": False, "why": f"{type(exc).__name__}: {exc}"[:150]}
    if game not in cache:
        cache[game] = timelines_for(game)
    tls = cache[game]
    if not tls:
        return {"loads": True, "replays": None, "why": "no recorded timeline to replay"}
    total = matched = 0
    for tl in tls:
        rep = run_backtest(model, tl)
        total += rep.total
        matched += rep.matched
        if not rep.ok:
            return {"loads": True, "replays": False,
                    "why": rep.summary()[:150], "matched": matched, "total": total}
    return {"loads": True, "replays": True, "matched": matched, "total": total,
            "why": f"replayed {matched}/{total} exactly"}


def main():
    p = _cli.parser(__doc__)
    p.add_argument("--model", default="/Users/sundong/Documents/arc-agi-3/models/"
                                      "qwen3.6-27b-mlx-4bit")
    p.add_argument("--adapter", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-tokens", type=int, default=3000)
    p.add_argument("--tag", default="base")
    a = p.parse_args()

    tasks = json.loads((SFT / "test_meta.json").read_text())
    if a.limit:
        tasks = tasks[:a.limit]
    system = json.loads(next((SFT / "train.jsonl").open()))["messages"][0]["content"]

    from mlx_lm import generate, load
    kw = {"adapter_path": a.adapter} if a.adapter else {}
    print(f"loading {a.model}" + (f" + adapter {a.adapter}" if a.adapter else ""))
    model, tok = load(a.model, **kw)

    cache, rows = {}, []
    for i, t in enumerate(tasks, start=1):
        sysmsg, user = build_prompt(t, system)
        # Thinking burns the whole budget before any code appears: the first
        # measured run hit a 3000-token cap with the reply still mid-reasoning.
        # The task is to emit a module, not to narrate.
        msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]
        try:
            prompt = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                             tokenize=False, enable_thinking=False)
        except TypeError:
            prompt = tok.apply_chat_template(msgs, add_generation_prompt=True,
                                             tokenize=False)
        t0 = time.time()
        out = generate(model, tok, prompt=prompt, max_tokens=a.max_tokens, verbose=False)
        dt = time.time() - t0
        blocks = CODE.findall(out)
        row = {"game": t["game"], "level": t["level"], "seconds": round(dt),
               "out_tokens": len(tok.encode(out)), "fenced": bool(blocks)}
        if blocks:
            row.update(score_one(max(blocks, key=len), t["game"], cache))
        else:
            row.update({"loads": False, "replays": False, "why": "no fenced block"})
        rows.append(row)
        print(f"  [{i}/{len(tasks)}] {t['game']} L{t['level']}  "
              f"fenced={row['fenced']} loads={row.get('loads')} "
              f"replays={row.get('replays')}  {row.get('why','')[:70]}")

    n = len(rows)
    summary = {
        "tag": a.tag, "adapter": a.adapter, "n": n,
        "fenced": sum(1 for r in rows if r["fenced"]),
        "loads": sum(1 for r in rows if r.get("loads")),
        "replays": sum(1 for r in rows if r.get("replays") is True),
        "mean_out_tokens": round(sum(r["out_tokens"] for r in rows) / max(1, n)),
        "mean_seconds": round(sum(r["seconds"] for r in rows) / max(1, n)),
    }
    print(f"\n  {summary}")
    out_path = SFT / f"eval_{a.tag}.json"
    out_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(f"  wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
