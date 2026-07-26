# HANDOFF — tu93 world-model solve

Read this first when resuming. It is the durable state of the work; the
conversation that produced it is gone. Last updated when tu93 was finished.

## Where things stand

**tu93 is solved end to end — 9 levels, 185 actions, final state `WIN`.**
Re-run `uv run python scripts/verify_tu93.py` to see it, don't take it on trust.

| level | new mechanic | solve actions | real deaths paid |
|---|---|---|---|
| L0 | maze, player, goal | 18 | 0 |
| L1 | guard (8): stationary, lethal head-on | 10 | 1 (probing) |
| L2 | three guards; lunge + "fed" notch | 19 | 1 (probing) |
| L3 | patroller (12): moves, bounces | 17 | 0 |
| L4 | a second block that looks like the player and is inert | 29 | 1 (probing) |
| L5 | nothing new — guards + patrollers composed | 28 | 0 |
| L6 | pursuer (13): trail-following hunter | 14 | 1 (probing) |
| L7 | nothing new | 21 | 0 |
| L8 | nothing new — all three enemy types at once | 29 | 0 |

L5, L7 and L8 each cost **two probe actions and no deaths**: by then the model
already contained everything they are made of. That is the whole point of the
approach, and it is the part worth extending to another game.

Solutions live in `artifacts/wm_journal/solutions.json` (the source of truth —
every script reads it to replay to a level). Model: `agents/wm/tu93_model.py`,
one model covering all levels, currently **v11**.

## THE NEXT TASK

tu93 has nothing left to solve. Pick one:

1. **Port the loop to a second game** (`ls20`, `ft09`, `sk48`, …). The scripts are
   all tu93-specific in their model import only — `observe_level.py`,
   `probe_movers.py`, `backtest_level.py`, `solve_level.py`, `verify_tu93.py`
   otherwise generalise. The real question this answers: how much of the *method*
   transfers when none of the *rules* do.
2. **Close the propose() seam.** The model is hand-authored by Claude Code; the
   framework's `propose()` is meant to be filled by a model that writes the rule
   from the counterexample. Every refutation in the journals is a training pair:
   pointed bug in, model diff out.
3. **Make certification honest about its window.** Partly done: `backtest_all.py`
   now replays every level along its own solution and it found two real bugs that
   probe-certification missed. Still open: require the probe set to exercise every
   action, and flag rules no observation has yet discriminated (the overlap
   draw-order rule is currently the only one carrying that flag by hand).

## Standard workflow

```bash
cd code/ARC-AGI-3-Agents

# look at a level (replays saved solutions to get there)
uv run python scripts/observe_level.py 6

# per-step census of every moving block: position, facing, notch value
uv run python scripts/probe_movers.py "ACTION4,ACTION4,ACTION3" --level 6

# certify the model against a real sequence, with a predicted/actual diff on failure
uv run python scripts/backtest_level.py "ACTION4,ACTION4" --level 6

# probe → certify → plan in-model → execute → save solution, journaling live
uv run python scripts/solve_level.py 6 "ACTION4,ACTION4"

# rebuild every page's data from the journals + real engine runs, then serve
uv run python scripts/gen_paper_data.py     # the write-up (landing page)
uv run python scripts/gen_level_pages.py    # ALL levels: replay + full in-model search
uv run python scripts/gen_model_evolve.py   # every retired model version, re-measured
uv run python scripts/gen_l4_evolve.py      # L4: cell count vs entity count
uv run python scripts/gen_l6_pursuer.py     # L6: pursuer trail vs simulated chaser
python3 -m http.server 8733 -d artifacts/wm_viz   # → /paper.html
```

`solve_level.py` **stops at a refutation and refuses to plan**. That is by
design, not a bug — an uncertified model produced a confident plan on L2 that
killed the player. If it stops, investigate the pointed bug and fix the model.
It appends to the journal; pass `--reset` only if you really mean to erase one.

### Regression set (run after every model change)

```bash
uv run python scripts/backtest_all.py      # THE one that matters: every level, every
                                           # step of its own solution, cell-exact
uv run python scripts/verify_tu93.py       # all 9 levels -> WIN
uv run python scripts/check_viz_pages.py   # the viz pages: ids, targets, links, scripts
uv run python -m pytest agents/wm/tests -q
```
`backtest_all.py` exists because short probes are not certification: L5 and L8
both passed a two-step probe while mispredicting their own solution paths.
(`scripts/solve_l2_wm.py` still uses the pre-refactor `state.pr/pc` API and will
raise `AttributeError`; ignore it — L2 is covered by `verify_tu93.py`.)

## Learned rules (all black box)

- **Movement**: 3×3 player block (9) + facing notch (4); `ACTION1/2/3/4` =
  up/down/left/right, 6 px per step. A move needs both the doorway strip at +3
  and the destination at +6 to be free of wall (5) / border (6).
