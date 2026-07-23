<!-- Created with Claude Opus during the harnessing session. -->
# `wm` — verified executable world-model solve core

This package is the **heart the earlier agentic framework never had**: a
persistent, executable world model that is *certified against the full recorded
history* and *planned inside for free*. It is the synthesis we chose after
reviewing the released Schema and Baseline1 harnesses — their proven loop shape,
instrumented to emit the project's own `data-logging-principles` traces so every
episode doubles as distillation data.

Status: **runnable skeleton, tested end-to-end offline.** No game files, no model
API, no numpy required. `python agents/wm/tests/test_wm.py` → 4/4.

## The loop

```
observe ─▶ deliberate ─▶ execute ─▶ record ─▶ (repeat)
             │
             ├─ theorize : brain authors world_model = (reconstruct, step, render, is_goal)
             ├─ certify  : run_backtest replays the WHOLE timeline — exact match or a pointed bug
             └─ plan     : run_bfs searches inside a certified model (zero real cost)
```

Three invariants are enforced (the Schema constraints, made concrete):

1. **The world model is executable code**, authored by the brain each round.
2. **It is certified against the full history** before it is trusted to plan —
   `run_backtest` must be green. (This is the organ the old `surprise_auditor`
   lacked: it checked one step, not the whole trajectory.)
3. **Reality outranks the model** — a single mispredicted transition during
   execution voids the plan and forces re-deliberation.

Only `env.step` costs real actions; backtest and BFS are free. That is where the
RHAE win comes from: pay to discover a mechanic once, then plan every later
level inside the model.

## Files

| File | Role |
| --- | --- |
| `core.py` | `Action`, `Frame`, `Status`, `Transition`, `Timeline` (append-only history), `WorldModel` (the four brain-authored callables). |
| `backtest.py` | `run_backtest` → exact match or a **pointed bug** (first divergence, predicted vs actual). `reconstruct_current_state`. |
| `planner.py` | `run_bfs` — shortest safe action sequence inside a certified model; prunes predicted `GAME_OVER`. |
| `brain.py` | `Brain` protocol; `CallableBrain` (offline); `ClaudeBrain` (frontier seam — `build_prompt` implemented, API call stubbed). |
| `trace.py` | `TraceWriter` + `TraceRecord` in the 6-stage `data-logging-principles` schema; `sparse_frame`. |
| `loop.py` | `SolveLoop` — the outer loop and all three invariants. |
| `env.py` | `Environment` protocol + `GraphMazeEnv` synthetic tu93-like fixture. |
| `reference_models.py` | Correct + deliberately-wrong maze world models (stand-ins for what a brain emits). |
| `tests/test_wm.py` | End-to-end proof of the three invariants + BFS death-pruning. |
| `demo.py` | Solve the maze, write a trace JSONL, print the records. |

## What is real vs stubbed

**Real and tested:** the full control loop, backtest with pointed-bug reporting,
BFS-in-model with death pruning, reality-outranks-model plan halting, and the
trace schema (verified by `demo.py`).

**Stubbed / next steps (deliberate seams):**
- `ClaudeBrain.propose` — wire the Opus call on a host with model access. The
  prompt contract (`build_prompt`) is implemented; it needs: call the model →
  exec the returned code into `reconstruct/step/render/is_goal` → wrap in
  `WorldModel`. This is the one piece that needs the driver model.
- `arc_agi` adapter — implement the `Environment` protocol over the offline
  Arcade (`OperationMode.OFFLINE`) so the loop plays real games. Runs on the Mac
  where the game files live.
- **Multi-attempt history** — on `GAME_OVER` the skeleton ends the attempt and
  keeps the counterexample; Baseline1 instead RESETs and backtests across *all*
  recorded attempts. Extend `Timeline` to hold attempts for cross-attempt
  refutation.
- Experiment designer — `_explore` in `loop.py` is round-robin; replace with the
  max-information-gain / hypothesis-discrimination probe selector.
- Richer perception — `sparse_frame` is a minimal object encoder; the existing
  `agents/agentic/perception.py` can back it.

## Run

```bash
cd code/ARC-AGI-3-Agents
python3 agents/wm/tests/test_wm.py   # 4/4
python3 agents/wm/demo.py            # writes agents/wm/trace_demo.jsonl
```
