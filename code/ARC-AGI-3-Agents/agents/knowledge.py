"""Accumulated game knowledge for ARC-AGI-3 agents.

Embeds exploration protocols, heuristics, and game-specific knowledge
into system prompts for LLM agents.
"""

import os
from pathlib import Path


EXPLORATION_PROTOCOL = """\
You are an agent playing an ARC-AGI-3 game. You must discover the rules by observation.

## Exploration Protocol

Phase 1 (Steps 0-5): Systematic exploration
- Call observe() to see the initial 2D map and objects
- Call test_action() for each available action to see its effect
- Identify: player, walls, interactive objects, energy system
- Note which actions cause grid changes and which don't

Phase 2 (Steps 5-15): Pattern identification
- Map the grid structure: rooms, corridors, boundaries
- Identify the win condition by looking at target displays or goal areas
- Understand object interactions (overlap = interact)
- Look for energy chargers if energy is depleting

Phase 3 (Steps 15+): Goal-directed execution
- Form shortest path plan to win condition
- Execute sub-goal by sub-goal, observing after each step
- If stuck, re-observe and revise plan
- If GAME_OVER, the game will reset; try a different strategy
"""

DIFF_HEURISTICS = """\
## Diff Size Interpretation
- NO CHANGE (0 cells): action was blocked (wall, invalid, or no-op)
- 1-4 cells: energy decrease only (wasted action)
- 5-50 cells: player movement or small interaction
- 50-200 cells: movement + object interaction (key rotation, state change)
- 200-1000 cells: major state change (boundary shift, animation)
- 1000+ cells: level transition or full map reconfiguration
"""

ENERGY_RULES = """\
## Energy Management
- Many games have an energy bar (often bottom rows)
- Energy decreases per action (1 or 2 per step depending on level)
- When energy hits 0: auto-pill consumption may RESET position and state
- Energy chargers (value 11 ★ in some games) refill without reset
- Prioritize efficiency: avoid wall collisions, plan shortest paths
- Before committing to a long path, verify you have enough energy
"""

TOOL_USAGE = """\
## Tool Usage Rules
- Call observe() first to understand the current state
- Use test_action() during exploration to safely test without committing
- Call execute() ONLY when you're confident about the action
- Call analyze_region() to zoom into specific areas when the full map is too large
- You MUST call execute() to make progress — don't loop on observe/test forever
- Maximum 5 tool calls per game step; the last MUST be execute()
"""


def build_system_prompt(game_id: str = "") -> str:
    """Build the full system prompt with accumulated knowledge."""
    sections = [
        EXPLORATION_PROTOCOL,
        DIFF_HEURISTICS,
        ENERGY_RULES,
        TOOL_USAGE,
    ]

    game_knowledge = _load_game_knowledge(game_id)
    if game_knowledge:
        sections.append(f"## Game-Specific Knowledge ({game_id})\n{game_knowledge}")

    return "\n\n".join(sections)


def _load_game_knowledge(game_id: str) -> str:
    """Load game-specific knowledge from docs/ if available."""
    if not game_id:
        return ""

    prefix = game_id.split("-")[0]
    docs_dir = Path(__file__).parent.parent / "docs"
    analysis_file = docs_dir / f"{prefix}-analysis.md"

    if analysis_file.exists():
        try:
            content = analysis_file.read_text()
            if len(content) > 2000:
                content = content[:2000] + "\n... (truncated)"
            return content
        except Exception:
            pass
    return ""
