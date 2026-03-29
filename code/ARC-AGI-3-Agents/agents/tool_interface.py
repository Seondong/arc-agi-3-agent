"""LLM tool interface for ARC-AGI-3 agents.

Defines tool schemas and a ToolExecutor that bridges LLM tool calls
to actual game environment interactions.
"""

from typing import Any, Callable, Optional

from arcengine import GameAction

from .grid_lib import (
    compute_diff,
    diff_cell_count,
    find_objects,
    map2d,
    summarize_state,
)


# ---------------------------------------------------------------------------
# Tool schema definitions (provider-agnostic)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "observe",
        "description": (
            "Get current game state: 2D map, objects, energy, diff from last action. "
            "Call this first to understand what you're looking at."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "test_action",
        "description": (
            "Test one action WITHOUT committing it. Returns the diff that WOULD happen. "
            "Use for exploration: test each action to discover what it does. "
            "Does NOT consume energy or advance the game."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "ACTION1", "ACTION2", "ACTION3", "ACTION4",
                        "ACTION5", "ACTION6", "ACTION7",
                    ],
                    "description": "Action to test. For ACTION6, also provide x and y.",
                },
                "x": {
                    "type": "integer",
                    "description": "X coordinate for ACTION6 (0-63)",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate for ACTION6 (0-63)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "execute",
        "description": (
            "Commit an action for real. This advances the game by one step. "
            "Call this when you're confident about your choice."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "RESET", "ACTION1", "ACTION2", "ACTION3",
                        "ACTION4", "ACTION5", "ACTION6", "ACTION7",
                    ],
                    "description": "The action to perform",
                },
                "x": {
                    "type": "integer",
                    "description": "X coordinate for ACTION6 (0-63). Required only for ACTION6.",
                },
                "y": {
                    "type": "integer",
                    "description": "Y coordinate for ACTION6 (0-63). Required only for ACTION6.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "analyze_region",
        "description": (
            "Zoom into a specific grid region. Returns detailed 2D char map "
            "and object list for that area. Useful for inspecting small patterns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "row_start": {"type": "integer", "description": "Start row (0-63)"},
                "row_end": {"type": "integer", "description": "End row (0-63)"},
                "col_start": {"type": "integer", "description": "Start column (0-63)"},
                "col_end": {"type": "integer", "description": "End column (0-63)"},
            },
            "required": ["row_start", "row_end", "col_start", "col_end"],
        },
    },
]


# ---------------------------------------------------------------------------
# Provider format converters
# ---------------------------------------------------------------------------

def to_anthropic_tools(schemas: list[dict] = TOOL_SCHEMAS) -> list[dict]:
    return [
        {
            "name": s["name"],
            "description": s["description"],
            "input_schema": s["parameters"],
        }
        for s in schemas
    ]


def to_openai_tools(schemas: list[dict] = TOOL_SCHEMAS) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s["description"],
                "parameters": s["parameters"],
            },
        }
        for s in schemas
    ]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

class ToolExecutor:
    """Executes tool calls by interacting with the game environment."""

    def __init__(
        self,
        get_grid: Callable[[], list[list[int]]],
        get_prev_grid: Callable[[], Optional[list[list[int]]]],
        get_frame: Callable,
        get_action_counter: Callable[[], int],
        simulate_action: Optional[Callable] = None,
    ):
        self._get_grid = get_grid
        self._get_prev_grid = get_prev_grid
        self._get_frame = get_frame
        self._get_action_counter = get_action_counter
        self._simulate_action = simulate_action

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        if tool_name == "observe":
            return self._observe()
        elif tool_name == "test_action":
            return self._test_action(tool_args)
        elif tool_name == "analyze_region":
            return self._analyze_region(
                tool_args.get("row_start", 0),
                tool_args.get("row_end", 63),
                tool_args.get("col_start", 0),
                tool_args.get("col_end", 63),
            )
        elif tool_name == "execute":
            return "ERROR: execute should be handled by SmartAgent, not ToolExecutor"
        else:
            return f"ERROR: Unknown tool '{tool_name}'"

    def _observe(self) -> str:
        grid = self._get_grid()
        prev_grid = self._get_prev_grid()
        frame = self._get_frame()
        counter = self._get_action_counter()
        return summarize_state(grid, prev_grid, frame, counter)

    def _test_action(self, args: dict) -> str:
        if self._simulate_action is None:
            return "test_action not available (no simulator configured)"
        try:
            action_name = args.get("action", "ACTION1")
            if action_name == "ACTION6" and "x" in args and "y" in args:
                result = self._simulate_action({"action": action_name, "x": args["x"], "y": args["y"]})
            else:
                result = self._simulate_action(action_name)
            return result
        except Exception as e:
            return f"test_action failed: {e}"

    def _analyze_region(self, r0: int, r1: int, c0: int, c1: int) -> str:
        grid = self._get_grid()
        parts = []
        parts.append(f"Region R{r0}-R{r1}, C{c0}-C{c1}:")
        parts.append(map2d(grid, row_range=(r0, r1), col_range=(c0, c1)))

        region_objects: dict[int, int] = {}
        for r in range(max(0, r0), min(len(grid), r1 + 1)):
            for c in range(max(0, c0), min(len(grid[r]), c1 + 1)):
                v = grid[r][c]
                if v not in {3, 4, 5}:
                    region_objects[v] = region_objects.get(v, 0) + 1

        if region_objects:
            from .grid_lib import CHAR_MAP
            obj_strs = [f"{v}({CHAR_MAP.get(v,'?')}):{n}" for v, n in sorted(region_objects.items())]
            parts.append(f"Objects in region: {', '.join(obj_strs)}")

        return "\n".join(parts)