- **Goal**: 3×3 block of 14; a player reaching its top-left clears the level.
- **HUD**: row 63 is an energy/step bar consumed right→left at a non-integer
  rate. Not modelled — excluded via `ignore()`. Running it to zero is GAME_OVER.
- **Guard (8 + notch 15)**: never moves. Entering the cell it *faces* makes it
  lunge into that cell → GAME_OVER; it vacates its old square and the player is
  removed. The guard that ate renders notch **11** instead of 15. Stepping onto a
  guard from any other side removes it.
- **Patroller (12 + notch 15)**: advances 6 px along its facing **only on turns
  where a player actually changed square**; bounces at walls, and the notch flips
  **on arrival** so it always shows where it will go next. Contact destroys the
  player. Patrollers **never destroy each other** — they overlap freely.
- **Pursuer (13 + notch 15)**: asleep until a player crosses the straight line it
  faces (any distance, through doors, stopped by walls). Its notch then turns
  **11** and it walks that line to the square where it saw the player, and from
  there follows the player's own trail one square per player move — never a
  shortcut. It stays exactly as far behind as it was when it locked on, so it can
  only catch a player who steps back onto their own trail. Contact kills.
- **Inert look-alikes (L4)**: a 3×3 block of 9 with a player notch that is not
  controlled. No single frame distinguishes it from the player — you find out by
  acting. Listed in `INERT_LOOKALIKES` in the model.
- **Crossing a patroller**: a player that steps into the square a patroller is
  *leaving* destroys it (the moving counterpart of stepping onto a guard from
  behind). Ending on the same square is still death. Unknown for pursuers.
- **Render order**: co-located enemies — a guard is drawn on top when its facing
  lies along the axis the other thing travels, otherwise the mover is on top; a
  patroller is always over a pursuer. Then the goal tile (over anything standing
  on it), then players. The guard/mover clause is the model's **least-trusted
  rule**: it fits all nine observed overlaps and refutes the obvious competitor
  (fixed z-order by starting position), but the discriminating case never occurs.

## Gotchas that cost time

- **Counting cells is not counting things.** Two entities on one square render as
  a single 3×3 block, and one on the goal square is hidden entirely. A whole
  session went into "which patroller gets destroyed when two meet" — none of them
  do; the cell count was just occlusion. Census the *blocks*, and use
  `probe_movers.py`, which prints them.
- **A probe set that cannot distinguish two rules certifies both.** The rule
  "every 9-block moves under one action" survived three L4 probes because the
  inert block was walled in on the only directions those probes used. If a rule
  has never been exercised, it has not been tested.
- `raw.levels_completed` alone does **not** detect death — check
  `raw.state.name == "GAME_OVER"` too, and `raw.frame` can be empty on death.
  Record such a transition with `after_frame=None`: the backtest then certifies
  the status only, instead of scoring the render against a stale frame.
- Comparing whole frames to detect "did the player move" is wrong: row 63 (HUD)
  changes every step. Compare entity positions.
- Guards, patrollers and pursuers all share notch value 15, so classify a block
  by its **body** value, not its notch. Notch 11 means "has locked on / eaten".
- `observe_level.py` and `solve_level.py` read `solutions.json`; if a level's
  solution is missing they cannot replay to later levels.
- The offline engine replays from RESET, so a naive BFS over the engine re-runs
  the whole prefix per node (1233 env-steps for L1). In-model search avoids this.

## Non-negotiable practices

Full statement in `artifacts/wm_viz/README.md` (§ Logging principles). Short form:

1. Never present only the answer — show the failed attempts and the deaths.
2. Discovery cost is part of the cost; a rule was paid for with real interaction.
3. Keep cost buckets separate: probe / planning (0, in-model) / solve / deaths.
4. Log in-model search per interaction — it is a research object, not a black box.
5. Show what a wrong model does, not just a right one.
6. Refutations are the story: predicted frame beside the real one, cells marked.
7. **Write the narrative as it happens** into `agents/wm/journal.py`, never
   reconstruct it afterwards from context. `probe()` records the hypothesis too.
   Do not run probes with journaling off "just to look" — the L4 census had to be
   paid for twice because of exactly that.
8. Black box only — `environment_files/` is never read.

## Artifacts

- `artifacts/wm_journal/*.jsonl` — the durable narrative (append-only, provenance-tagged)
- `artifacts/wm_journal/solutions.json` — per-level action sequences
- `artifacts/wm_viz/paper.html` — the landing page; links to everything
- `artifacts/wm_viz/level.html?l=N` — every level, uniformly instrumented
- `artifacts/wm_viz/model_evolve.html` — model versions re-run against every level
- `artifacts/wm_viz/l4_evolve.html` — L4: the phantom question, the real bug, the discriminator
- `artifacts/wm_viz/l6_pursuer.html` — L6: one-cell refutation, the trail, the chaser it is not
- `artifacts/wm_viz/*.html` — supporting figures; `README.md` maps each to its generator
- `agents/wm/tu93_model.py` — the world model
- `agents/wm/journal.py` — the recorder
