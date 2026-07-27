# HANDOFF — world-model solve, per game

**Two documents, on purpose.** This one is the state of the WORK — which games,
what is solved, what to do next. `ARCHITECTURE.md` next to it is the state of the
SYSTEM — every module, why it exists, and what it caught. Read this first, then
that one before changing anything structural. If something is only in a
conversation, it does not exist.

Read this first when resuming. It is the durable state of the work; the
conversation that produced it is gone. Last updated when the pipeline was
namespaced by game and ls20 was opened.

## Layout — everything is per game

```
agents/wm/
  harness.py            game-agnostic: env session, solutions, paths
  models/__init__.py    game id -> model factory  (add a game here)
  models/tu93.py        one game's executable theory + its page metadata
scripts/wm/             game-parameterized: every script takes --game
  observe_level.py  probe_diff.py  probe_movers.py
  backtest_level.py backtest_all.py verify_game.py solve_level.py gen_site.py
scripts/wm/games/<g>/   that game's own deep-dive generators
artifacts/wm_journal/<g>/L<n>.jsonl , solutions.json
artifacts/wm_viz/index.html          the methodology page (root landing)
artifacts/wm_viz/<g>/                that game's pages, data under <g>/data/
artifacts/wm_viz/shared/style.css    the shared look
```

Nothing is game-specific outside `models/<g>.py` and `scripts/wm/games/<g>/`.
That is the claim being tested by opening a second game.

## Games

| game | status |
|---|---|
| tu93 | **solved, L0–L8, 185 actions, WIN**; model v12 reproduces every frame |
| ls20 | **opened**. First probes journaled, no model yet — see below |

## Where things stand

**tu93 is solved end to end — 9 levels, 185 actions, final state `WIN`.**
Re-run `uv run python scripts/wm/verify_game.py --game tu93` to see it, don't take it on trust.

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

## The dataset (the point of all this)

`uv run python scripts/wm/export_dataset.py --all-games` turns the journals into
typed training pairs in `artifacts/wm_dataset/<game>.jsonl`, and writes what it
could NOT build to `<game>.gaps.json`.

| pair type | input | target | tu93 today |
|---|---|---|---|
| `predict` | frame + action | next frame as a cell diff | **185** (free: the engine is deterministic, so solutions.json is enough) |
| `plan` | frame | the action sequence that clears it | 6 |
| `probe` | frame + open question | actions to spend + what came back | 18 of 70 |
| `analyse` | frame | entities and structure | 7 of 9 |
| `repair` | model source + pointed bug | rewritten source + why | **0 of 5** |

`repair` is the one that teaches a model to *write* world models, and for tu93 it
is gone: the author entries stored the string `"see agents/wm/models/tu93.py"`,
which resolves to a later version, and no copy of the earlier source survives in
git either because several versions were authored inside one session.

Fixed forward, not backfilled:

- `Journal` stamps every entry with a **run id** and **`at`** — the action prefix
  that reproduces the frame the entry refers to.
- `author()` stores the model's **actual source text + sha**, not a pointer.
- `refute()` stores the **pointed cells** `[row, col, predicted, actual]`.

The exporter recovers some older entries by replaying candidate prefixes and
accepting one only when the replayed frame matches what was recorded; those
examples are labelled `derived`, never `recorded`. The journal itself is never
rewritten.

## THE NEXT TASK — ls20

Opened, probed, not modelled. What the first probes established (journal:
`artifacts/wm_journal/ls20/L0.jsonl`):

- Actions 1-4 only. **ACTION2 moves nothing** from the start position and still
  costs a turn.
- The controlled thing is a **composite**: 10 cells of value 12 (5x2) sitting on
  15 cells of value 9 (5x3); both translate together.
- **Step size is 5 px**, not tu93's 6.
- **Value 9 is not a player marker here** — the same value draws glyphs inside
  two display boxes (rows 8-16 cols 32-40, rows 53-62 cols 1-11). Find the player
  by what moves, never by value.
- Rows 61-62 carry a value-11 bar across cols 13-54, consumed one column per
  action from the left. Same role as tu93's row 63, drawn the other way round.
- Background is values 3 and 4; there is no maze and no border wall.

