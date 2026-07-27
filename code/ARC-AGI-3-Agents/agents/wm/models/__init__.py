"""World models, one module per game.

A model is a game-specific executable theory; everything around it — the
backtest, the planner, the journal, the site generators — is game-agnostic and
looks the model up here by game id. Adding a game means adding one module and
one line in `MODELS`, not copying a pipeline.

The keys are the short ids the engine uses as a prefix (`tu93`, `ls20`, …); the
full environment id carries a hash suffix, so lookups always go through
`model_for`, which strips it.
"""
from __future__ import annotations

from typing import Callable

from ..core import WorldModel
from .vc33 import vc33_world_model
from .ft09 import ft09_world_model
from .m0r0 import m0r0_world_model
from .sk48 import sk48_world_model
from .tu93 import tu93_world_model

# game id -> factory(version=..., **kwargs) -> WorldModel
MODELS: dict[str, Callable[..., WorldModel]] = {
    "vc33": vc33_world_model,
    "ft09": ft09_world_model,   # recovered from the journal, not hand-written
    "m0r0": m0r0_world_model,
    "sk48": sk48_world_model,
    "tu93": tu93_world_model,
}


def short_id(game: str) -> str:
    """`tu93-2b534c15` and `tu93` both mean the same game."""
    return game.split("-", 1)[0]


def has_model(game: str) -> bool:
    return short_id(game) in MODELS


def model_for(game: str, **kwargs) -> WorldModel:
    """The world model for a game, or a pointed error naming what is missing."""
    key = short_id(game)
    if key not in MODELS:
        raise KeyError(
            f"no world model for game {key!r}. Games with a model: "
            f"{sorted(MODELS)}. Write agents/wm/models/{key}.py and register it "
            f"in agents/wm/models/__init__.py — a new game starts with no theory, "
            f"which is the point."
        )
    return MODELS[key](**kwargs)


def meta_for(game: str) -> dict:
    """Game metadata the site generators need, read off the game's own module.

    Every key is optional — a game whose model was written five minutes ago has
    none of them, and the generators fall back rather than fail.
    """
    import importlib
    key = short_id(game)
    try:
        mod = importlib.import_module(f".{key}", __name__)
    except ModuleNotFoundError:
        return {}
    return {
        "title": getattr(mod, "TITLE", key),
        "blurb": getattr(mod, "BLURB", ""),
        "versions": getattr(mod, "VERSION_BY_LEVEL", {}),
        "mechanics": getattr(mod, "MECHANIC_BY_LEVEL", {}),
        "legacy_variants": getattr(mod, "LEGACY_VARIANTS", []),
        "deep_dives": getattr(mod, "DEEP_DIVES", []),
        "source": f"agents/wm/models/{key}.py",
    }


__all__ = ["MODELS", "model_for", "meta_for", "has_model", "short_id",
           "tu93_world_model", "m0r0_world_model", "sk48_world_model"]
