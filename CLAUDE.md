# ARC-AGI-3 Agent Project

## Project Goal
Build an LLM-based agent for ARC-AGI-3 (ARC Prize 2026 Kaggle competition), starting from a working baseline and iterating toward high scores. The approach builds on the ralph-loop self-evolving agent pattern.

## What is ARC-AGI-3

ARC-AGI-3 is an **interactive reasoning benchmark** — completely different from ARC-AGI-1/2 (static grid transformations). Agents play turn-based 2D grid games where they must:
- **Explore** environments with unknown rules
- **Infer goals** — the agent is NEVER told the objective or win condition
- **Build world models** from observations
- **Plan and execute** action sequences efficiently

Frontier AI scores as of March 2026: Gemini 3.1 Pro 0.37%, GPT 5.4 0.26%, Opus 4.6 0.25%. The preview competition winner (StochasticGoose) scored 12.58% using a CNN approach. Humans solve 100%.

## Game Environment

### Grid
- Max 64×64, cell values 0–15 (16 colors), (0,0) top-left
- Each turn: agent receives frame(s) as JSON, responds with one action
- Game states: `NOT_FINISHED`, `WIN`, `GAME_OVER`
- Each game has multiple levels of increasing difficulty

### Actions (7 total, varies per game)
| Action | Description |
|--------|-------------|
| `RESET` | Start/restart game/level |
| `ACTION1–4` | Directional (up/down/left/right semantically) |
| `ACTION5` | Interact (select, rotate, execute, etc.) |
| `ACTION6` | Complex: requires (x, y) coordinates, range 0–63 |
| `ACTION7` | Undo |

**Critical:** Action meanings vary per game. The agent must discover what each action does. Each frame's metadata indicates which actions are available.

### Game Design Constraints
- Core Knowledge priors only (objectness, basic geometry, basic physics, agentness)
- No language, no cultural symbols
- Tutorial level first (intentionally easy), difficulty via composition
- Multiple mechanics per game, minimum 6 levels
- Random policy win probability < 1/10,000 per non-tutorial level

## Scoring (RHAE — Relative Human Action Efficiency)

### Formula
```
level_score = min(1.0, human_baseline / ai_actions)²    # SQUARED!
game_score = weighted_avg(level_scores, weights=[1,2,3,...,n])  # 1-indexed linear weights
total_score = mean(all game_scores)
```

### Key implications
- Score is SQUARED: 2x human actions → 25% credit, 10x → 1% credit
- Level 1 contributes least (1/15 for 5-level game), Level 5 most (5/15)
- Cap at 1.0 per level (no bonus for beating humans)
- Official leaderboard uses 5x human baseline cutoff per level
- Internal reasoning/tool calls do NOT count as actions — only environment interactions count

### Human baselines
- 2nd-best human (fewest actions) per game, from first-time players
- 486 participants tested across 414 candidate environments
- Median successful attempt: 8.1 minutes

## Datasets
| Set | Count | Purpose |
|-----|-------|---------|
| Public | 25 | Demo only, intentionally easier, mechanics don't overlap with private |
| Semi-private | 55 | Tests frontier models via API (external API calls allowed) |
| Fully private | 55 | Kaggle competition evaluation (no internet) |

**Private set is intentionally OOD from public set.** Harnesses tuned on public games do NOT generalize.

## Development Infrastructure

### Two repos + benchmarking tool
1. **`arc-agi` (Toolkit)**: `pip install arc-agi` — local/online execution, environment engine, scorecard management
2. **`ARC-AGI-3-Agents`**: Agent framework with `main.py`, Swarm for parallel execution
3. **`arc-agi-3-benchmarking`**: Model/prompt comparison tool (beta)

### Local vs Online
```python
from arc_agi import Arcade, OperationMode

# Local: fast (2K+ FPS), no rate limits, no API key needed
arc = Arcade(operation_mode=OperationMode.OFFLINE)

# Online: scorecards + replays recorded
arc = Arcade(operation_mode=OperationMode.ONLINE)
```

### Running agents
```bash
# Single game
uv run main.py --agent=myagent --game=ls20

# All games (swarm)
uv run main.py --agent=myagent

# With tags
uv run main.py --agent=myagent --tags="experiment,v1"
```

### Example games
- `ls20` — Agent reasoning
- `ft09` — Elementary logic
- `vc33` — Orchestration

## Agent Interface

```python
from agents.agent import Agent
from arcengine import FrameData, GameAction, GameState

class MyAgent(Agent):
    MAX_ACTIONS = float('inf')

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        if latest_frame.state in [GameState.NOT_PLAYED, GameState.GAME_OVER]:
            action = GameAction.RESET
            action.reasoning = "Reset"
            return action

        # Your logic here
        action = GameAction.ACTION1
        action.reasoning = "Reasoning text for replay"
        return action

        # For ACTION6 (coordinate-based):
        # action = GameAction.ACTION6
        # action.set_data({"x": 10, "y": 20})
        # action.reasoning = "Click at (10, 20)"
```

### FrameData fields
- `frame`: list of 2D arrays (frame sequence), last element is current grid
- `state`: GameState enum
- `levels_completed`: int
- `available_actions`: list of available action IDs
- `guid`: game session ID

### Registering an agent
```python
# agents/__init__.py
from .my_agent import MyAgent

AVAILABLE_AGENTS: dict[str, Type[Agent]] = {
    "myagent": MyAgent,
}
```

## Kaggle Submission Pattern

The notebook structure is fixed — only `my_agent.py` content changes:

