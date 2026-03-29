import json
import logging
import os
from typing import Any, Optional

import anthropic
from arcengine import FrameData, GameAction, GameState

from ..agent import Agent

logger = logging.getLogger()


# ---------------------------------------------------------------------------
# Grid compression utilities
# ---------------------------------------------------------------------------

def _rle_row(row: list[int]) -> str:
    """Run-length encode a single row. e.g. [8,8,8,10,10] -> '8x3 10x2'"""
    if not row:
        return ""
    parts: list[str] = []
    current = row[0]
    count = 1
    for val in row[1:]:
        if val == current:
            count += 1
        else:
            parts.append(f"{current}x{count}" if count > 1 else str(current))
            current = val
            count = 1
    parts.append(f"{current}x{count}" if count > 1 else str(current))
    return " ".join(parts)


def compress_grid(grid: list[list[int]]) -> str:
    """Compress a 2D grid using RLE + identical-row merging."""
    if not grid:
        return "(empty)"
    lines: list[str] = []
    i = 0
    while i < len(grid):
        # Find runs of identical rows
        j = i + 1
        while j < len(grid) and grid[j] == grid[i]:
            j += 1
        row_rle = _rle_row(grid[i])
        if j - i > 2:
            lines.append(f"R{i}-R{j-1}: {row_rle}")
        elif j - i == 2:
            lines.append(f"R{i}-R{i+1}: {row_rle}")
        else:
            lines.append(f"R{i}: {row_rle}")
        i = j
    return "\n".join(lines)


def compute_grid_diff(old: list[list[int]], new: list[list[int]]) -> str:
    """Compute diff between two grids. Returns human-readable change summary."""
    changes: list[str] = []
    for r in range(min(len(old), len(new))):
        for c in range(min(len(old[r]), len(new[r]))):
            if old[r][c] != new[r][c]:
                changes.append(f"({r},{c}):{old[r][c]}->{new[r][c]}")
    if not changes:
        return "NO CHANGE"
    summary = f"{len(changes)} cells changed"
    # Show up to 60 changes to keep context manageable
    if len(changes) <= 60:
        return f"{summary}: {' '.join(changes)}"
    return f"{summary} (showing first 60): {' '.join(changes[:60])}"


# ---------------------------------------------------------------------------
# Claude LLM Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an agent exploring a 2D grid-based game (ARC-AGI-3). The grid is up to 64x64, with cell values 0-15 representing different colored elements.

## Your Task
1. EXPLORE: Take actions to discover what each action does. Track effects carefully.
2. MODEL: Build hypotheses about rules, goals, objects, and win conditions.
3. PLAN: Once you understand the game, find the shortest path to WIN.
4. EXECUTE: Act efficiently. Every action counts toward your score.

## Grid Format
- Grids use Run-Length Encoding (RLE): "8x10 10x4" means 10 cells of value 8, then 4 cells of value 10.
- After the first frame, you receive DIFFS showing only what changed.
- "NO CHANGE" means your last action had no visible effect (possibly hit a wall or invalid action).

## Actions Available
- RESET: Restart game. Required when state is NOT_PLAYED or GAME_OVER.
- ACTION1: Up/W
- ACTION2: Down/S
- ACTION3: Left/A
- ACTION4: Right/D
- ACTION5: Confirm/Enter/Space
- ACTION6: Click at (x,y) coordinates on the grid
- ACTION7: Undo last action

Action meanings may vary per game — you must discover what each one does.

