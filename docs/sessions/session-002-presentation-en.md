# ARC-AGI-3: Simulator-Building Approach — Experiment Log

## 0. The Journey So Far

### Phase A: Master Plan → Manual Analysis of 1 Game

Created master-plan-gpt.md to define the essence of ARC-AGI-3:
- **"Not predicting next action, but reconstructing the world"**
- world model → hypothesis bank → motif retrieval → epistemic/instrumental planning
- Must be designed in a form transferable to small models (Qwen)

Based on this master plan, manually analyzed sk48 using Claude Code (harness.py). Created per-game **harness-narrative** documents.

→ Stored in `docs/harness-narratives/`

### Phase B: Scaffolding — solve_loop + agentic modules

Implemented the master plan's cognitive architecture in code:

```
agents/agentic/
  schemas.py              ← 40+ Pydantic models (ObservationSnapshot, BeliefLedger, DynamicsRule...)
  perception.py           ← Object tracking, role scoring (controllable/goal/blocker)
  experiment_designer.py  ← Epistemic probe selection (maximize information gain)
  phase_manager.py        ← EPISTEMIC / INSTRUMENTAL / RECOVERY mode switching
  surprise_auditor.py     ← Prediction vs reality comparison → hypothesis revision
  memory.py               ← Per-episode filesystem storage
  solve_loop.py           ← Full orchestration
```

At this stage, **heuristic placeholders** filled in without LLM. Data format was designed as intended — observation/belief/decision triplets saved per step.

→ Stored in `data/episodes/{game}-{id}/steps/`

### Phase C: LLM Brain Integration → Failed

Attached **llm_brain.py** (OpenAI API) to solve_loop — LLM decides actions each step.

**Problem**:
- API call per step → **context breaks** (previous observation/reasoning history not carried over)
- LLM judges 1 step at a time without full game context → no coherent strategy
- Cost/speed issues

→ Could not solve games with this approach

### Phase D: Claude Code (harness) Direct Play → Good for data collection

Claude Code CLI directly analyzes games:
- Claude Code = 1M token context → full history retained
- See frames, reason, write code, execute → **can solve games like a human**
- Discovered mechanics and strategies for sk48, tu93, etc.

**But critical problems**:
- **Every hypothesis check = replay game from scratch** → actions consumed exponentially
- 5 attempts = 5 scorecards = Level 0 replayed 5 times
- **Cannot use Claude Code on Kaggle** (requires internet)

→ Analysis records stored in `docs/harness-narratives/`, `docs/sessions/`

### Phase E: Simulator-Based Approach ← **WE ARE HERE**

To solve Phase D's problems:

```
Phase D problem:    Every hypothesis check = real game action consumed
                    ↓
Solution:           Check hypotheses in simulator (0 actions)
                    ↓
Required:           Observe → write simulator code → BFS → execute → fix
                    ↓
On Kaggle:          SLM (Qwen) performs this entire process
```

**Can we progressively build a simulator within 1 scorecard and solve the game?** — this is the current objective.

### Where the Data Lives

| Data | Location | Content |
|------|----------|---------|
| Master plan | `docs/strategy/master-plan-gpt.md` | Cognitive architecture, simulator section |
| Strategy comparison | `docs/strategy/search-strategies-comparison.md` | MCTS vs CLI vs Harness |
| Simulator approach | `docs/strategy/simulator-building-approach.md` | 4-phase loop, probabilistic model, SLM |
| Game analysis | `docs/harness-narratives/` | sk48, ls20, etc. |
| Session logs | `docs/sessions/session-002-*.md` | Full session records |
| Episode data | `data/episodes/{game}-{id}/` | observation/belief/decision/simulator |
| Simulator code | `agents/agentic/simulator.py` | BaseSimulator (abstract) |
| Game simulators | `agents/agentic/simulators/tu93_simulator.py` | tu93-specific |
| Schema definitions | `agents/agentic/schemas.py` | 40+ data models |
| Solver loop | `agents/agentic/solve_loop.py` | Full orchestration |

---

## 1. Phase B: Scaffolding — What Data We Collect and How

Before any game-solving, we built the **agentic infrastructure** — the data pipeline that captures everything the solver sees, thinks, and decides.

### Per-Step Data (3 files per action)

Every time the agent takes 1 action, three JSON files are saved:

