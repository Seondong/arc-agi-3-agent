"""[Mar 29] Created by SD with GPT-5.4.

Run a naive random agent on sb26 for 50 actions and persist the returned scorecard.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import types
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

REPO_ROOT = Path(__file__).resolve().parent
os.environ.setdefault("RECORDINGS_DIR", "recordings_random50_sb26")

agents_pkg = types.ModuleType("agents")
agents_pkg.__path__ = [os.path.join(os.path.dirname(__file__), "agents")]
sys.modules["agents"] = agents_pkg

from agents.agent import Playback  # type: ignore[attr-defined]
from agents.recorder import Recorder  # type: ignore[attr-defined]

agents_pkg.AVAILABLE_AGENTS = {}
agents_pkg.Recorder = Recorder
agents_pkg.Playback = Playback

from agents.templates.random_agent import Random  # type: ignore[attr-defined]


class Random50(Random):
    MAX_ACTIONS = 50


agents_pkg.AVAILABLE_AGENTS["random50"] = Random50

from agents.swarm import Swarm  # type: ignore[attr-defined]


def root_url() -> str:
    scheme = os.environ.get("SCHEME", "https")
    host = os.environ.get("HOST", "three.arcprize.org")
    port = os.environ.get("PORT", "443")
    if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def fetch_games(base_url: str) -> list[str]:
    session = requests.Session()
    session.headers.update({"X-API-Key": os.getenv("ARC_API_KEY", "")})
    response = session.get(f"{base_url}/api/games", timeout=10)
    response.raise_for_status()
    return [item["game_id"] for item in response.json()]


def main() -> None:
    os.environ["RECORDINGS_DIR"] = os.environ.get("RECORDINGS_DIR", "recordings_random50_sb26")
    Path(os.environ["RECORDINGS_DIR"]).mkdir(parents=True, exist_ok=True)

    base_url = root_url()
    games = [gid for gid in fetch_games(base_url) if gid.startswith("sb26")]
    if not games:
        raise SystemExit("Could not find an sb26 game from the API.")

    game = games[0]
    print(f"Using ARC endpoint: {base_url}")
    print(f"Running Random50 on game: {game}")
    print(f"Recordings dir: {Path(os.environ['RECORDINGS_DIR']).resolve()}")

    swarm = Swarm(
        agent="random50",
        ROOT_URL=base_url,
        games=[game],
        tags=["agent", "random50", "naive-baseline", "sb26"],
    )
    swarm.agent_class = Random50

    result: dict[str, object] = {"card_id": None, "scorecard": None}

    def run_agent() -> None:
        scorecard = swarm.main()
        result["scorecard"] = scorecard.model_dump() if scorecard else None
        result["card_id"] = swarm.card_id

    agent_thread = threading.Thread(target=run_agent, daemon=True)
    agent_thread.start()

    def cleanup(signum: int | None, frame: object | None) -> None:
        print("\nCleaning up random50 sb26 run...")
        if swarm.card_id:
            try:
                scorecard = swarm.close_scorecard(swarm.card_id)
                result["scorecard"] = scorecard.model_dump() if scorecard else None
            finally:
                print(f"Scorecard URL candidate: {base_url}/scorecards/{swarm.card_id}")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    agent_thread.join()

    scorecard_path = REPO_ROOT / "artifacts" / "random50_sb26_scorecard.json"
    scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root_url": base_url,
        "game": game,
        "recordings_dir": os.environ["RECORDINGS_DIR"],
        "scorecard_url_candidate": (
            f"{base_url}/scorecards/{swarm.card_id}" if swarm.card_id else None
        ),
        "scorecard": result["scorecard"],
    }
    scorecard_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved scorecard payload to {scorecard_path.resolve()}")
    if payload["scorecard_url_candidate"]:
        print(f"Scorecard URL candidate: {payload['scorecard_url_candidate']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    main()
