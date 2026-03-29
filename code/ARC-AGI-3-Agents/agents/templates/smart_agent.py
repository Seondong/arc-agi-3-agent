"""SmartAgent — automated ARC-AGI-3 agent with LLM reasoning.

Uses the observe→plan→act loop with tool calling.
Supports Claude API (dev) and local LLM (Kaggle) via LLM_PROVIDER env var.
"""

import json
import logging
from typing import Any, Optional

from arcengine import FrameData, GameAction, GameState

from ..agent import Agent
from ..grid_lib import compute_diff, diff_cell_count, map2d, summarize_state
from ..knowledge import build_system_prompt
from ..llm_provider import LLMResponse, create_provider
from ..tool_interface import TOOL_SCHEMAS, ToolExecutor

logger = logging.getLogger(__name__)

MAX_INNER_LOOPS = 5


class SmartAgent(Agent):
    """An agent that uses LLM reasoning with tool calling to play ARC-AGI-3 games."""

    MAX_ACTIONS: int = 200

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.provider = create_provider()
        self.conversation: list[dict[str, Any]] = []
        self.step_summaries: list[str] = []
        self.previous_grid: Optional[list[list[int]]] = None
        self.current_grid: Optional[list[list[int]]] = None
        self.total_tokens: int = 0
        self._system_prompt = build_system_prompt(self.game_id)

        self.tool_executor = ToolExecutor(
            get_grid=lambda: self.current_grid or [],
            get_prev_grid=lambda: self.previous_grid,
            get_frame=lambda: self.frames[-1] if self.frames else FrameData(levels_completed=0),
            get_action_counter=lambda: self.action_counter,
            simulate_action=self._simulate_action,
        )

    @property
    def name(self) -> str:
        return f"{super().name}.smart"

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        # Handle RESET states
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self._add_step_summary("RESET (game start/restart)")
            return GameAction.RESET

        # Update grid state
        self.current_grid = (
            [row[:] for row in latest_frame.frame[-1]]
            if latest_frame.frame
            else []
        )

        # Build observation for the LLM
        state_summary = summarize_state(
            self.current_grid, self.previous_grid, latest_frame, self.action_counter
        )
        self._append_user_message(f"Game state after last action:\n{state_summary}")

        # Inner tool loop: LLM calls tools until it calls execute()
        for i in range(MAX_INNER_LOOPS):
            response = self._call_llm()
            self.total_tokens += response.input_tokens + response.output_tokens

            if not response.tool_calls:
                logger.warning("LLM returned no tool call, defaulting to ACTION5")
                self.previous_grid = self.current_grid
                action = GameAction.ACTION5
                action.reasoning = response.text[:200] or "no tool call"
                self._add_step_summary(f"ACTION5 (default, no tool call)")
                return action

            tool_call = response.tool_calls[0]

            if tool_call.name == "execute":
                # This is the real action
                action = self._parse_execute(tool_call.arguments)
                action.reasoning = {
                    "text": response.text[:300],
                    "step": self.action_counter,
                    "inner_loops": i + 1,
                }
                self.previous_grid = self.current_grid
                self._add_step_summary(
                    f"{action.name} (reason: {response.text[:80]})"
                )
                return action

            # Read-only tool — execute and feed result back
            result = self.tool_executor.execute_tool(tool_call.name, tool_call.arguments)
            logger.info(f"Tool {tool_call.name}: {len(result)} chars result")

            self._append_assistant_tool_use(tool_call.name, tool_call.arguments, response.text)
            self._append_tool_result(tool_call.name, result)

        # Fallback: max inner loops reached
        logger.warning("Max inner loops reached, defaulting to ACTION5")
        self.previous_grid = self.current_grid
        action = GameAction.ACTION5
        action.reasoning = "max inner loops"
        self._add_step_summary("ACTION5 (max loops)")
        return action

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _call_llm(self) -> LLMResponse:
        messages = self._build_messages()
        return self.provider.chat(messages, TOOL_SCHEMAS)

    def _build_messages(self) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
        ]

        # Add compressed history if we have many steps
        if len(self.step_summaries) > 3:
            recent_history = self.step_summaries[-20:]
            msgs.append({
                "role": "user",
                "content": "Previous steps:\n" + "\n".join(recent_history),
            })
            msgs.append({
                "role": "assistant",
                "content": "Understood. Continuing from the latest state.",
            })

        # Add recent conversation (last 8 messages)
        recent = self.conversation[-8:]

        # Ensure starts with user message
        while recent and recent[0]["role"] != "user":
            recent.pop(0)

        msgs.extend(recent)
        return msgs

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    def _append_user_message(self, content: str) -> None:
        self.conversation.append({"role": "user", "content": content})
        self._trim_conversation()

    def _append_assistant_tool_use(self, tool_name: str, args: dict, text: str = "") -> None:
        # Use plain text format that works with all providers
        tool_str = f"[Called {tool_name}({json.dumps(args)})]"
        full_text = f"{text[:200]}\n{tool_str}" if text else tool_str
        self.conversation.append({"role": "assistant", "content": full_text})
        self._trim_conversation()

    def _append_tool_result(self, tool_name: str, result: str) -> None:
        self.conversation.append({
            "role": "user",
            "content": f"Result of {tool_name}:\n{result[:3000]}",
        })
        self._trim_conversation()

    def _trim_conversation(self) -> None:
        if len(self.conversation) > 20:
            self.conversation = self.conversation[-16:]
            while self.conversation and self.conversation[0]["role"] != "user":
                self.conversation.pop(0)

    def _add_step_summary(self, summary: str) -> None:
        self.step_summaries.append(f"Step {self.action_counter}: {summary}")

    # ------------------------------------------------------------------
    # Action parsing
    # ------------------------------------------------------------------

    def _parse_execute(self, args: dict) -> GameAction:
        action_name = args.get("action", "ACTION5")
        action = GameAction.from_name(action_name)
        if action_name == "ACTION6":
            x = args.get("x", 0)
            y = args.get("y", 0)
            try:
                action.set_data({"x": int(x), "y": int(y)})
            except (ValueError, TypeError):
                action.set_data({"x": 0, "y": 0})
        return action

    # ------------------------------------------------------------------
    # Action simulation (for test_action tool)
    # ------------------------------------------------------------------

    def _simulate_action(self, action_spec: str) -> str:
        """Simulate an action by executing it then undoing.

        action_spec can be "ACTION1" or a JSON string like
        '{"action":"ACTION6","x":10,"y":20}'
        """
        if not self.current_grid:
            return "No current grid to simulate against"

        frame = self.frames[-1] if self.frames else None
        if not frame:
            return "No frame data available"

        avail = frame.available_actions or []

        # Parse action spec (may include x,y for ACTION6)
        if isinstance(action_spec, dict):
            action_name = action_spec.get("action", action_spec)
            x = action_spec.get("x")
            y = action_spec.get("y")
        else:
            action_name = action_spec
            x = y = None

        action_id = GameAction.from_name(action_name).value[0]
        if action_id not in avail:
            return f"{action_name} is not available (available: {avail})"

        # Execute the action
        test_action = GameAction.from_name(action_name)
        if action_name == "ACTION6" and x is not None and y is not None:
            test_action.set_data({"x": int(x), "y": int(y)})
        test_action.reasoning = "simulation"
        test_frame = self.take_action(test_action)

        if test_frame is None:
            return f"{action_name}: no frame returned"

        test_grid = (
            [row[:] for row in test_frame.frame[-1]] if test_frame.frame else []
        )
        diff_str = compute_diff(self.current_grid, test_grid, max_show=20)

        # Try to undo
        if 7 in avail:
            undo = GameAction.ACTION7
            undo.reasoning = "undo simulation"
            self.take_action(undo)

        return f"{action_name}: {diff_str}"

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, *args: Any, **kwargs: Any) -> None:
        if self._cleanup:
            if hasattr(self, "recorder") and not self.is_playback:
                self.recorder.record({
                    "agent_type": "smart",
                    "total_tokens": self.total_tokens,
                    "total_actions": self.action_counter,
                    "step_summaries": self.step_summaries[-20:],
                })
        super().cleanup(*args, **kwargs)
