"""[Mar 29] Created by SD with GPT-5.4.

Run the CNN/StochasticGoose-style agent in isolation and print the ARC scorecard URL.
"""

from __future__ import annotations

import argparse
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

# Keep recordings separate from hybrid/Claude runs unless the caller overrides it.
os.environ.setdefault("RECORDINGS_DIR", "recordings_stochasticgoose")

# Bypass importing the full agents package so we don't interfere with other work.
agents_pkg = types.ModuleType("agents")
agents_pkg.__path__ = [os.path.join(os.path.dirname(__file__), "agents")]
sys.modules["agents"] = agents_pkg

from agents.agent import Playback  # type: ignore[attr-defined]
from agents.recorder import Recorder  # type: ignore[attr-defined]

agents_pkg.AVAILABLE_AGENTS = {}
agents_pkg.Recorder = Recorder
agents_pkg.Playback = Playback

from agents.templates.cnn_agent import CNNAgent  # type: ignore[attr-defined]

agents_pkg.AVAILABLE_AGENTS["cnn"] = CNNAgent
agents_pkg.AVAILABLE_AGENTS["stochasticgoose"] = CNNAgent

from agents.swarm import Swarm  # type: ignore[attr-defined]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the CNN/StochasticGoose-style ARC-AGI-3 agent and open a scorecard."
    )
    parser.add_argument(
        "-a",
        "--agent",
        default="cnn",
        choices=["cnn", "stochasticgoose"],
        help="Alias to use for tags and scorecard metadata.",
    )
    parser.add_argument(
        "-g",
        "--game",
        default=None,
        help="Optional comma-separated game prefix filter, e.g. ls20 or ls20,tn36",
    )
    parser.add_argument(
        "-t",
        "--tags",
        default="stochasticgoose,cnn-baseline",
        help="Optional comma-separated scorecard tags.",
    )
    parser.add_argument(
        "--recordings-dir",
        default=os.environ.get("RECORDINGS_DIR", "recordings_stochasticgoose"),
        help="Directory for local recordings/log artifacts.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of games to run after filtering.",
    )
    return parser.parse_args()


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
    args = parse_args()
    os.environ["RECORDINGS_DIR"] = args.recordings_dir
    Path(args.recordings_dir).mkdir(parents=True, exist_ok=True)

    base_url = root_url()
    print(f"Using ARC endpoint: {base_url}")
    print(f"Recordings dir: {Path(args.recordings_dir).resolve()}")

    games = fetch_games(base_url)
    if args.game:
        prefixes = [item.strip() for item in args.game.split(",") if item.strip()]
        games = [gid for gid in games if any(gid.startswith(prefix) for prefix in prefixes)]
    if args.limit is not None:
        games = games[: args.limit]

    if not games:
        raise SystemExit("No matching games found for the provided filter.")

    print(f"Selected games ({len(games)}): {games}")

    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    tags.extend(["agent", args.agent])

    swarm = Swarm(
        agent="cnn",
        ROOT_URL=base_url,
        games=games,
        tags=tags,
    )
    swarm.agent_class = CNNAgent

    def run_agent() -> None:
        scorecard = swarm.main()
        if scorecard:
            swarm.cleanup(scorecard)

    agent_thread = threading.Thread(target=run_agent, daemon=True)
    agent_thread.start()

    def cleanup(signum: int | None, frame: object | None) -> None:
        print("\nCleaning up stochastic goose run...")
        if swarm.card_id:
            try:
                swarm.close_scorecard(swarm.card_id)
            finally:
                print(f"View your scorecard online: {base_url}/scorecards/{swarm.card_id}")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    agent_thread.join()

    if swarm.card_id:
        print(f"View your scorecard online: {base_url}/scorecards/{swarm.card_id}")


if __name__ == "__main__":
    main()