| File | What it captures | Key fields |
|------|-----------------|------------|
| `observation.json` | What the agent **saw** | grid state, diff, objects (with persistent IDs, role scores), available actions |
| `belief.json` | What the agent **believes** | hypotheses (with confidence), dynamics rules, motifs, action semantics, subgoals |
| `decision.json` | What the agent **decided** | chosen action, rationale, expected outcome, simulator prediction |

### Modules in the Agentic Pipeline

```
perception.py         → Extracts objects, tracks identity across frames, scores roles
experiment_designer.py → Picks the most informative probe action (epistemic mode)
phase_manager.py      → Decides: explore more? or execute plan? or recover from failure?
surprise_auditor.py   → Compares prediction vs reality → revises beliefs
memory.py             → Saves everything to filesystem
solve_loop.py         → Orchestrates the full loop
```

Each module fills in **structured data** (Pydantic models in schemas.py — 40+ classes). Even when the solver is heuristic-only, the data format is production-ready.

→ Stored in `data/episodes/{game}-{id}/steps/step_NNNN.{observation,belief,decision}.json`

---

## 2. Phase C: LLM Brain — Why Per-Step API Calls Failed

Attached `llm_brain.py` to solve_loop — OpenAI API decides each action.

```
Step 1: Send grid + diff to LLM → LLM says "try ACTION4" → execute
Step 2: Send new grid + diff to LLM → LLM says "try ACTION1" → execute
  (LLM has NO MEMORY of step 1's reasoning!)
```

**Why it failed**:
- Each API call = independent. **No persistent context** across steps
- LLM can't build a world model because it forgets everything between calls
- Rolling memory window (last 4 steps) was too short for complex games
- Cost: ~$0.10 per step × hundreds of steps = expensive

**Key lesson**: Solving ARC-AGI-3 requires **sustained reasoning over the entire episode**, not independent per-step decisions. This is why Claude Code (1M token context) worked where API calls didn't.

---

## 3. Phase D: Claude Code Solves Games Directly

With the LLM Brain approach failing, tried having **Claude Code itself** play games interactively.

Started with **tu93** (maze + enemy avoidance):
- 64×64 grid, ACTION1-4 (directional)
- Claude Code sees frames, reasons about them, writes Python scripts, executes

### Discovered Mechanics
1. Grid composed of **3×3 block tiles** forming a graph (0-blocks=nodes, 2-blocks=edges, 5=walls)
2. Agent (9+4 block) **jumps** between nodes along edges
3. e(14) block = **goal**. Reaching it clears the level
4. From Level 1: **enemies (8+f blocks)** appear — horizontal entry → DEAD, vertical entry → SWAP (removes enemy)
5. Enemy's f/b pixel = **eye**. Entering the node in eye direction = eaten

### Results
- Level 0: Cleared in 18 actions (BFS)
- Level 1: Cleared in 10 actions (enemy-avoidance BFS)
- Level 2: 3 enemies + sight cones → unsolved

### The Problem with This Approach
- **Every hypothesis test = new game from scratch** → 5 scorecards consumed
- Level 0 replayed 5 times (90 wasted actions)
- Claude Code requires internet → **can't run on Kaggle**

---

## 4. Phase D→E: Why We Need Simulators (Three Approaches Compared)

Playing manually revealed **why this is hard**. Compared three approaches:

### MCTS (Ideal)
- With a simulator, try 10,000 "what if..." scenarios **for free**
- Only send the best 1 action to real game
- **Prerequisite: accurate simulator must exist**

### Harness LLM Agent (Current Approach)
- Each turn, ask LLM "what should I do?"
- **Exploration = Execution**. Every mistake costs a real action
- No look-ahead. 1-step reasoning (greedy)

### CLI BFS with Oracle (What I Did)
- Use real game engine as black-box oracle, replay from scratch each time
- **Accurate but slow** — O(N²) replay overhead
- Timed out at Level 3

### Comparison Table

|  | MCTS | CLI BFS | Harness LLM |
|--|------|---------|-------------|
| Search cost | 0 (simulated) | O(N²) replays | Every test = real |
| Plan quality | Optimal | Optimal (within depth) | Heuristic/greedy |
| Look-ahead | Deep (20+) | Deep but slow | None (1-step) |
| Enemy handling | Perfect model | Perfect (oracle) | "Probably moves left" |

---

## 5. Phase E: Build Simulators On-the-Fly

**Strongest approach**: Write simulator code from observations, then BFS/MCTS on top.

### Four-Phase Loop