## Strategy
- On each turn, briefly reason about what you observe, then call exactly ONE action tool.
- Track which actions cause changes and which don't.
- Look for patterns: moving objects, color changes, score increases.
- If GAME_OVER, RESET and try a different approach.
- Minimize total actions — your score depends on efficiency.
"""


class ClaudeLLM(Agent):
    """An agent that uses Claude API with tool_use to play ARC-AGI-3 games."""

    MAX_ACTIONS: int = 200
    MODEL: str = "claude-sonnet-4-20250514"
    MESSAGE_LIMIT: int = 20

    messages: list[dict[str, Any]]
    token_counter: int
    previous_grid: Optional[list[list[int]]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.messages = []
        self.token_counter = 0
        self.previous_grid = None
        self._latest_tool_use_id: str = ""
        self._client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    @property
    def name(self) -> str:
        sanitized = self.MODEL.replace("/", "-").replace(":", "-")
        return f"{super().name}.{sanitized}"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    # ------------------------------------------------------------------
    # Tool definitions (Anthropic format)
    # ------------------------------------------------------------------

    def build_tools(self) -> list[dict[str, Any]]:
        """Build tool definitions in Anthropic tool_use format."""
        empty_schema: dict[str, Any] = {"type": "object", "properties": {}}
        simple_actions = [
            ("RESET", "Start or restart the game. Required when state is NOT_PLAYED or GAME_OVER."),
            ("ACTION1", "Move Up (W key)"),
            ("ACTION2", "Move Down (S key)"),
            ("ACTION3", "Move Left (A key)"),
            ("ACTION4", "Move Right (D key)"),
            ("ACTION5", "Confirm / Enter / Spacebar"),
            ("ACTION7", "Undo last action"),
        ]
        tools: list[dict[str, Any]] = []
        for action_name, desc in simple_actions:
            tools.append({
                "name": action_name,
                "description": desc,
                "input_schema": empty_schema,
            })
        tools.append({
            "name": "ACTION6",
            "description": "Click/point at (x, y) coordinates on the grid.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate (0-63)"},
                    "y": {"type": "integer", "description": "Y coordinate (0-63)"},
                },
                "required": ["x", "y"],
            },
        })
        return tools

    # ------------------------------------------------------------------
    # Observation building
    # ------------------------------------------------------------------

    def _get_current_grid(self, frame: FrameData) -> list[list[int]]:
        """Extract the current (last) 2D grid from frame data."""
        if frame.frame:
            return frame.frame[-1]
        return []

    def build_observation(self, latest_frame: FrameData) -> str:
        """Build compressed observation string from the latest frame."""
        current_grid = self._get_current_grid(latest_frame)
        parts: list[str] = []

        parts.append(f"State: {latest_frame.state.name}")
        parts.append(f"Levels completed: {latest_frame.levels_completed}")
        parts.append(f"Action #{self.action_counter}")
        available = [GameAction.from_id(a).name for a in latest_frame.available_actions] if latest_frame.available_actions else []
        if available:
            parts.append(f"Available actions: {', '.join(available)}")

        # Grid: diff or full
        if self.previous_grid is not None and current_grid:
            diff = compute_grid_diff(self.previous_grid, current_grid)
            parts.append(f"\nDIFF from last action: {diff}")
            # If too many changes (level transition etc.), also show full grid
            if diff.startswith("NO CHANGE") or len(diff) > 500:
                parts.append(f"\nFull grid:\n{compress_grid(current_grid)}")
        elif current_grid:
            parts.append(f"\nGrid ({len(current_grid)}x{len(current_grid[0]) if current_grid else 0}):\n{compress_grid(current_grid)}")

        if current_grid:
            self.previous_grid = [row[:] for row in current_grid]

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    def push_message(self, role: str, content: Any) -> None:
        """Add a message, maintaining Claude's alternating role constraint."""
        self.messages.append({"role": role, "content": content})

        if len(self.messages) > self.MESSAGE_LIMIT:
            self.messages = self.messages[-self.MESSAGE_LIMIT:]

        # Ensure messages start with a user message
        while self.messages and self.messages[0]["role"] != "user":
            self.messages.pop(0)

        # Ensure first user message doesn't start with tool_result
        while (self.messages and self.messages[0]["role"] == "user"
               and isinstance(self.messages[0]["content"], list)
               and self.messages[0]["content"]
               and self.messages[0]["content"][0].get("type") == "tool_result"):
            self.messages.pop(0)

    # ------------------------------------------------------------------
    # Core action selection
    # ------------------------------------------------------------------

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        """Choose the next action using Claude API."""

        logging.getLogger("anthropic").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        # First turn: RESET without API call
        if len(self.messages) == 0:
            self.push_message("user", "Game started. Sending RESET to begin.")
            self.push_message("assistant", [
                {"type": "text", "text": "Starting the game with RESET."},
                {"type": "tool_use", "id": "init_reset", "name": "RESET", "input": {}},
            ])
            self._latest_tool_use_id = "init_reset"
            return GameAction.RESET

        # Build observation from the frame we just received
        observation = self.build_observation(latest_frame)

        # Send tool_result for the previous action
        self.push_message("user", [
            {
                "type": "tool_result",
                "tool_use_id": self._latest_tool_use_id,
                "content": observation,
            }
        ])

        # Call Claude to pick the next action
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=self.messages,
                tools=self.build_tools(),
                tool_choice={"type": "any"},
            )
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            logger.debug(f"Messages: {json.dumps(self.messages, indent=2, default=str)}")
            # Fallback: return ACTION5 as default
            action = GameAction.ACTION5
            action.reasoning = f"API error fallback: {e}"
            return action

        # Track tokens
        if response.usage:
            self.track_tokens(
                response.usage.input_tokens + response.usage.output_tokens
            )

        # Parse response: find tool_use block
        tool_use_block = None
        reasoning_text = ""
        for block in response.content:
            if block.type == "text":
                reasoning_text = block.text
            elif block.type == "tool_use":
                tool_use_block = block

        if tool_use_block is None:
            logger.warning("Claude did not return a tool_use block, defaulting to ACTION5")
            action = GameAction.ACTION5
            action.reasoning = reasoning_text or "No tool call returned"
            return action

        # Store assistant response for message history
        self.push_message("assistant", response.content)
        self._latest_tool_use_id = tool_use_block.id

        # Map tool call to GameAction
        action_name = tool_use_block.name
        action_input = tool_use_block.input or {}

        logger.info(f"Claude chose: {action_name} {action_input}")
        if reasoning_text:
            logger.debug(f"Reasoning: {reasoning_text[:200]}")

        action = GameAction.from_name(action_name)
        if action_input:
            # Ensure x,y are integers for ACTION6
            cleaned = {}
            for k, v in action_input.items():
                try:
                    cleaned[k] = int(v)
                except (ValueError, TypeError):
                    cleaned[k] = v
            action.set_data(cleaned)

        action.reasoning = {
            "model": self.MODEL,
            "reasoning": reasoning_text[:500] if reasoning_text else "",
            "action": action_name,
            "input": action_input,
        }

        return action

    # ------------------------------------------------------------------
    # Token tracking
    # ------------------------------------------------------------------

    def track_tokens(self, tokens: int, message: str = "") -> None:
        self.token_counter += tokens
        if hasattr(self, "recorder") and not self.is_playback:
            self.recorder.record({
                "tokens": tokens,
                "total_tokens": self.token_counter,
                "assistant": message,
            })
        logger.info(f"Tokens: +{tokens} = {self.token_counter} total")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, *args: Any, **kwargs: Any) -> None:
        if self._cleanup:
            if hasattr(self, "recorder") and not self.is_playback:
                self.recorder.record({
                    "agent_type": "claude",
                    "model": self.MODEL,
                    "total_tokens": self.token_counter,
                    "total_actions": self.action_counter,
                    "tools": self.build_tools(),
                })
        super().cleanup(*args, **kwargs)
