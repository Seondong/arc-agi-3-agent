"""BFS solver for tu93 using the offline engine (no API key needed).

Acts as the "brain": explores real game dynamics by replaying action
prefixes from RESET, keyed on player position, until the level is won.
"""
import sys
from collections import deque

from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.example")
load_dotenv(dotenv_path=".env", override=True)

from arc_agi import Arcade, OperationMode
from arcengine import GameAction, GameState

MOVES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4"]
PLAYER_VALS = {9}  # player block (may include a notch value 4)


def player_pos(grid):
    cells = [(r, c) for r, row in enumerate(grid) for c, v in enumerate(row) if v in PLAYER_VALS]
    if not cells:
        return None
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    return (min(rs), min(cs))  # top-left of player block


def make_env(arc, prefix):
    game_id = next(e.game_id for e in arc.get_environments() if e.game_id.startswith("tu93"))
    env = arc.make(game_id)
    last = None
    for name in prefix:
        act = GameAction.from_name(name)
        act.reasoning = "bfs"
        last = env.step(act, data=act.action_data.model_dump(), reasoning={})
    return last


def grid_of(raw):
    return [arr.tolist() for arr in raw.frame][-1] if raw.frame else []


def main():
    arc = Arcade(operation_mode=OperationMode.OFFLINE)

    start_raw = make_env(arc, ["RESET"])
    start_grid = grid_of(start_raw)
    start_key = player_pos(start_grid)
    print(f"start player at {start_key}, state={start_raw.state.name}")

    seen = {start_key}
    q = deque([["RESET"]])
    nodes = 0
    while q:
        path = q.popleft()
        nodes += 1
        for mv in MOVES:
            raw = make_env(arc, path + [mv])
            if raw is None:
                continue
            grid = grid_of(raw)
            if raw.state == GameState.WIN or raw.levels_completed > 0:
                seq = path[1:] + [mv]  # drop RESET
                print(f"\nSOLVED L0 in {len(seq)} actions ({nodes} nodes explored)")
                print(f"state={raw.state.name} levels={raw.levels_completed}")
                print("ACTIONS=" + ",".join(seq))
                return
            key = player_pos(grid)
            if key is None or key in seen:
                continue
            seen.add(key)
            q.append(path + [mv])
        if nodes % 25 == 0:
            print(f"  explored {nodes} nodes, frontier {len(q)}, visited {len(seen)}")
        if nodes > 5000:
            print("gave up at 5000 nodes")
            return


if __name__ == "__main__":
    main()
