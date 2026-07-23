"""Convert the hand-curated sk48 L0 winning solution into SFT training JSONL.

Reads the 24-action winning sequence from sk48_reasoning_chain.md (verified by
harness.py to clear L0 with score 1.0), replays it through Arcade OFFLINE, and
pairs each step's state with a 6-stage reasoning chain authored from the
markdown narrative.

Output format matches convert_episodes_to_sft.py so train_qwen_sft.py can
ingest it directly.

Usage:
    uv run python scripts/build_sk48_gold.py \
        --output artifacts/sft_gold/sk48_gold.jsonl
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction

from agents.grid_lib import compress_grid, diff_cell_count


SYSTEM_PROMPT = (
    "You are playing an ARC-AGI-3 game. "
    "Based on the observation, choose the best action."
)


# ---------------------------------------------------------------------------
# Verified winning sequence for sk48 L0 (24 game actions).
# Source: data/sk48_reasoning_chain.md (5th attempt, 5th section).
# Verified 2026-04-20 via harness.py: clears L0 in 24 steps, score 1.0.
# ---------------------------------------------------------------------------

@dataclass
class StepNote:
    action: str
    intent: str       # what this action is doing (one line)
    strategy: str     # why THIS action now (one line, references plan)
    predict: str      # expected outcome
    learned: str = "" # what the previous action just taught (fills RESULT/REVISE)


SK48_GAME_ID_PREFIX = "sk48"


STEPS: list[StepNote] = [
    # UP×3 → R20 (♥ height). Diamond player at R42, ♥ block at R19-22.
    StepNote(
        action="ACTION1",
        intent="Move UP toward the ♥ block height (R20).",
        strategy=(
            "Plan: thread blocks in reference order ♦→♥→⑭→◆. ♥ is the "
            "nearest-to-diamond wall block, and per 'closest-after-retract' "
            "rule it must be threaded first. Diamond starts at R42; ♥ is at "
            "R19-22. One ACTION1 moves the diamond up 6 rows."
        ),
        predict=(
            "~100 cells change. Diamond cluster shifts from R42 to R36."
        ),
    ),
    StepNote(
        action="ACTION1",
        intent="Move UP again toward ♥ height.",
        strategy="Still approaching R20. Diamond at R36 → R30 after this step.",
        predict="~100 cells change. Diamond R36 → R30. No wall contact yet.",
        learned=(
            "Previous ACTION1 produced expected large diff. "
            "ACTION1 confirmed as UP by 6 rows (directional, not click)."
        ),
    ),
    StepNote(
        action="ACTION1",
        intent="Final UP to reach ♥ height (R20).",
        strategy=(
            "After this, diamond head at R24 and trail can extend into ♥ row. "
            "Next action should be ACTION4 (extend) to thread ♥."
        ),
        predict="~100 cells change. Diamond R30 → R24.",
        learned="Pattern: each ACTION1 shifts diamond block up 6 rows.",
    ),
    # ACTION4 × 4 → extend tail to reach and thread ♥ (C42-45)
    StepNote(
        action="ACTION4",
        intent="Extend tail one step to the right.",
        strategy=(
            "Trail is the ●② pattern at R20; each ACTION4 grows it +6 columns. "
            "Need ~4 extends to reach ♥ at C42-45."
        ),
        predict="~13 cells change. Trail tip advances 6 cols right.",
        learned="Diamond reached target R24 as expected.",
    ),
    StepNote(
        action="ACTION4",
        intent="Extend tail further toward ♥.",
        strategy="Continuing extension; no collision yet.",
        predict="~13 cells change. Trail tip advances 6 more cols.",
    ),
    StepNote(
        action="ACTION4",
        intent="Extend tail — should be at C36 approximately.",
        strategy="One or two more extends to reach ♥ at C42-45.",
        predict="~13 cells change. Tip at C36-ish.",
    ),
    StepNote(
        action="ACTION4",
        intent="Extend tail — should thread through ♥ block.",
        strategy="This extension should pass through ♥(C42-45) and hit the wall.",
        predict=(
            "Large diff: tail threads ♥ block. Expect ~25+ cells change "
            "including ♥ cells being overlaid."
        ),
    ),
    # ACTION3 × 3 → partial retract, pull ♥ to C24 while keeping trail connected
    StepNote(
        action="ACTION3",
        intent="Partial retract — pull ♥ inward while keeping trail intact.",
        strategy=(
            "Critical: partial retract keeps ♥ attached to trail. Full retract "
            "(all the way to diamond) would detach ♥ — not recoverable. "
            "Target: ♥ at around C24 so it is in a DIFFERENT column from ◆ "
            "(C42), enabling DOWN without collision push."
        ),
        predict="~13 cells change. Trail shortens, ♥ moves left with it.",
        learned="Tail now threads ♥. Going to retract partially next.",
    ),
    StepNote(
        action="ACTION3",
        intent="Continue partial retract.",
        strategy="♥ should now be at ~C30. One more retract to reach C24.",
        predict="~13 cells change. ♥ moves closer to diamond.",
    ),
    StepNote(
        action="ACTION3",
        intent="Final partial retract to put ♥ at C24.",
        strategy=(
            "Stop here — trail still connected, ♥ positioned at C24 "
            "(safely different from ◆ at C42)."
        ),
        predict="~13 cells change. ♥ now at C24.",
    ),
    # ACTION2 × 2 → DOWN to ⑭ height (R32). Different-column test.
    StepNote(
        action="ACTION2",
        intent="DOWN toward ⑭ block height.",
        strategy=(
            "Diamond moves down 6 rows. Trail+♥ follow. Key hypothesis to "
            "test: does ♥ at C24 push ◆ at C42 when at same row? Per "
            "column-based collision rule, NO (different columns)."
        ),
        predict=(
            "Large diff (~130 cells): diamond+trail+♥ shift down. "
            "◆ at R25 should NOT move (different column)."
        ),
        learned="♥ successfully at C24, trail intact.",
    ),
    StepNote(
        action="ACTION2",
        intent="Final DOWN to ⑭ height (R32).",
        strategy=(
            "Diamond now at R36, trail+♥ at R32. ⑭ at R31 — at diamond-row "
            "level, ready to be threaded."
        ),
        predict=(
            "~130 cells change. Column-different push rule confirmed: no "
            "block got pushed by ♥."
        ),
    ),
    # ACTION4 × 4 → extend through ♥(C24) and onward to ⑭(C42)
    StepNote(
        action="ACTION4",
        intent="Extend at ⑭ height, passing through ♥(C24) first.",
        strategy=(
            "Extension is left→right. ♥(C24) re-threads first (closest), "
            "then extend continues toward ⑭(C42)."
        ),
        predict="~13 cells change. Trail tip extends past ♥.",
        learned="Column-based push rule verified: ♥(C24) and ◆(C42) are different columns, no push occurred.",
    ),
    StepNote(
        action="ACTION4",
        intent="Continue extending toward ⑭.",
        strategy="Tail approaches ⑭ at C42-45.",
        predict="~13 cells change.",
    ),
    StepNote(
        action="ACTION4",
        intent="Extend — should reach ⑭ now.",
        strategy="Thread ⑭ block.",
        predict="~25 cells change. ⑭ now threaded.",
    ),
    StepNote(
        action="ACTION4",
        intent="Final extend to ensure ⑭ fully threaded.",
        strategy="Should hit wall. Trail now threads ♥ then ⑭ (correct order).",
        predict="~13 cells change.",
    ),
    # ACTION3 × 2 → partial retract, pull ♥+⑭ inward
    StepNote(
        action="ACTION3",
        intent="Partial retract — pull ♥+⑭ toward diamond.",
        strategy=(
            "Both blocks are now on trail. Keep partial retract so both "
            "stay attached when we move up to ◆ height."
        ),
        predict="~13 cells change. Blocks move left with trail.",
        learned="⑭ threaded. Order so far: ♥→⑭.",
    ),
    StepNote(
        action="ACTION3",
        intent="Continue partial retract.",
        strategy="Position ♥+⑭ comfortably left so extension at ◆ height works.",
        predict="~13 cells change.",
    ),
    # ACTION1 → UP to ◆ height (R26)
    StepNote(
        action="ACTION1",
        intent="UP to ◆ height (R25-28).",
        strategy=(
            "Diamond+trail+♥+⑭ move up 6 rows. ◆ waits at C42. "
            "After this, extension will re-thread ♥→⑭→◆ in correct order."
        ),
        predict=(
            "Very large diff (~180 cells): diamond+trail+♥+⑭ all shift up. "
            "◆ at R25 stays put."
        ),
        learned="Partial retract preserved both blocks on trail.",
    ),
    # ACTION4 × 5 → extend through ♥→⑭→◆, final threading triggers level clear
    StepNote(
        action="ACTION4",
        intent="Extend at ◆ height, passing through ♥ first.",
        strategy=(
            "Reference order is ♦→♥→⑭→◆. Extension left→right will thread "
            "♥ first, then ⑭, then ◆ — matching reference exactly."
        ),
        predict="~13 cells change. Trail tip advances.",
    ),
    StepNote(
        action="ACTION4",
        intent="Continue extension toward ⑭ and ◆.",
        strategy="Thread each block in order.",
        predict="~13 cells change.",
    ),
    StepNote(
        action="ACTION4",
        intent="Extension threading ⑭ and heading to ◆.",
        strategy="Almost at ◆.",
        predict="~25 cells change. ⑭ re-threaded.",
    ),
    StepNote(
        action="ACTION4",
        intent="Extension reaches ◆ — threading completes reference order.",
        strategy=(
            "♥→⑭→◆ now threaded in correct reference order. Final extension "
            "should trigger level clear."
        ),
        predict=(
            "HUGE diff expected (level transition). ♦→♥→⑭→◆ order matches "
            "reference → L0 clear."
        ),
    ),
    StepNote(
        action="ACTION4",
        intent="Final confirming extension — triggers LEVEL UP.",
        strategy="Complete threading; game enters L1.",
        predict="Level transition: ~1000+ cells change as L0 completes.",
        learned="Threading order ♦→♥→⑭→◆ matches reference → level clears.",
    ),
]


# ---------------------------------------------------------------------------
# Build SFT JSONL
# ---------------------------------------------------------------------------

def _object_summary_line(grid: list[list[int]], bg: set[int] = {3, 4, 5}) -> str:
    """Compact object summary: 'v<val>:n<count>@r<rmin>-<rmax>c<cmin>-<cmax>'."""
    objs: dict[int, list[tuple[int, int]]] = {}
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            if v in bg:
                continue
            objs.setdefault(v, []).append((r, c))
    parts = []
    for v, cells in sorted(objs.items(), key=lambda kv: -len(kv[1]))[:8]:
        rs = [r for r, _ in cells]
        cs = [c for _, c in cells]
        parts.append(
            f"v{v}:n{len(cells)}@r{min(rs)}-{max(rs)}c{min(cs)}-{max(cs)}"
        )
    return "; ".join(parts)


def _build_user_message(
    step_index: int,
    grid: list[list[int]],
    prev_grid: list[list[int]] | None,
    state_name: str,
    levels_completed: int,
    available_actions: list[str],
    recent_actions: list[str],
) -> str:
    diff_cells = diff_cell_count(prev_grid, grid) if prev_grid else 0
    diff_str = "INITIAL" if prev_grid is None else f"{diff_cells} cells changed"
    obj_line = _object_summary_line(grid)
    recent_str = ", ".join(recent_actions[-5:]) if recent_actions else "(none)"
    return (
        f"Game: sk48 | State: {state_name} | Level: {levels_completed} | "
        f"Step: {step_index} | Grid: {len(grid)}x{len(grid[0]) if grid else 0}\n"
        f"Available actions: {', '.join(available_actions)}\n"
        f"Top objects: {obj_line}\n"
        f"Diff since last step: {diff_str}\n"
        f"Recent actions: {recent_str}"
    )


def _build_assistant_message(note: StepNote) -> str:
    """Compose 6-stage chain from the curated StepNote."""
    parts = []
    # OBSERVE is in the user msg; we focus on interpretation+plan here.
    if note.learned:
        parts.append(f"[RESULT] {note.learned}")
    parts.append(f"[INTERPRET] {note.intent}")
    parts.append(f"[HYPOTHESIZE] {note.strategy}")
    parts.append(f"[PREDICT] {note.predict}")
    parts.append("")
    parts.append(f"ACTION: {note.action}")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=Path("artifacts/sft_gold/sk48_gold.jsonl"),
    )
    args = parser.parse_args()

    arc = Arcade(operation_mode=OperationMode.OFFLINE)
    envs = arc.get_environments()
    game_id = next((e.game_id for e in envs if e.game_id.startswith(SK48_GAME_ID_PREFIX)), None)
    if not game_id:
        raise SystemExit(f"sk48 game not found. Available: {[e.game_id for e in envs]}")

    env = arc.make(game_id)

    # RESET first
    reset = GameAction.RESET
    reset.reasoning = "gold-sample"
    raw = env.step(reset, data=reset.action_data.model_dump(), reasoning={})
    if raw is None:
        raise SystemExit("Reset failed.")
    grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else []
    levels = raw.levels_completed
    prev_grid = None

    action_history: list[str] = ["RESET"]
    examples: list[dict] = []

    from arcengine import GameState

    for i, note in enumerate(STEPS):
        available = (
            [GameAction.from_id(a).name for a in raw.available_actions]
            if raw.available_actions
            else ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6", "ACTION7"]
        )
        user_msg = _build_user_message(
            step_index=i,
            grid=grid,
            prev_grid=prev_grid,
            state_name=raw.state.name,
            levels_completed=levels,
            available_actions=available,
            recent_actions=action_history,
        )
        assistant_msg = _build_assistant_message(note)

        examples.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": assistant_msg},
                ],
                "metadata": {
                    "game_id": game_id,
                    "episode_id": "sk48_gold_L0",
                    "step": i,
                    "phase": "gold_solution",
                    "levels_completed": levels,
                    "source": "sk48_reasoning_chain.md (5th attempt)",
                },
            }
        )

        # Execute the action
        ga = GameAction.from_name(note.action)
        ga.reasoning = note.intent[:100]
        prev_grid = [row[:] for row in grid]
        raw = env.step(ga, data=ga.action_data.model_dump(), reasoning={})
        if raw is None:
            raise SystemExit(f"Action {note.action} failed at step {i}.")
        grid = [arr.tolist() for arr in raw.frame][-1] if raw.frame else grid
        levels = raw.levels_completed
        action_history.append(note.action)

    # Verify the final state
    print(f"Final state: {raw.state.name}, levels_completed: {levels}")
    if levels < 1:
        print("WARNING: Expected levels_completed >= 1; gold sequence did not clear L0!")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Wrote {len(examples)} gold examples to {args.output}")


if __name__ == "__main__":
    main()
