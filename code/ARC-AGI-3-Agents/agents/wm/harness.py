"""The game-agnostic half of the loop: environment, solutions, paths.

Everything here is identical for every game. What differs per game is exactly
one thing — the world model in `agents/wm/models/<game>.py` — and that is the
whole claim being tested when the method moves to a second game.

Paths are namespaced by game id so nothing collides:

    artifacts/wm_journal/<game>/L<n>.jsonl     the durable narrative
    artifacts/wm_journal/<game>/solutions.json the action sequences
    artifacts/wm_viz/<game>/                   that game's pages
    artifacts/wm_viz/<game>/data/              that game's page data
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import short_id

JOURNAL_ROOT = Path("artifacts/wm_journal")
VIZ_ROOT = Path("artifacts/wm_viz")


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #

def journal_dir(game: str) -> Path:
    return JOURNAL_ROOT / short_id(game)


def solutions_path(game: str) -> Path:
    return journal_dir(game) / "solutions.json"


def viz_dir(game: str) -> Path:
    return VIZ_ROOT / short_id(game)


def data_dir(game: str) -> Path:
    return viz_dir(game) / "data"


# --------------------------------------------------------------------------- #
# solutions
# --------------------------------------------------------------------------- #

def load_solutions(game: str) -> dict[int, list[str]]:
    p = solutions_path(game)
    if not p.exists():
        return {}
    return {int(k): v for k, v in json.loads(p.read_text()).items()}


def save_solution(game: str, level: int, actions: list[str]) -> None:
    sols = load_solutions(game)
    sols[level] = actions
    p = solutions_path(game)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({str(k): v for k, v in sorted(sols.items())}, indent=1))


def prefix_for(game: str, level: int) -> list[str]:
    """The actions that replay from RESET to the start of `level`."""
    sols = load_solutions(game)
    out: list[str] = []
    for i in range(level):
        if i not in sols:
            raise SystemExit(
                f"{short_id(game)}: no saved solution for L{i}, so L{level} cannot be "
                f"reached. Solve the earlier level first.")
        out += sols[i]
    return out


# --------------------------------------------------------------------------- #
# environment
# --------------------------------------------------------------------------- #

def open_arcade():
    """Offline arcade — thousands of frames per second, no key, no rate limit."""
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=".env.example")
    load_dotenv(dotenv_path=".env", override=True)
    from arc_agi import Arcade, OperationMode
    return Arcade(operation_mode=OperationMode.OFFLINE)


def resolve_game(arc, game: str) -> str:
    """`tu93` -> the engine's full id, with a listing when it does not exist."""
    ids = sorted(e.game_id for e in arc.get_environments())
    key = short_id(game)
    for gid in ids:
        if gid.startswith(key):
            return gid
    raise SystemExit(f"no game starting with {key!r}. Available: {', '.join(ids)}")


def frame(raw):
    """The current grid, or None when the engine returned nothing (it does that
    on death)."""
    return [a.tolist() for a in raw.frame][-1] if raw is not None and raw.frame else None


def died(raw) -> bool:
    """levels_completed alone does not detect death — the state has to be read."""
    return raw is None or not raw.frame or raw.state.name == "GAME_OVER"


class Session:
    """One engine run, replayed to a level, counting every real step it costs."""

    def __init__(self, arc, gid: str, game: str):
        self.arc, self.gid, self.game = arc, gid, game
        self.env = None
        self.raw = None
        self.steps = 0
        # Actions taken since reset_to(), i.e. AFTER the level prefix. This is the
        # replay key the journal stores so any recorded frame can be reproduced.
        self.actions: list[str] = []

    @classmethod
    def open(cls, game: str, level: int = 0):
        arc = open_arcade()
        gid = resolve_game(arc, game)
        s = cls(arc, gid, game)
        s.reset_to(level)
        return s

    def reset_to(self, level: int):
        from arcengine import GameAction
        self.env = self.arc.make(self.gid)
        self.raw = self.env.step(GameAction.RESET,
                                 data=GameAction.RESET.action_data.model_dump(),
                                 reasoning={})
        self.steps += 1
        for name in prefix_for(self.game, level):
            self.act(name)
        self.actions = []           # the prefix is implied by the level, not recorded
        return self.raw

    def act(self, name: str, x=None, y=None):
        """`name` may carry coordinates as ACTION6(x,y) for click-style actions."""
        from arcengine import GameAction
        if "(" in name:
            name, coords = name.split("(", 1)
            x, y = (int(v) for v in coords.rstrip(")").split(","))
        a = GameAction.from_name(name)
        data = a.action_data.model_dump()
        if x is not None:
            data.update(x=x, y=y)
        self.raw = self.env.step(a, data=data, reasoning={})
        self.steps += 1
        self.actions.append(name if x is None else f"{name}({x},{y})")
        return self.raw

    @property
    def grid(self):
        return frame(self.raw)

    @property
    def dead(self) -> bool:
        return died(self.raw)


def bounds(grid, walls=(5, 6)):
    """The interesting rectangle of a frame: everything that is not wall/border."""
    rows = [r for r in range(len(grid))
            if any(v not in walls for v in grid[r])]
    cols = [c for c in range(len(grid[0]))
            if any(grid[r][c] not in walls for r in range(len(grid)))]
    if not rows or not cols:
        return 0, len(grid) - 1, 0, len(grid[0]) - 1
    return min(rows), max(rows), min(cols), max(cols)