```
Phase 1: EXPLORE — Spend real actions (small budget)
  → Observe mechanics with a few actions

Phase 2: MODEL — Write simulator code (0 action cost)
  → Generate simulate(state, action) function from observations

Phase 3: PLAN — Search over simulator (0 action cost)
  → Test 10,000 paths with 0 real actions

Phase 4: EXECUTE — Run only the optimal path
  → If prediction mismatches, return to Phase 2 and fix simulator
```

### Key Insight: Probabilistic Simulator

- Each mechanic carries a **confidence** score
- Confidence increases with consistent observations
- Prediction failures decrease confidence + trigger rule updates
- BFS only follows **high-confidence paths** (safe planning)

---

## 6. Phase E: Implementation + Validation

### What We Built

| File | Role |
|------|------|
| `simulator.py` | BaseSimulator (abstract) + Simulator (rule-based) |
| `simulators/tu93_simulator.py` | Game-specific: graph parsing + sight cone + eat/swap |
| `schemas.py` | SimulatorSnapshot, SimulatorEvolutionEntry |
| `solve_loop.py` | Simulator integration (build→predict→verify→update) |
| `memory.py` | evolution.jsonl logging |

### Progressive Simulator Building in 1 Scorecard

```
Step 1-4:   EPISTEMIC (4 actions) → Discover "3x3 block graph jumps"
Step 5:     Build simulator v1 (graph movement only)
Step 5-21:  v1 BFS clears Level 0 (17 actions)
Step 21:    Level 1 starts, enemy discovered → simulator v2 (collision/SWAP)
Step 22-31: v2 BFS clears Level 1 (10 actions)

Total: 31 actions, 2 levels, RHAE = 1.0 + 1.0 (both perfect!)
```

### Simulator Evolution History

| Version | Step | Trigger | Result |
|---------|------|---------|--------|
| v1 | 4 | epistemic probes | L0 ✓ (17 steps) |
| v2 | 21 | enemy discovered | L1 ✓ (10 steps) |
| v3 | 55 | L2 death → sight cone | L2 ✗ (BFS path actually unsafe) |

---

## 7. Key Lessons

### ✅ What Worked
- Progressive simulator building actually solves games
- v1→v2 upgrade within 1 scorecard → 5x more efficient than restarting
- RHAE perfect score achieved (more efficient than human baseline)

### ❌ What Didn't Work
- Level 2: 3 enemies with sight cones + chase mechanics → simulator-reality mismatch
- **Repeated same failure** — no logic to change strategy after failed prediction
- **ls20**: Goal inference failure — couldn't determine win condition at all

### 💡 What We Learned
1. **LLM is essential for simulator building** — pattern matching can't achieve structural understanding
2. **Enemy behavior differs per level** — must learn per-level
3. **Goal inference precedes simulator building** — can't define BFS goal_test without knowing the goal
4. **On Kaggle, SLM must do this** — replace Claude with Qwen

---

## 8. Connection to Kaggle Strategy

### What SLM Must Do

```
Claude Code (local dev)              Qwen 3.5 (Kaggle)
───────────────────                  ───────────────────
Observe frames → infer mechanics     Must do the same
Write simulator code                 Must do the same
Fix simulator on failure             Must do the same
BFS/MCTS on simulator                Must do the same
```

### SFT Data = Simulator Evolution Logs

```
Input:  "New entity: 8-block with f marker at offset (0,-1)"
Output: "if agent enters enemy cell horizontally → DEAD
         if agent enters enemy cell vertically → SWAP
         Confidence: 0.7"
```

These (observation, simulator_update) pairs train SLM to "translate observations into code."

### Per-Game Simulator Files

```
simulators/
  tu93_simulator.py  ← Created this session
  ls20_simulator.py  ← Next target
  common_patterns.py ← Reusable: graph_movement, sight_cone, etc.
```

Retry same game → load previous simulator → skip re-learning.

---

## 9. ls20 Analysis (In Progress)

Completely different challenge from tu93 — **simple mechanics but opaque goal**.

### Discovered
- c(12)+9 block moves in 5-cell increments (the tool)
- 0/1 pattern = transform operator (fixed position)
- Moving c-block through 0/1 **transforms the bottom-left reference pattern**
- Reference cycles through 4 states (4 crossings = back to original)
- Only LEFT-direction crossing triggers transformation

### Unsolved
- **Win condition unknown** — matching ref to top room pattern didn't trigger WIN
- 130 action budget (3 rounds) before GAME_OVER
- **Goal inference is the core challenge**

---

## 10. Next Steps

