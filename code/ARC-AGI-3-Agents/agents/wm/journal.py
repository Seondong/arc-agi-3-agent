"""Discovery journal — the durable narrative of how a world model was learned.

Why this exists
---------------
The first visualizations rebuilt their story from the author's conversational
context: the frames were regenerated from the engine, but the *narrative*
("what this probe taught us", "why the model changed") was hand-written into
each generator afterwards. That story dies with the context window.

So: record at the moment it happens. Solving scripts call `probe()`, `refute()`,
`author()`, `plan()`, `execute()` as they run; the journal appends one JSON line
per event to `artifacts/wm_journal/<game>_L<level>.jsonl`. Visualizations then
read the journal instead of embedding prose. The record is a byproduct of doing
the work, not a separate writing step.

Every entry carries `provenance`:
  "live"  — written during the run that produced it (trustworthy)
  "retro" — reconstructed after the fact from context/memory (flag it, don't hide it)

Append-only: entries are never rewritten, so a journal is a real audit trail of
what was believed when.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

DEFAULT_DIR = "artifacts/wm_journal"


class Journal:
    """Append-only discovery log for one game/level."""

    def __init__(self, game: str, level: int, *, directory: str = DEFAULT_DIR,
                 provenance: str = "live", reset: bool = False):
        self.game, self.level, self.provenance = game, level, provenance
        self.path = Path(directory) / f"{game}_L{level}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if reset and self.path.exists():
            self.path.unlink()
        self._seq = self._count()

    def _count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open(encoding="utf-8") as fh:
            return sum(1 for _ in fh)

    def _write(self, kind: str, **fields: Any) -> dict:
        self._seq += 1
        entry = {"seq": self._seq, "game": self.game, "level": self.level,
                 "kind": kind, "provenance": self.provenance, **fields}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    # -- event types ---------------------------------------------------------

    def observe(self, *, note: str, entities: Optional[dict] = None,
                frame: Optional[list] = None) -> dict:
        """A look at the world without acting on it (e.g. the level's first frame)."""
        return self._write("observe", note=note, entities=entities or {}, frame=frame)

    def probe(self, *, actions: list[str], hypothesis: str, observed: str,
              died: bool = False, env_steps: int = 0,
              entities: Optional[dict] = None, frame: Optional[list] = None) -> dict:
        """A real interaction run to test something. `hypothesis` is what we
        wanted to find out; `observed` is what actually came back — write both
        NOW, while the reason for running it is still known."""
        return self._write("probe", actions=actions, hypothesis=hypothesis,
                           observed=observed, died=died, env_steps=env_steps,
                           entities=entities or {}, frame=frame)

    def refute(self, *, version: str, bug: str, step_index: int, action: str,
               cells_off: int, predicted_frame: Optional[list] = None,
               actual_frame: Optional[list] = None) -> dict:
        """A backtest counterexample: the pointed bug that kills a model version."""
        return self._write("refute", version=version, bug=bug, step_index=step_index,
                           action=action, cells_off=cells_off,
                           predicted_frame=predicted_frame, actual_frame=actual_frame)

    def author(self, *, version: str, rules: list[str], code: str,
               changed: str, because: str, backtest: Optional[dict] = None) -> dict:
        """A (re)authored model. `changed` = what rule moved; `because` = which
        observation forced it. This is the line that makes the story reproducible."""
        return self._write("author", version=version, rules=rules, code=code,
                           changed=changed, because=because, backtest=backtest or {})

    def plan(self, *, version: str, actions: list[str], stats: dict,
             search_log: Optional[list] = None) -> dict:
        """An in-model search. `stats` should carry sims/nodes/deaths/revisits."""
        return self._write("plan", version=version, actions=actions, stats=stats,
                           search_log=search_log)

    def execute(self, *, actions: list[str], result: str, cleared: bool,
                died_at: Optional[int] = None, env_steps: int = 0) -> dict:
        """Running a plan for real."""
        return self._write("execute", actions=actions, result=result,
                           cleared=cleared, died_at=died_at, env_steps=env_steps)

    def note(self, *, text: str) -> dict:
        """Free-form remark worth keeping (a limitation, a suspicion, a TODO)."""
        return self._write("note", text=text)

    # -- reading -------------------------------------------------------------

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


def load(game: str, level: int, *, directory: str = DEFAULT_DIR) -> list[dict]:
    """Read a journal without opening it for writing."""
    p = Path(directory) / f"{game}_L{level}.jsonl"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def summary(entries: list[dict]) -> dict:
    """Cost ledger straight from the journal — no hand-counting."""
    probe_steps = sum(e.get("env_steps", 0) for e in entries if e["kind"] == "probe")
    exec_steps = sum(e.get("env_steps", 0) for e in entries if e["kind"] == "execute")
    deaths = sum(1 for e in entries if e["kind"] == "probe" and e.get("died"))
    deaths += sum(1 for e in entries if e["kind"] == "execute" and e.get("died_at"))
    plans = [e for e in entries if e["kind"] == "plan"]
    return {
        "probe_env_steps": probe_steps,
        "execute_env_steps": exec_steps,
        "real_deaths": deaths,
        "refutations": sum(1 for e in entries if e["kind"] == "refute"),
        "model_versions": [e["version"] for e in entries if e["kind"] == "author"],
        "planning_actions": 0,
        "in_model_sims": sum(p.get("stats", {}).get("sims", 0) for p in plans),
        "in_model_deaths": sum(p.get("stats", {}).get("deaths", 0) for p in plans),
        "retro_entries": sum(1 for e in entries if e.get("provenance") == "retro"),
    }