Next: probe what the two display boxes are for (they are the obvious candidates
for the win condition — this game is listed as "agent reasoning"), then write
`agents/wm/models/ls20.py` and register it. Do not carry tu93 rules across: every
single quantity above differs.

Other directions:

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
uv run python scripts/wm/observe_level.py --game tu93 --level 6

# per-step census of every moving block: position, facing, notch value
uv run python scripts/wm/probe_movers.py --game tu93 --level 6 "ACTION4,ACTION4"

# certify the model against a real sequence, with a predicted/actual diff on failure
uv run python scripts/wm/backtest_level.py --game tu93 --level 6 "ACTION4,ACTION4"

# probe → certify → plan in-model → execute GATED → save solution, journaling live
uv run python scripts/wm/solve_level.py --game tu93 --level 6 "ACTION4,ACTION4"

# run a plan one checked action at a time, stopping at the first mispredicted step
uv run python scripts/wm/execute_gated.py --game m0r0 --level 1 "ACTION2,..." \
    --legacy no_mirror_law     # gate with a RETIRED version to see where it breaks

# rebuild every page's data from the journals + real engine runs, then serve
uv run python scripts/wm/games/tu93/gen_paper.py     # the write-up (landing page)
uv run python scripts/wm/gen_site.py --game tu93    # ALL levels: replay + full in-model search
# (folded into gen_site.py)   # every retired model version, re-measured
uv run python scripts/wm/games/tu93/gen_l4_evolve.py      # L4: cell count vs entity count
uv run python scripts/wm/games/tu93/gen_l6_pursuer.py     # L6: pursuer trail vs simulated chaser
python3 -m http.server 8733 -d artifacts/wm_viz   # → /paper.html
```

There are **two different stops** in `solve_level.py` and they are not the same
thing:

- **`MODEL REFUTED`** — the backtest failed, so it does not plan at all. A real
  guard, added because an uncertified model produced a confident plan on tu93 L2
  that killed the player.
- **`NO PLAN`** — the search ran and `is_goal` was never true in any reachable
  state. Not a guard; the model simply does not know what winning looks like
  here. The cure is `scripts/wm/explore_level.py`, which goes and interacts
  instead of stopping: it tries every action the model has no dynamics for and
  `ACTION6` on a representative square of every value region, ranks what actually
  happened, and follows the best lead into the state it opens. On m0r0 L2 it
  re-found the switch mechanic unaided, first out of 22 candidates.

**Execution is gated.** A plan is no longer run blind: before each action the
model predicts, after it the prediction is checked, and the first mismatch stops
execution with a pointed bug and the replay key. Proven on m0r0 L1 — the retired
`no_mirror_law` model's 20-action plan aborts at step 12 with 64 mispredicted
cells and 8 actions unspent, where running it blind spent all 20 to learn only
"no clear". A model with no renderer (sk48) is gated on status alone and the
report says so.

`solve_level.py` **stops at a refutation and refuses to plan**. That is by
design, not a bug — an uncertified model produced a confident plan on L2 that
killed the player. If it stops, investigate the pointed bug and fix the model.
It appends to the journal; pass `--reset` only if you really mean to erase one.

### Running unattended

```bash
uv run python scripts/wm/autosolve.py --game ft09 --levels 3 --minutes 90
```

`propose()` is a headless `claude -p` whose answer is accepted only if it replays
every recorded step exactly. Bounded by `--budget-x` (actions per level, 5x the
human baseline), `--max-brain` (Claude Code sessions per level), `--minutes`, and
`--levels`. Resumable: solutions are saved as levels clear, so a re-run continues
from the first unsolved one. A NO PLAN triggers exploration and a re-proposal
rather than stopping.

Note: a brain proposal is not written back into `agents/wm/models/`, so a game
solved this way has its model in the journal only. Registering it is a manual
step for now.

### Modules added from the ARC-AGI-3 papers (full write-up in ARCHITECTURE.md)

```bash
uv run python scripts/wm/execute_gated.py  --game m0r0 --level 1 "..."  # checked actions
uv run python scripts/wm/simplify_model.py --game tu93 --journal        # weaken + verify
uv run python scripts/wm/stuck_report.py   --game m0r0 --level 2        # what was never tried
```

`simplify_model.py` weakens the model one retired rule at a time and replays every
recorded solution AND probe through it; a rule that survives was never forced by
anything we saw. It earned its place by catching that m0r0's hazard rule had no
recorded evidence at all — the ten measurements behind it had been run in an
ad-hoc script that never journaled. Re-probing the 10-action discriminating
sequence with journaling closed it.

### Measuring ourselves (added from the ARC-AGI-3 papers)

```bash
uv run python scripts/wm/score_rhae.py --all-games   # the benchmark's own metric
uv run python scripts/wm/model_debt.py --all-games   # magic constants, masks, flags
uv run python scripts/wm/stuck_report.py --game m0r0 --level 2   # what was never tried
```

`score_rhae.py` is the number that matters and the one we never had: RHAE counts
unsolved levels as zero and weights the later ones most. Every level we solve
beats the human action count, so our problem is coverage, not efficiency —
tu93 100, m0r0 14.3, sk48 2.8, mean 39.0.

Solving and exploring now take `--budget-x` (default 5, the official cutoff),
which raises `BudgetExceeded` rather than letting a diagnostic spend thousands of
actions the way one sk48 enumeration did.

### Regression set (run after every model change)

```bash
uv run python scripts/wm/backtest_all.py --game tu93   # THE one that matters:
                             # every level, every step of its own solution, cell-exact
