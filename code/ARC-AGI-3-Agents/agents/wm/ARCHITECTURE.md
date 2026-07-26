# The loop, module by module

Durable description of what exists and why. `HANDOFF.md` is the state of the
*work* (which games, what is solved, what to do next); this is the state of the
*system*. Both are written to survive a cleared context — if something is only in
a conversation, it does not exist.

Every module below is game-agnostic. The only per-game code is
`agents/wm/models/<game>.py` plus optional deep-dive generators in
`scripts/wm/games/<game>/`.

---

## The core contract

```
WorldModel(
  reconstruct(frame)      -> state       the level's initial state, from one frame
  step(state, action)     -> (state, status)   the dynamics
  render(state)           -> frame       for verification; may raise NotImplementedError
  is_goal(state)          -> bool        the inferred win condition
  ignore(frame)           -> cells       excluded from verification = modelling debt
  fingerprint(state)      -> hashable    keys the planner's visited set
)
```

This is the same four-part contract the published ablation gives its verification
variant (transition engine, state reconstruction, renderer, planner), arrived at
independently. `render` returning `NotImplementedError` is legitimate: sk48's
dynamics are enough to plan with while its frame is not reconstructed, and the
tools report frame-exactness as *not applicable* rather than as a failure.

## The loop

```
observe   →  probe   →  certify  →  author  →  plan in-model  →  execute gated
             (real)     backtest   new rules   BFS, 0 actions   check every step
                 ↑                     |
                 └──── refutation ─────┘
```

| stage | module | notes |
|---|---|---|
| observe | `scripts/wm/observe_level.py` | values, blocks, the interesting rectangle |
| probe | `probe_diff.py` (unknown game), `probe_movers.py` (entity census) | `probe_diff --each` resets between actions so "nothing happened" is distinguishable |
| certify | `agents/wm/backtest.py` | replays the whole timeline, demands cell-exactness, returns the **first** divergence as a pointed bug |
| author | `agents/wm/models/<game>.py` | see "who writes the model" below |
| plan | `agents/wm/planner.py` | BFS inside the certified model, zero real actions |
| execute | `scripts/wm/execute_gated.py` | predict → act → compare, stop at the first mismatch |
| when no plan | `scripts/wm/explore_level.py` | goal inference: try what the model treats as nothing, rank by what happened, follow the lead |

**Two different stops, often confused.** `MODEL REFUTED` is a guard — the backtest
failed, so it does not plan at all. `NO PLAN` is not a guard — the search ran and
`is_goal` was never true anywhere reachable, which usually means the model does
not know what winning looks like. The cure for the second is `explore_level.py`,
not stopping.

## Modules added from the two ARC-AGI-3 papers

Read 2607.15439 (nested ablation of executable modelling / simplification /
replay verification) and 2607.20709 (NVIDIA NOOA). What was adopted and why:

### `execute_gated.py` — every action is a checked experiment
Plans used to run blind: spend N actions, learn only "cleared" or "no clear".
Now the model predicts before each action and the prediction is checked after.
The first mismatch stops execution with a pointed bug and the replay key.
Demonstrated, not asserted: gating the retired `no_mirror_law` model on m0r0 L1's
20-action plan aborts at step 12 with 64 mispredicted cells and 8 actions unspent.

### `agents/wm/simplify.py` + `scripts/wm/simplify_model.py` — simplification with a verifier
The paper's simplification pass is a prompt, and its stated risk is that a
refactor destroys a partially correct model. A replay verifier removes that risk,
so here simplification is a **search with an acceptance test**: weaken the model,
replay everything ever recorded, accept only if still exact.

Candidates are free: every rule kept behind a `legacy` switch *is* a candidate,
because switching it off is the simpler model.

Both halves are training signal. An accepted weakening says no observation ever
forced that rule. A rejected one comes back with the counterexample that does —
the `(model, bug)` half of a repair pair, obtained without spending an
environment action beyond replays.

**It also detects unrecorded evidence, which is how it earned its place.** On
m0r0 it reported the hazard-reset rule as unforced. That was correct and alarming:
the ten measurements that established the rule had been run in an ad-hoc script
that never journaled, so the evidence did not exist. Re-probing the 10-action
discriminating sequence *with* journaling closed it — the rule is now refuted at
step 10 by 64 cells. A rule whose evidence was never recorded looks exactly like
a rule that was invented.

### `scripts/wm/stuck_report.py` — the anti-tunnel-vision check, computed
The paper handles being stuck by prompting the agent to ask what simple cue it
might be missing. That asks the mind that is already stuck. Everything the
question wants is computable: actions never taken, values never clicked, reachable
squares never observed, rules the model itself flags as unsure, open journal
notes. On m0r0 L2 it immediately found that the corridor value had never been
clicked and 34 of 36 reachable squares had never been observed. Testing that lead
cost 1573 engine steps and ruled it out — a dead lead, but a closed one.

