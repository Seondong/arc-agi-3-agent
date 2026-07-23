<!-- [Mar 29] Created by SD with GPT-5.4. -->
# StochasticGoose 10-Game Report

## Run info

- Runner: [`run_stochasticgoose_scorecard.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/run_stochasticgoose_scorecard.py)
- Agent implementation: [`cnn_agent.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/templates/cnn_agent.py)
- Scorecard URL: `https://three.arcprize.org/scorecards/439a841e-280c-412b-b2a5-c74555203d7f`
- Recordings directory: [`recordings_stochasticgoose`](/Users/sundong/Documents/arc-agi-3/recordings_stochasticgoose)

## Summary

- Games run: 10
- Wins: 0
- Total levels completed: 0
- Final state for every game: `NOT_FINISHED`

Games:

- `bp35-0a0ad940`
- `sp80-0ee2d095`
- `ls20-9607627b`
- `tu93-2b534c15`
- `ka59-9f096b4a`
- `wa30-ee6fef47`
- `r11l-aa269680`
- `s5i5-a48e4b1d`
- `sb26-7fbdac44`
- `cd82-fb555c5d`

## Primary Finding

The strongest signal is not just "the CNN baseline is weak." In these 10 recordings, the agent appears to have submitted `RESET` on every step.

Evidence:

- `GameAction.RESET` is enum value `0`, while `ACTION1..6` are `1..6`.
- In every recording file, `action_input.id` was only `0`.
- This happened even when the frame state was already `NOT_FINISHED` and the environment exposed valid non-reset actions.

Examples:

- [`ls20-9607627b.cnnagent.d7705854-f650-4da1-826d-b51ce159ca40.recording.jsonl`](/Users/sundong/Documents/arc-agi-3/recordings_stochasticgoose/ls20-9607627b.cnnagent.d7705854-f650-4da1-826d-b51ce159ca40.recording.jsonl)
- [`bp35-0a0ad940.cnnagent.f73708d2-4c0c-4efc-9e8c-003faad202a3.recording.jsonl`](/Users/sundong/Documents/arc-agi-3/recordings_stochasticgoose/bp35-0a0ad940.cnnagent.f73708d2-4c0c-4efc-9e8c-003faad202a3.recording.jsonl)

This means the current result should be treated as a control/debug run failure before treating it as a pure policy-quality failure.

## Game-by-game Snapshot

- `bp35-0a0ad940`: 97 recorded steps, only action id `0`, max level `0`, states included `GAME_OVER`
- `cd82-fb555c5d`: 94 recorded steps, only action id `0`, max level `0`
- `ka59-9f096b4a`: 94 recorded steps, only action id `0`, max level `0`
- `ls20-9607627b`: 140 recorded steps, only action id `0`, max level `0`, one `GAME_OVER`
- `r11l-aa269680`: 136 recorded steps, only action id `0`, max level `0`, states included `GAME_OVER`
- `s5i5-a48e4b1d`: 136 recorded steps, only action id `0`, max level `0`, states included `GAME_OVER`
- `sb26-7fbdac44`: 94 recorded steps, only action id `0`, max level `0`
- `sp80-0ee2d095`: 102 recorded steps, only action id `0`, max level `0`, states included `GAME_OVER`
- `tu93-2b534c15`: 141 recorded steps, only action id `0`, max level `0`, states included `GAME_OVER`
- `wa30-ee6fef47`: 139 recorded steps, only action id `0`, max level `0`

## Interpretation

There are two plausible explanations.

1. The agent is truly sending `RESET` every turn.
   - If so, the issue is upstream of score quality.
   - The most likely problem is a mismatch between chosen `GameAction` objects and what the environment actually receives or records.

2. The recording field is stale or misleading.
   - If `action_input` is not the action that was just chosen, then the scorecard still says the run made no progress, and the logging path needs verification.

Given that all 10 files show only `action_input.id = 0`, explanation 1 is currently the more actionable assumption.

## Why This Matters

[`cnn_agent.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/templates/cnn_agent.py) does contain non-reset action logic in `_choose_with_model()` and `_random_action()`. So the observed behavior does not match the intended code path.

Relevant code:

- [`cnn_agent.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/templates/cnn_agent.py): `_choose_with_model()`
- [`cnn_agent.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/templates/cnn_agent.py): `choose_action()`

The key inconsistency is:

- code intent: choose `ACTION1..6`
- observed recording: only `RESET`

## Recommended Next Step

Before comparing stochasticgoose vs hybrid on score, add a tiny debug patch to the CNN runner or agent that logs:

- `latest_frame.state`
- chosen `action.name`
- chosen `action.value`
- `available_actions`

immediately before the action is returned to the environment.

If that debug log shows non-reset actions but recordings still show `0`, then the bug is in transmission/recording.
If the debug log also shows `RESET`, then the bug is in the agent decision path.
