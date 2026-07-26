# wm_viz — world-model solve, instrumented

Visualizations of the `agents/wm` world-model pipeline solving **tu93 end to end
— all 9 levels, 185 actions, final state `WIN`** — with the world model authored
by Claude Code (Max subscription) standing in for `ClaudeBrain`'s `propose()` —
no API calls.

Start at **`paper.html`** — it is the landing page and links to everything below.
`level.html` covers every level uniformly; the per-level pages that predate it
(L0–L2) are kept because they show workings the uniform page does not.

Serve locally:

```bash
cd code/ARC-AGI-3-Agents/artifacts/wm_viz
python3 -m http.server 8733            # → http://127.0.0.1:8733/
```

---

## Logging principles

These were established by correcting earlier, dishonest versions of these pages.
**They are requirements, not style preferences** — a page that violates one is wrong
even if its numbers are right.

### 1. Never show only the final answer
The first L1 page replayed the 10-action solution and nothing else, which read as
"solved it instantly". It had actually taken 41 candidate moves and 2 deaths.
**Every search must expose its failures**: the moves tried, the branches pruned, the
deaths. `l1_search.html` is the corrected form.

### 2. Discovery cost is part of the cost
A rule the agent "knows" was paid for with real interaction. The guard rule on L1
cost 342 env-steps **and one real death**. Never present a learned rule as if it
arrived for free, and never let the solve-action count stand in for total cost.

Wrong framing (used once, corrected): *"the model knew the death in advance."*
Right framing: *"a real death was already paid for; the model encodes that lesson so
the **planner** never has to die again."*

### 3. Separate the cost buckets, always
| bucket | meaning |
|---|---|
| **probe / explore** | real env actions spent learning dynamics |
| **planning** | in-model simulation — 0 real actions |
| **solve** | real env actions executing the certified plan |
| **deaths** | real deaths, counted separately from imagined ones |

Reporting a single total hides where the cost actually went.

### 4. In-model search is logged too, per interaction
In-model BFS is not a free black box — it is the object of study for *how to
interact inside a model*. Log every simulated `(state, action) → outcome`
(`death` / `blocked` / `revisit` / `frontier` / `goal`), not just aggregates.
`inmodel_search.html` shows all 184 simulated interactions for L2, including the
**5 imagined deaths** and the **71 % wasted** (revisit + wall-blocked) share —
that waste is the slack an in-model-interaction study would attack.

### 5. Model fidelity must be shown against search outcome
An uncertified model produces confident, wrong plans. On L2, `v4` (which modelled
1 of 3 guards) found a 9-action "shortcut" through a guard it did not know about;
executing it **killed the player for real**. Any page showing in-model planning
must also show what happens when the model is wrong.

### 6. Refutations are the story, not a footnote
Model versions change because `run_backtest` produced a *pointed bug* — a specific
step, action, and set of wrong cells. Show the predicted frame next to the real one
with the mismatching cells marked. On L2 a single death frame refuted three
successive models (18 cells → 18 cells → 1 cell → 0).

### 7. Record the narrative as it happens, not afterwards
**This one is architectural, and the first pages got it wrong.** `l1_evolve.py`,
`l2_evolve.py` and `evolve_data.py` regenerate their *frames* from the engine, but
their *story* — `"learn"`, `RULES`, `"note"` strings — was hand-written into the
generator afterwards, from the author's conversational context. If that context is
gone, the narrative cannot be rebuilt: the visualization becomes unmaintainable.

The fix is `agents/wm/journal.py`: the solver appends each discovery to an
append-only JSONL **at the moment it happens** (`observe` / `probe` / `refute` /
`author` / `plan` / `execute` / `note`), and visualizations read that journal.
`probe()` records the *hypothesis* alongside the observation, because why a probe
was run is exactly what gets forgotten first. Every entry carries `provenance`:
`live` (written during the run) or `retro` (reconstructed later — flag it, never
hide it), and `journal.summary()` derives the cost ledger with no hand-counting.

`scripts/solve_l3_journaled.py` is the reference workflow. The L0–L2 generators
predate the journal and still embed prose; treat them as legacy.

### 8. Black box only
Dynamics come from stepping the engine and reading returned frames.
`environment_files/` is never read. (Also recorded in memory as `feedback_no_env_files`.)

### 9. Count entities, not cells — and check that a probe can discriminate
Two failures on L4, both invisible to a green backtest. **Cells lie about
entities**: two blocks on one square render as one, and a block under the goal
tile renders as none, so a falling cell count looked exactly like destruction and
became an open research question that had no answer. **A probe set that cannot
separate two rules certifies both**: the rule "every 9-block is a player" survived
three probes because the inert block was walled in on the only direction they
used. `l4_evolve.html` is the corrected record of both. Before trusting a rule,
ask which observation would have refuted it — and whether one was ever run.

### 10. Instrument every case, not the interesting ones
The pages grew one per session and covered whatever was interesting that day: L0
had three pages, L2 had the only in-model search log, and L3/L5/L7/L8 had none.
A record with holes reads as a record. Worse, the holes hid real bugs: no level
had ever been replayed frame-by-frame along its *own* solution, and when that
sweep was finally run (`scripts/backtest_all.py`) two levels failed it — a guard
drawn on the wrong side of a patroller, and a patroller the player destroys by
crossing it. Both had passed their two-step certification, and both plans still
worked, so nothing complained. `level.html` now produces the same four views for
every level, and `model_evolve.html` re-runs every retired version against every
level. Where a record genuinely does not exist — L0–L2 predate the journal — the
gap is shown as a gap, not back-filled from memory.

