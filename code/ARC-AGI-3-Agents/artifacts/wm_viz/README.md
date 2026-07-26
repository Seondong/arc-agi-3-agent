# wm_viz — world-model solve, instrumented

Visualizations of the `agents/wm` world-model pipeline solving **tu93 L0–L2**,
with the world model authored by Claude Code (Max subscription) standing in for
`ClaudeBrain`'s `propose()` — no API calls.

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
| `inmodel_search.html` | **every simulated interaction** of the in-model BFS + fidelity/outcome table | `scripts/gen_inmodel_search.py` |

Regenerate any page's data with `uv run python scripts/<generator>.py` from
`code/ARC-AGI-3-Agents/`.

---

## Results so far

| level | world model | backtest | solve | real deaths paid |
|---|---|---|---|---|
| L0 | v3 (maze + HUD ignore) | 17/18 (only the terminal frame differs) | 18 actions | 0 |
| L1 | v4 (+ guard rule) | 7/7 exact | 10 actions | 1 (during probing) |
| L2 | v7 (+ N guards, lunge move, fed notch) | 4/4 exact | 19 actions | 1 (during probing) |

One model (`agents/wm/tu93_model.py`) covers all three levels: `guards: tuple = ()`
means L0 (none), L1 (one), L2 (three) all run through the same code.

**Known limits.** Certification windows are short (L2 = 4 transitions), so "certified"
means *consistent with what was observed*, not *proven correct*. The 19-action L2 plan
is shortest **under the model**, not verified optimal. Deaths render exactly, but the
terminal frame of a cleared level (next level's maze) is not modelled.
