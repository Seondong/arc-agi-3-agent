"""Accumulated game knowledge for ARC-AGI-3 agents.

Embeds exploration protocols, heuristics, and game-specific knowledge
into system prompts for LLM agents.
"""

import os
from pathlib import Path


EXPLORATION_PROTOCOL = """\
You are playing a grid game. Discover rules by observation.

Steps:
1. OBSERVE to see the map
2. TEST each available action to see what it does
3. EXECUTE actions to win

If an action causes many cell changes, it worked. If few changes, it was blocked.
"""

DIFF_HEURISTICS = ""
ENERGY_RULES = ""
TOOL_USAGE = ""


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