---

## Pages

| page | shows | data generator |
|---|---|---|
| `index.html` | L0 solve: model prediction vs reality, 18 actions | `scripts/gen_viz_data.py` |
| `episode.html` | L0 autonomous episode: explore → author v1/v2 → solve; total 24 actions | `scripts/gen_episode_data.py` |
| `evolve.html` | L0 model rebuilt **per observation** (v0→v3), each refutation shown | `scripts/gen_evolve_data.py` |
| `l1.html` | L1 solution playback + the guard mechanic | `scripts/gen_l1_viz.py` |
| `l1_search.html` | L1 **brute-force search over the real engine**: 41 attempts, 2 real deaths | `scripts/gen_l1_search.py` |
| `l1_evolve.html` | L1 the world-model way: inherit v3 → 5 real probes (1 death) → v4 → solve | `scripts/gen_l1_evolve.py` |
| `l2_evolve.html` | L2: inherited v4 refuted 3× by one death frame → v7 certified → solve | `scripts/gen_l2_evolve.py` |
| **`level.html?l=N`** | **every level, uniformly** — solution replay against the model's prediction, the FULL in-model search, cost ledger and journal, for L0–L8 | `scripts/gen_level_pages.py` |
| **`model_evolve.html`** | **how the model evolved** — every retired version reconstructed and re-run against all nine levels, plus the live source of each rule | `scripts/gen_model_evolve.py` |
| `l4_evolve.html` | L4: the cell-count artefact that became a phantom research question, the refuted model re-run, and the probe that could tell the theories apart | `scripts/gen_l4_evolve.py` |
| `l6_pursuer.html` | L6: a one-cell refutation, the pursuer's trail, and a shortest-path chaser simulated on the same frames to show which rule it is **not** | `scripts/gen_l6_pursuer.py` |
| `inmodel_search.html` | **every simulated interaction** of the in-model BFS + fidelity/outcome table | `scripts/gen_inmodel_search.py` |
| `paper.html` | the write-up that ties them together; data from the journals + solutions | `scripts/gen_paper_data.py` |

Regenerate any page's data with `uv run python scripts/<generator>.py` from
`code/ARC-AGI-3-Agents/`, then check the pages themselves:

```bash
uv run python scripts/check_viz_pages.py
```

That checker exists because a real rendering bug shipped and nothing complained:
`paper.html` carried `id="ledger"` on both the section heading and the table under
it, so `getElementById("ledger")` returned the **heading**, the rows were injected
into an `<h2>`, and the browser silently dropped every `<tr>` — the ledger rendered
as a wall of oversized text. The JSON was valid, the JS parsed, the page returned
200. It now checks duplicate/shadowed ids, missing targets, table rows injected
into non-tables, `getContext` on non-canvases, unresolvable links and fetches, and
script syntax.

---

## Results

**tu93 solved: 9 levels, 185 actions, final state `WIN`.** Re-run it with
`uv run python scripts/verify_tu93.py` rather than taking the table on trust.

| level | world model | new mechanic | solve | real deaths paid |
|---|---|---|---|---|
| L0 | v3 (maze + HUD ignore) | maze, player, goal | 18 actions | 0 |
| L1 | v4 (+ guard rule) | guard: stationary, lethal head-on | 10 actions | 1 (probing) |
| L2 | v7 (+ N guards, lunge move, fed notch) | three guards | 19 actions | 1 (probing) |
| L3 | v8 (+ patroller) | patroller: moves when you move, bounces | 17 actions | 0 |
| L4 | v10 (+ inert look-alike) | a block that looks like the player and is not | 29 actions | 1 (probing) |
| L5 | v12 | none — guards + patrollers composed | 28 actions | 0 |
| L6 | v11 (+ pursuer) | pursuer: follows your own trail | 14 actions | 1 (probing) |
| L7 | v11 | none | 21 actions | 0 |
| L8 | v12 | none — all three enemy types at once | 29 actions | 0 |

One model (`agents/wm/tu93_model.py`) covers every level; empty tuples mean an
entity type is simply absent. **L5, L7 and L8 each cost two probe actions, zero
refutations and zero deaths** — that is the return on everything paid earlier, and
it is the number to watch when porting the method to another game.

Every level's own solution now replays through the model **cell-exact at every
step** — 176 steps, `uv run python scripts/backtest_all.py`.

**Known limits.** Probe certification windows are short (several levels = 2
transitions), so passing one means *consistent with what was observed*, not
*proven correct* — L4 is the cautionary case: three probes certified a rule none
of them could discriminate, and L5/L8 passed theirs with a render bug and a
missing destruction rule intact. The overlap draw-order rule is explicitly
under-determined: it fits all nine observed overlaps and refutes the obvious
competitor, but the experiment that would separate it from other explanations
does not occur in any solution path. Plan lengths are shortest **under the model**, not verified optimal.
The HUD row is excluded from verification rather than modelled. Deaths return no
frame, so they certify a status only. And the terminal frame of a cleared level
(the next level's maze) is not modelled.