```python
# Cell 1: Install from bundled wheels (no internet)
!pip install --no-index --find-links \
    /kaggle/input/competitions/arc-prize-2026-arc-agi-3/arc_agi_3_wheels \
    arc-agi python-dotenv

# Cell 2: %%writefile /kaggle/working/my_agent.py
# ... your agent code ...

# Cell 3: Competition rerun logic
import os
if os.getenv('KAGGLE_IS_COMPETITION_RERUN'):
    # Wait for gateway
    !curl --fail --retry 999 --retry-all-errors --retry-delay 5 \
          --retry-max-time 600 http://gateway:8001/api/games

    # Copy repo to writable location
    !cp -r /kaggle/input/competitions/arc-prize-2026-arc-agi-3/ARC-AGI-3-Agents \
           /kaggle/working/ARC-AGI-3-Agents

    # Copy custom agent
    !cp /kaggle/working/my_agent.py \
        /kaggle/working/ARC-AGI-3-Agents/agents/templates/my_agent.py

    # Minimal __init__.py to avoid unmet dependency imports
    with open('/kaggle/working/ARC-AGI-3-Agents/agents/__init__.py', 'w') as f:
        f.write("""from typing import Type, cast
from dotenv import load_dotenv
from .agent import Agent, Playback
from .swarm import Swarm
from .templates.my_agent import MyAgent
load_dotenv()
AVAILABLE_AGENTS: dict[str, Type[Agent]] = {
    "myagent": MyAgent,
}
""")

    # .env for gateway connection
    with open('/kaggle/working/ARC-AGI-3-Agents/.env', 'w') as f:
        f.write("""SCHEME=http
HOST=gateway
PORT=8001
ARC_API_KEY=test-key-123
ARC_BASE_URL=http://gateway:8001/
OPERATION_MODE=online
ENVIRONMENTS_DIR=
RECORDINGS_DIR=/kaggle/working/server_recording
""")

    # Run
    !cd /kaggle/working/ARC-AGI-3-Agents && \
        MPLBACKEND=agg python main.py --agent myagent

# Cell 4: Dummy submission for non-rerun
if not os.getenv('KAGGLE_IS_COMPETITION_RERUN'):
    import pandas as pd
    submission = pd.DataFrame(
        data=[['1_0', '1', True, 1]],
        columns=['row_id', 'game_id', 'end_of_game', 'score'])
    submission.to_parquet('/kaggle/working/submission.parquet', index=False)
```

### Kaggle environment constraints
- **No internet** during competition rerun
- Gateway at `http://gateway:8001` provides game API
- Packages must be bundled or pre-installed (arc-agi wheels are provided)
- `KAGGLE_IS_COMPETITION_RERUN` env var distinguishes dry run vs actual evaluation
- For Kaggle: NO external LLM API calls possible. Must use local model or non-LLM approach.

### Kaggle CLI submission
```bash
kaggle competitions submit \
  -c arc-prize-2026-arc-agi-3 \
  -f submission.parquet \
  -k sundong/<NOTEBOOK> \
  -v <VERSION> \
  -m "Message"
```

## Reference: StochasticGoose (12.58%, Preview 1st Place)

CNN-based agent that learns online which actions cause frame changes:

### Architecture
- 4-layer CNN backbone (16ch one-hot → 32 → 64 → 128 → 256)
- Action head: MaxPool → FC(512) → 5 logits (ACTION1–5)
- Coordinate head: Conv(128→64→32→1) → 64×64 logits (ACTION6 coordinates)

### Training loop
- Each step: store (prev_frame, action, frame_changed?) as experience
- reward = 1.0 if frame changed, 0.0 if not
- Train every 5 steps with batch_size=64, binary cross-entropy
- Entropy regularization to encourage exploration
- Reset model + buffer on level change

### Key design choices
- Sliding window of 10 frames max (memory efficiency)
- Experience deduplication via MD5 hashing
- 8-hour timeout
- Sigmoid probabilities for sampling (not softmax)
- Available action masking

### Weakness
"Frame changed = good" is a crude heuristic. No goal inference, no planning, no world model beyond "what makes things move." Still beat all other approaches at 12.58%.

## Strategy: LLM Agent → Local Model Pipeline

### Phase 1: Working LLM Agent (Claude API, local dev)
- Implement `choose_action` using Claude API
- Prompt: current grid state + action history + frame diffs
- Explore → build rules → plan → execute
- ralph-loop pattern: accumulate discovered rules across steps

### Phase 2: Optimize for efficiency
- Separate exploration phase (discover mechanics) from execution phase (minimal actions)
- Use UNDO (ACTION7) strategically during exploration
- Compress frame representation (diff-based, not full grid each time)

### Phase 3: Kaggle submission via local model
- Options: Qwen 3.5 7B, or similar model that fits in Kaggle GPU
- Distill LLM agent strategies into smaller model, or
- Hybrid: CNN (StochasticGoose-style) + small LM for planning
- Must run without internet

## Key Technical Notes

### Frame representation for LLM
The 64×64 grid with 16 colors is large. Strategies to compress:
- Only send diff from previous frame
- Identify and describe objects rather than raw grid
- Use run-length encoding or sparse representation
- Focus on the "interesting" region (crop empty borders)

### Context management
ARC-AGI-3's biggest LLM challenge is context. At 64×64×16 one-hot, each frame is huge.
- Duke University approach: let model execute Python code to query action history
- Symbolica (Arcgentica): orchestrator + subagents with compressed summaries
- StochasticGoose: just 10-frame sliding window, no LLM context issue

### What makes a good ARC-AGI-3 agent
1. **Exploration efficiency**: systematically discover what each action does with minimal tries
2. **World modeling**: build accurate internal model of environment dynamics
3. **Goal inference**: figure out the win condition without being told
4. **Planning**: find shortest action sequence to goal state
5. **Cross-level transfer**: mechanics learned in level 1–2 apply to later levels