### `scripts/wm/score_rhae.py` — the benchmark's own metric
Every number reported before this was one we chose. `baseline_actions` sits on the
environment object. RHAE squares the ratio and scores unsolved levels zero with
the largest weights, so it is dominated by coverage, not efficiency. It also
prints "over solved levels only" and labels that as **not** the metric.

### Action budget — `Session.open(..., budget_x=5)`
5× the human baseline is the official leaderboard cutoff. Before this there was no
cap and one sk48 diagnostic spent 3229 engine steps. Raises `BudgetExceeded`.

### `scripts/wm/model_debt.py` — a simplicity gauge
Counts what makes a model less general: board coordinates baked into rules,
per-level branches, ignore masks, a missing renderer, rules flagged
`UNDER-DETERMINED`, retired rules still carried. Its own first run was wrong — it
counted coordinates *narrated in docstring prose* as hardcoded ones and therefore
reported the models getting worse at the moment real debt was removed. A
simplicity metric that miscounts is worse than none.

## Instrumentation

### The journal — `agents/wm/journal.py`
Append-only JSONL per game and level: `observe / probe / refute / author / plan /
execute / note`. Written **at the moment of discovery**, never reconstructed
afterwards, because an earlier generation of the visualizations rebuilt their
narrative from conversation context and that narrative died with the context.

Every entry carries what is needed to *replay* the situation, not just the
conclusion:

- `run` — an id per script run, so entries from different runs are not read as one sequence
- `at` — the action prefix that reproduces the frame the entry refers to
- `author.source` — the model's **actual text** and its sha, because a pointer resolves to whatever the file says today
- `refute.diff` — the pointed cells `[row, col, predicted, actual]`

### Cost — `ENGINE_STEPS`, `Meter`
Counts every engine step including the replays that reach a level. "36 probe
actions" was close to a lie: each probe re-opened a session first, so the real
cost was 1572. `Session.open` at tu93 L8 costs 157 steps.

### Pages — `artifacts/wm_viz/`
`index.html` is the methodology root; `<game>/paper.html` is a game's write-up;
`<game>/level.html` gives every level the same four views; `<game>/model_evolve.html`
re-runs every retired version against every level. Data comes from the journals
via `gen_site.py`. `scripts/check_viz_pages.py` checks what a browser would fail
at silently — it has caught the same duplicate-id bug three times.

## The dataset — `scripts/wm/export_dataset.py`

The journals are an audit trail first and a dataset second. The exporter emits
typed pairs and, just as importantly, writes what it **could not** build:

| type | input | target |
|---|---|---|
| `predict` | frame + action | next frame as a cell diff |
| `analyse` | frame | entities and structure |
| `probe` | frame + open question | actions to spend, and what came back |
| `plan` | frame | the action sequence that clears it |
| `repair` | model source + pointed bug | rewritten source + why |

`repair` is the one that teaches a model to *write* world models and it is the
scarcest. For tu93 it is unrecoverable: those author entries stored the string
`"see agents/wm/models/tu93.py"`, which resolves to a later version, and several
versions were authored inside one session so git does not have them either.

A pairing bug worth remembering: the exporter used to pair a refutation with the
*next* author entry, and the loop also writes routine `changed: none` entries when
a carried model simply passes — so the one usable pair had been paired with one of
those, teaching that the fix for a pointed bug is to do nothing.

## Who writes the model

`brain.propose(timeline, prev_model, last_report) -> WorldModel` exists in
`agents/wm/brain.py` and is called by `SolveLoop` in `loop.py`. **The current
scripts do not call it.** The models are written by Claude Code editing files
between conversational turns.

So the difference from the published systems is not "human versus LLM" — an LLM
writes the model in both. It is **in-loop versus conversational**: there, a
controller sends prompts and inspects session state with stopping conditions and
runtime recovery; here, the next step happens when the user types. Consequences:

- no unattended playthrough is possible
- our RHAE is not comparable to a published one: it was produced across sessions, reading prior journals, with the operator choosing which level to attack
- isolation is discipline, not engineering. `environment_files/` is on disk and "never read it" is a rule in `CLAUDE.md`. The paper removes the possibility with a container, a hidden game id, no web, and a client that refuses a second connection — because agents had exploited exactly those channels.

Closing this is the natural next step, and it is what makes everything above a
dataset rather than a demo: wire `SolveLoop` to the new pipeline with `propose()`
filled by an API model or a headless `claude -p`, add the action cap and
no-progress detection, and the work done by hand becomes recorded `propose()`
trajectories.
