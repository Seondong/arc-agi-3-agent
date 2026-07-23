"""Run hybrid agent directly without importing the full agents package."""
import sys
import os
import signal
import argparse

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

# Import directly, bypassing __init__.py which imports everything
import importlib, types
# Temporarily replace agents package to avoid importing all templates
agents_pkg = types.ModuleType("agents")
agents_pkg.__path__ = [os.path.join(os.path.dirname(__file__), "agents")]
sys.modules["agents"] = agents_pkg

from agents.agent import Agent, Playback
from agents.recorder import Recorder

# Inject AVAILABLE_AGENTS before Swarm imports it
agents_pkg.AVAILABLE_AGENTS = {}
agents_pkg.Recorder = Recorder

from agents.templates.hybrid_agent import MyAgent as HybridAgent
agents_pkg.AVAILABLE_AGENTS["hybrid"] = HybridAgent

from agents.swarm import Swarm

AVAILABLE_AGENTS = {"hybrid": HybridAgent}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-a", "--agent", default="hybrid")
    parser.add_argument("-g", "--game", default=None)
    parser.add_argument("-t", "--tags", default=None)
    args = parser.parse_args()

    SCHEME = os.environ.get("SCHEME", "https")
    HOST = os.environ.get("HOST", "three.arcprize.org")
    PORT = os.environ.get("PORT", "443")
    if (SCHEME == "http" and PORT == "80") or (SCHEME == "https" and PORT == "443"):
        ROOT_URL = f"{SCHEME}://{HOST}"
    else:
        ROOT_URL = f"{SCHEME}://{HOST}:{PORT}"

    import requests
    session = requests.Session()
    session.headers.update({"X-API-Key": os.getenv("ARC_API_KEY", "")})

    response = session.get(f"{ROOT_URL}/api/games", timeout=10)
    print(ROOT_URL + "/api/games")
    full_games = [g["game_id"] for g in response.json()]

    if args.game:
        games = [gid for gid in full_games if gid.startswith(args.game)]
    else:
        games = full_games

    tags = args.tags.split(",") if args.tags else []
    tags.extend(["agent", args.agent])

    swarm = Swarm(
        agent=args.agent,
        ROOT_URL=ROOT_URL,
        games=games,
        tags=tags,
    )
    swarm.agent_class = HybridAgent

    import threading
    def run_agent():
        scorecard = swarm.main()
        if scorecard:
            swarm.cleanup(scorecard)

    agent_thread = threading.Thread(target=run_agent, daemon=True)
    agent_thread.start()

    def cleanup(signum, frame):
        print("\nCleaning up...")
        if swarm.card_id:
            scorecard = swarm.close_scorecard(swarm.card_id)
            print(f"View your scorecard online: https://arcprize.org/scorecards/{swarm.card_id}")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    agent_thread.join()

    if swarm.card_id:
        print(f"View your scorecard online: https://arcprize.org/scorecards/{swarm.card_id}")

if __name__ == "__main__":
    main()
