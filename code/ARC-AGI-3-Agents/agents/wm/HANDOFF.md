# HANDOFF — tu93 world-model solve

Read this first when resuming. It is the durable state of the work; the
conversation that produced it is gone. Last updated after L3 was solved and L4
was blocked on one open question.

## Where things stand

| level | new mechanic | status | solve actions | real deaths paid |
|---|---|---|---|---|
| L0 | maze, player, goal | ✅ solved | 18 | 0 |
| L1 | guard (8): stationary, lethal head-on | ✅ solved | 10 | 1 (probing) |
| L2 | three guards; lunge + "fed" notch | ✅ solved | 19 | 1 (probing) |
| L3 | patroller (12): moves, bounces | ✅ solved | 17 | 0 |
| L4 | 2 player blocks; goal renders over patroller | ❌ **blocked** | — | 0 |
| L5+ | unknown | not reached | — | — |

Solutions live in `artifacts/wm_journal/solutions.json` (this is the source of
truth — every script reads it to replay to a level). Model:
`agents/wm/tu93_model.py`, one model covering all levels.

## THE NEXT TASK — L4 patroller-vs-patroller collision

Everything else on L4 is modelled. This one rule is missing, and the loop
correctly refuses to plan without it.

**Evidence already collected** (in `artifacts/wm_journal/tu93_L4.jsonl`):
- L4 opens with 4 patrollers → value-12 cell count is 32.
- After the *first* move the count is 16 (two are hidden under the goal tile),
  then 24 from the second move onward — **and never returns to 32**.
- So exactly **one patroller is permanently destroyed** when the two column-27
  patrollers — one above facing D, one below facing U — both advance onto the
  goal square (32,27).
- The model currently keeps both alive, so four steps later it predicts a
  patroller at (14,27) where reality shows empty floor → backtest 3/4, 81 cells off.

**Probes to run** (black box, never read `environment_files/`):
1. Do two patrollers annihilate on meeting, or does one survive? Which one —
   the one that arrives from a particular direction, or a fixed index order?
2. Does it matter that the meeting square is the goal? Find two patrollers that
   meet in a plain corridor and repeat.
3. What happens if they would *swap* squares (pass through each other) rather
   than land on the same one?

Then encode the rule in the patroller section of `step()` in
`agents/wm/tu93_model.py`, re-run the regression set (below), and continue.

## Standard workflow

```bash
cd code/ARC-AGI-3-Agents

# look at a level (replays saved solutions to get there)
uv run python scripts/observe_level.py 4

# probe → certify → plan in-model → execute → save solution, journaling live
uv run python scripts/solve_level.py 4 "ACTION3,ACTION3,ACTION1"

# rebuild the paper's data from the journals, then serve
uv run python scripts/gen_paper_data.py
python3 -m http.server 8733 -d artifacts/wm_viz   # → /paper.html
```

`solve_level.py` **stops at a refutation and refuses to plan**. That is by
design, not a bug — an uncertified model produced a confident plan on L2 that
killed the player. If it stops, investigate the pointed bug and fix the model.

### Regression set (run after every model change)

```bash
uv run python scripts/backtest_tu93.py     # L0 → expect 17/18 (only the terminal frame differs)
uv run python scripts/backtest_l1.py       # L1 → expect 7/7 exact + L1 CLEARED
uv run python scripts/solve_level.py 3 "ACTION1,ACTION4,ACTION3,ACTION4"   # L3 → 4/4 + CLEARED
```
(`scripts/solve_l2_wm.py` still uses the pre-refactor `state.pr/pc` API and will
raise `AttributeError`; either fix it to use `state.players` or ignore it — L2 is
covered by the L3 run replaying through it.)

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
  player.
- **Players (L4+)**: several player blocks all obey the same action; each is
  blocked independently.
- **Render order**: guards, then patrollers, then the goal tile (the goal is drawn
  *over* a patroller standing on it), then players.

## Gotchas that cost time

- `raw.levels_completed` alone does **not** detect death — check
  `raw.state.name == "GAME_OVER"` too, and `raw.frame` can be empty on death.
- Comparing whole frames to detect "did the player move" is wrong: row 63 (HUD)
  changes every step. Compare entity positions.
- Guards and patrollers share notch value 15, so classify a block by its **body**
  value, not its notch.
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
8. Black box only — `environment_files/` is never read.

## Artifacts

- `artifacts/wm_journal/*.jsonl` — the durable narrative (append-only, provenance-tagged)
- `artifacts/wm_journal/solutions.json` — per-level action sequences
- `artifacts/wm_viz/paper.html` — the interactive write-up (data from the journals)
- `artifacts/wm_viz/*.html` — supporting figures; `README.md` maps each to its generator
- `agents/wm/tu93_model.py` — the world model
- `agents/wm/journal.py` — the recorder

Nothing here is committed to git yet (`git status` shows the scripts and model as
untracked). Commit before relying on it.