1. **ls20 goal inference**: Claude Code observes and reasons about WIN condition directly
2. **tu93 Level 2**: Precise observation of enemy chase mechanics → simulator v4
3. **Failure repetition prevention**: Auto-switch strategy after 2 deaths on same path
4. **SLM training**: Build Qwen SFT dataset from Claude session logs

---

## 11. Data Collection & Storage Architecture

### Three Data Files Per Step

```
step_0001.observation.json  ← What the agent SAW
step_0001.belief.json       ← What the agent BELIEVES
step_0001.decision.json     ← What the agent DECIDED
```

#### Observation (What did the agent see?)
```json
{
  "step_index": 1,
  "grid_rows": 64, "grid_cols": 64,
  "diff_summary": "19 cells changed",
  "available_actions": ["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
  "objects": [
    {
      "persistent_id": "P_○0_3",
      "value": 9, "cell_count": 8,
      "bbox": {"row_min": 16, "row_max": 18, "col_min": 15, "col_max": 17},
      "controllable_score": 0.8,
      "goal_score": 0.0,
      "blocker_score": 0.0
    }
  ],
  "compressed_grid": "...(RLE)...",
  "map2d": "...(ASCII visualization)..."
}
```

#### Belief (What does the agent believe about the world?)
```json
{
  "step_index": 1,
  "mode": "epistemic",
  "top_motifs": [{"name": "navigation", "confidence": 0.7}],
  "hypotheses": [
    {
      "hypothesis_id": "H0",
      "summary": "Game follows a 'navigation' motif",
      "confidence": 0.7, "status": "provisional",
      "evidence": ["directional actions available"]
    }
  ],
  "dynamics_rules": [
    {
      "rule_id": "DR_1", "action_name": "ACTION4",
      "effect": "moves controllable P_○0_3 right ~6 cells",
      "confidence": 0.30, "times_verified": 1, "times_violated": 0
    }
  ],
  "action_semantics": {"ACTION4": ["moves agent right"]},
  "active_subgoals": []
}
```

#### Decision (What did the agent decide and why?)
```json
{
  "step_index": 1,
  "mode": "epistemic",
  "chosen_action": "ACTION4",
  "rationale": "Epistemic probe: test ACTION4 effect",
  "expected_outcome": "Agent moves right",
  "simulator_version": 0,
  "simulator_prediction": "agent moves to (17, 23)",
  "simulator_correct": true
}
```

### Simulator Evolution Log

```
episode_{id}/simulator/
  evolution.jsonl        ← Appended each time simulator changes
  simulator_v000.json    ← v0 snapshot
  simulator_v001.json    ← v1 snapshot (after surprise update)
```

#### evolution.jsonl Example
```jsonl
{"step_index":5,"version_before":0,"version_after":0,"trigger":"initial_build","rules_added":["move_up","move_right","collision_death","goal_reached"]}
{"step_index":16,"version_before":0,"version_after":1,"trigger":"surprise_update","rules_added":["enemy_mirror"],"prediction_that_failed":"action=ACTION4","actual_observation":"diff=19, GAME_OVER"}
```

### Full Directory Structure

```
data/episodes/{game_id}-{episode_hash}/
│
├── episode.json                    ← Metadata (game_id, tags, timestamp)
├── episode_trace.jsonl             ← Compressed trajectory (1 line per step)
│
├── simulator/                      ← ★ Simulator evolution records
│   ├── evolution.jsonl             ← Version-by-version change history
│   ├── simulator_v000.json         ← Initial simulator snapshot
│   └── simulator_v001.json         ← Updated snapshot
│
└── steps/                          ← Per-step detailed data
    ├── step_0001.observation.json
    ├── step_0001.belief.json
    ├── step_0001.decision.json
    └── ...
```

### How This Data Feeds Into SFT

```
Observation + Belief → "What the agent knows"            = SFT Input
Decision (action + rationale + simulator_update)         = SFT Output

The simulator evolution is the key signal:
  (observation, prediction_failure, simulator_code_fix) tuples
  = Supervision for teaching SLM "how to turn observations into code"
```

---

## Related Documents

- `docs/strategy/search-strategies-comparison.md` — Detailed MCTS vs CLI vs Harness comparison
- `docs/strategy/simulator-building-approach.md` — Simulator approach + probabilistic model + SLM strategy
- `docs/strategy/master-plan-gpt.md` — "Simulator as code" section added
- `docs/sessions/session-002-simulator-evolution.md` — Full session log
