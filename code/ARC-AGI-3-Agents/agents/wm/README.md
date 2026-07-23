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
| `brain.py` | `Brain` protocol; `CallableBrain` (offline); `ClaudeBrain` (Opus authors the world-model code — implemented: streams `claude-opus-4-8` with adaptive thinking, execs the returned callables). |
| `trace.py` | `TraceWriter` + `TraceRecord` in the 6-stage `data-logging-principles` schema; `sparse_frame`. |
| `loop.py` | `SolveLoop` — the outer loop and all three invariants. |
| `env.py` | `Environment` protocol + `GraphMazeEnv` synthetic tu93-like fixture. |
| `env_arcagi.py` | `ArcAgiEnv` — adapts the offline `arc_agi` Arcade to the `Environment` protocol (lazy import; runs on a host with the game engine). |
| `run_game.py` | CLI: play a real game (`--game tu93`) with `ClaudeBrain`, or a hand-written reference model via `--reference-model`. |
| `reference_models.py` | Correct + deliberately-wrong maze world models (stand-ins for what a brain emits). |
| `tests/test_wm.py` | End-to-end proof of the three invariants + BFS death-pruning. |
| `tests/test_env_arcagi.py` | Adapter status/level-up/RESET-filter mapping, via a fake engine (no arc_agi). |
| `demo.py` | Solve the maze, write a trace JSONL, print the records. |

## What is real vs stubbed

**Real and tested offline:** the full control loop; backtest with pointed-bug
reporting; BFS-in-model with death pruning; reality-outranks-model plan halting;
the trace schema (`demo.py`); the `arc_agi` adapter's status mapping
(`tests/test_env_arcagi.py`, fake engine).

**Written, exercised only on the Mac** (need the game engine / model creds — not
runnable in a bare container):
- `ClaudeBrain.propose` — streams `claude-opus-4-8` (adaptive thinking, `effort`),
  extracts the ```python block, execs it into `reconstruct/step/render/is_goal`,
  wraps a `WorldModel`. Needs `ANTHROPIC_API_KEY` (or an `ant auth login` profile).
- `ArcAgiEnv` — drives `Arcade(OperationMode.OFFLINE)` exactly as
  `agents/agentic/solve_loop.py` does. Needs `pip install arc-agi` + game files.

**Next steps (deliberate seams):**
- **Multi-attempt history** — on `GAME_OVER` the skeleton ends the attempt and
  keeps the counterexample; Baseline1 instead RESETs and backtests across *all*
  recorded attempts. Extend `Timeline` to hold attempts for cross-attempt
  refutation. (Biggest gap for real games.)
- **Render-exact vs HUD noise** — real frames include a step counter/HUD that
  changes every step, so the model's `render()` must reproduce it (or the
  backtest needs a region mask). Opus can model the counter; watch for this on
  the first real run.
- Experiment designer — `_explore` in `loop.py` is round-robin; replace with the
  max-information-gain / hypothesis-discrimination probe selector.
- Richer perception — `sparse_frame` is a minimal object encoder; the existing
  `agents/agentic/perception.py` can back it.

## Run

Offline (no engine, no model — works anywhere):
```bash
cd code/ARC-AGI-3-Agents
python3 agents/wm/tests/test_wm.py          # 4/4
python3 agents/wm/tests/test_env_arcagi.py  # adapter mapping
python3 agents/wm/demo.py                    # writes agents/wm/trace_demo.jsonl
```

On the Mac (real game + Opus):
```bash
export ANTHROPIC_API_KEY=...        # or: ant auth login
python3 agents/wm/run_game.py --game tu93 --max-steps 200
```

`--reference-model mod:factory` runs a hand-written `WorldModel` via
`CallableBrain` instead of Opus — useful to validate the loop against a
known-good model (e.g. port `agents/agentic/simulators/tu93_simulator.py` to the
`reconstruct/step/render/is_goal` interface and pass its factory here).
