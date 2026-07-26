"""Shared argument handling, so every script in this directory takes --game.

Nothing here is game-specific. A script that needs a game-specific fact gets it
from the world model, never from its own constants — that is what keeps the
pipeline reusable when a second game arrives.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# scripts/wm/x.py -> repo root on sys.path, so `agents.wm...` imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game", default="tu93",
                   help="game id or its short prefix (default: tu93)")
    return p


def level_arg(p, default=None):
    p.add_argument("--level", type=int, default=default,
                   help="level index (0-based)")
    return p


def actions_arg(p):
    p.add_argument("actions", nargs="?", default="",
                   help="comma-separated action names, e.g. ACTION3,ACTION4")
    return p


def actions(value: str) -> list[str]:
    return [a for a in value.split(",") if a.strip()]