uv run python scripts/wm/verify_game.py --game tu93   # all 9 levels -> WIN
uv run python scripts/check_viz_pages.py   # the viz pages: ids, targets, links, scripts
uv run python -m pytest agents/wm/tests -q
```
`backtest_all.py` exists because short probes are not certification: L5 and L8
both passed a two-step probe while mispredicting their own solution paths.
(`scripts/wm/games/tu93/legacy/` holds the L0–L2 era generators; several use the
pre-refactor `state.pr/pc` API and will raise `AttributeError`. They are kept for
the pages they still feed, not as working tools.)

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

## Opening a new game — the checklist

```bash
G=ls20
uv run python scripts/wm/observe_level.py --game $G --level 0     # what is on screen
uv run python scripts/wm/probe_diff.py    --game $G --level 0 --each   # what each action does
uv run python scripts/wm/probe_movers.py  --game $G --level 0 "..."    # per-step entity census
# write agents/wm/models/$G.py, register it in agents/wm/models/__init__.py
uv run python scripts/wm/backtest_level.py --game $G --level 0 "..."   # certify or get a bug
uv run python scripts/wm/solve_level.py    --game $G --level 0 "..."   # plan + execute + save
uv run python scripts/wm/gen_site.py       --game $G                   # build its pages
```

`probe_diff.py --each` is the right first tool: it resets between actions and
reports what changed, so "nothing happened" and "an object moved" are
distinguishable before anything is known. Carrying the previous game's constants
across is the mistake it exists to prevent — ls20's step is 5 px where tu93's is
6, and ls20 draws glyphs in value 9, the value that was the player in tu93.


---

## 2026-07-27 — four new games, and the coordinate action

Running `autosolve` on ft09, vc33, bp35, cd82. Checking their action sets first
was what saved the session:

| game | available actions | levels | human baseline |
|---|---|---|---|
| ft09 | **6 only** | 6 | 17, 19, 15, 21, 65, 26 |
| vc33 | **6 only** | 7 | 6, 13, 31, 59, 92, 24, 82 |
| bp35 | 3, 4, 6, 7 | 9 | 15, 72, 36, 31, 31, 48, 86, 155, 163 |
| cd82 | 1, 2, 3, 4, 5, 6 | 6 | 41, 8, 30, 21, 19, 17 |

Two of the four are coordinate-only. See ARCHITECTURE.md, "The action set is
derived, never assumed". Evidence gathering after the fix, at level 0:

    ft09  23 runs,  8 changed   (all 8 found by the sweep fallback)
    vc33   8 runs, 14 changed
    bp35  16 runs, 19 changed
    cd82  15 runs, 20 changed

**ft09's responsive squares are clustered**: of 100 coarse-sweep clicks only the
block at x,y >= 38 did anything, each changing 38 cells. Whatever ft09 is, it
listens in one corner. That is the first thing to look at when reading its
journal.

Run configuration: two streams, 70 min per game, `--max-brain 8 --budget-x 5`.
Logs in `artifacts/wm_runs/<game>.log`; journals are per-game as usual.
