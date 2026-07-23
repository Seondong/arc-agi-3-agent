import math
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from arcengine import FrameData, GameAction, GameState
from ..agent import Agent

GRID_SIZE = 64
NUM_COLORS = 16
ACTION_NAMES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6"]
STATE_VOCAB = ["NOT_FINISHED", "GAME_OVER", "WIN"]
HISTORY_VOCAB = ["<PAD>", "RESET", *ACTION_NAMES]
ACTION_MAP = [
    GameAction.ACTION1,
    GameAction.ACTION2,
    GameAction.ACTION3,
    GameAction.ACTION4,
    GameAction.ACTION5,
]
ACTION_TO_ID = {name: idx for idx, name in enumerate(ACTION_NAMES)}
STATE_TO_ID = {name: idx for idx, name in enumerate(STATE_VOCAB)}
HISTORY_TO_ID = {name: idx for idx, name in enumerate(HISTORY_VOCAB)}


def grid_to_onehot(grid: list[list[int]], device: torch.device) -> torch.Tensor:
    padded = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.int64)
    if grid:
        arr = np.array(grid, dtype=np.int64)
        h, w = arr.shape
        padded[:h, :w] = arr[:GRID_SIZE, :GRID_SIZE]
    onehot = np.zeros((NUM_COLORS, GRID_SIZE, GRID_SIZE), dtype=np.float32)
    for color in range(NUM_COLORS):
        onehot[color] = (padded == color).astype(np.float32)
    return torch.tensor(onehot, device=device).unsqueeze(0)


def available_action_names(latest_frame: FrameData) -> set[str]:
    names = set()
    for item in latest_frame.available_actions or []:
        if isinstance(item, str):
            names.add(item)
        else:
            try:
                names.add(GameAction.from_id(int(item)).name)
            except Exception:
                pass
    return names


def extract_objects(grid: list[list[int]], bg_values: set[int] | None = None, limit: int = 8) -> list[dict[str, int]]:
    if bg_values is None:
        bg_values = {3, 4, 5}
    objects: dict[int, list[tuple[int, int]]] = {}
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            if value not in bg_values:
                objects.setdefault(int(value), []).append((r, c))
    compact = []
    ranked = sorted(objects.items(), key=lambda item: (-len(item[1]), item[0]))
    for value, cells in ranked[:limit]:
        rs = [r for r, _ in cells]
        cs = [c for _, c in cells]
        compact.append({
            "value": int(value),
            "count": len(cells),
            "r_min": min(rs),
            "r_max": max(rs),
            "c_min": min(cs),
            "c_max": max(cs),
        })
    return compact


def encode_policy_features(
    grid: list[list[int]],
    latest_frame: FrameData,
    step_count: int,
    diff_cells: int,
    history: list[str],
) -> torch.Tensor:
    vec: list[float] = []
    available = available_action_names(latest_frame)
    vec.extend([1.0 if name in available else 0.0 for name in ACTION_NAMES])
    vec.extend([
        min(step_count / 200.0, 1.0),
        min(float(latest_frame.levels_completed) / 10.0, 1.0),
        min(diff_cells / 512.0, 1.0),
        min(float(latest_frame.levels_completed) / 10.0, 1.0),
        min(float(latest_frame.levels_completed) / 10.0, 1.0),
        min(math.log1p(max(diff_cells, 0)) / 5.0, 1.0),
    ])

    state_one_hot = [0.0] * len(STATE_VOCAB)
    state_idx = STATE_TO_ID.get(latest_frame.state.name, 0)
    state_one_hot[state_idx] = 1.0
    vec.extend(state_one_hot)

    local_history = history[-4:]
    local_history = ["<PAD>"] * (4 - len(local_history)) + local_history
    for item in local_history:
        one_hot = [0.0] * len(HISTORY_VOCAB)
        one_hot[HISTORY_TO_ID.get(item, 0)] = 1.0
        vec.extend(one_hot)

    objects = extract_objects(grid)
    for obj in objects:
        value_one_hot = [0.0] * NUM_COLORS
        value = int(obj.get("value", 0))
        if 0 <= value < NUM_COLORS:
            value_one_hot[value] = 1.0
        vec.extend(value_one_hot)
        vec.extend([
            min(math.log1p(float(obj.get("count", 0))) / 5.0, 1.0),
            float(obj.get("r_min", 0)) / 63.0,
            float(obj.get("r_max", 0)) / 63.0,
            float(obj.get("c_min", 0)) / 63.0,
            float(obj.get("c_max", 0)) / 63.0,
        ])
    missing = 8 - len(objects)
    if missing > 0:
        vec.extend([0.0] * missing * (NUM_COLORS + 5))
    return torch.tensor(vec, dtype=torch.float32)


def grid_diff_cells(old: Optional[list[list[int]]], new: list[list[int]]) -> int:
    if old is None:
        return 0
    rows = min(len(old), len(new))
    cols = min(len(old[0]) if old else 0, len(new[0]) if new else 0)
    count = 0
    for r in range(rows):
        for c in range(cols):
            if old[r][c] != new[r][c]:
                count += 1
    return count


def build_qwen_prompt(
    game_id: str,
    step_count: int,
    latest_frame: FrameData,
    history: list[str],
    diff_cells: int,
    grid: list[list[int]],
) -> str:
    available = sorted(available_action_names(latest_frame))
    objects = extract_objects(grid, limit=8)
    object_text = []
    for obj in objects:
        object_text.append(
            f"v{obj['value']}:n{obj['count']}@r{obj['r_min']}-{obj['r_max']}c{obj['c_min']}-{obj['c_max']}"
        )
    recent = ', '.join(history[-4:]) if history else 'none'
    return (
        f"Game: {game_id}\n"
        f"Step: {step_count}\n"
        f"Level: {int(latest_frame.levels_completed)}\n"
        f"Available actions: {', '.join(available) or 'none'}\n"
        f"Recent actions: {recent}\n"
        f"Diff cells after previous step: {diff_cells}\n"
        f"Objects: {'; '.join(object_text) if object_text else 'none'}\n\n"
        "Choose the next action. Reply with either ACTION1-5 or ACTION6 x=<int> y=<int>."
    )


def parse_qwen_action(text: str) -> tuple[Optional[str], Optional[tuple[int, int]]]:
    action_match = re.search(r"\bACTION([1-6])\b", text.upper())
    if not action_match:
        return None, None
    action_name = f"ACTION{action_match.group(1)}"
    if action_name != 'ACTION6':
        return action_name, None
    x_match = re.search(r"X\s*=\s*(\d+)", text.upper())
    y_match = re.search(r"Y\s*=\s*(\d+)", text.upper())
    if x_match and y_match:
        return action_name, (int(x_match.group(1)), int(y_match.group(1)))
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if len(nums) >= 3:
        return action_name, (nums[1], nums[2])
    return action_name, None


class QwenActionPrior:
    def __init__(self, device: torch.device):
        self.device = device
        self.model = None
        self.tokenizer = None
        self._available = False
        self._load()

    def _find_dir(self, candidates: list[str]) -> Optional[Path]:
        for item in candidates:
            path = Path(item)
            if path.exists():
                return path
        return None

    def _load(self) -> None:
        base_dir = self._find_dir([
            '/kaggle/input/qwen3-5-0-8b',
            '/kaggle/input/qwen35-08b',
            '/kaggle/input/qwen2-5-0-5b-instruct',
            '/kaggle/input/qwen25-05b-instruct',
            '/kaggle/input/qwen-base-model',
        ])
        adapter_dir = self._find_dir([
            '/kaggle/input/qwen35-sft-adapter',
            '/kaggle/input/arc-agi-3-qwen-adapter',
            '/kaggle/input/qwen-sft-adapter',
            '/kaggle/working/qwen_sft_adapter',
        ])
        if base_dir is None:
            print('No Qwen base model found; skipping Qwen prior')
            return
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except Exception as exc:
            print(f'Transformers unavailable; skipping Qwen prior: {exc}')
            return
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                adapter_dir if adapter_dir and (adapter_dir / 'tokenizer_config.json').exists() else base_dir,
                trust_remote_code=True,
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(
                base_dir,
                trust_remote_code=True,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            )
            if adapter_dir is not None:
                try:
                    from peft import PeftModel
                    model = PeftModel.from_pretrained(model, adapter_dir)
                    print(f'Loaded Qwen adapter from {adapter_dir}')
                except Exception as exc:
                    print(f'Failed to load Qwen adapter; using base model only: {exc}')
            self.model = model.to(self.device)
            self.model.eval()
            self._available = True
        except Exception as exc:
            print(f'Failed to load Qwen prior: {exc}')
            self.model = None
            self.tokenizer = None
            self._available = False

    def score(
        self,
        game_id: str,
        step_count: int,
        latest_frame: FrameData,
        history: list[str],
        diff_cells: int,
        grid: list[list[int]],
    ) -> tuple[np.ndarray, Optional[tuple[int, int]], str]:
        scores = np.zeros(len(ACTION_NAMES), dtype=np.float32)
        if not self._available or self.model is None or self.tokenizer is None:
            return scores, None, ''
        prompt = build_qwen_prompt(game_id, step_count, latest_frame, history, diff_cells, grid)
        messages = [
            {
                'role': 'system',
                'content': 'You are a compact ARC-AGI-3 action prior. Reply with a single short action line only.',
            },
            {'role': 'user', 'content': prompt},
        ]
        if hasattr(self.tokenizer, 'apply_chat_template'):
            text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            text = '\n'.join(f"{m['role'].upper()}: {m['content']}" for m in messages) + '\nASSISTANT: '
        inputs = self.tokenizer(text, return_tensors='pt', truncation=True, max_length=1024)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=16,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        raw = self.tokenizer.decode(output[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True).strip()
        action_name, coord = parse_qwen_action(raw)
        if action_name is not None:
            scores[ACTION_TO_ID[action_name]] = 1.0
        return scores, coord, raw


class CNNBackbone(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(NUM_COLORS, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.conv4 = nn.Conv2d(128, 256, kernel_size=3, padding=1)

    def forward(self, x: torch.Tensor):
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        mid = F.relu(self.conv3(x))
        final = F.relu(self.conv4(mid))
        return final, mid


class ActionHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.pool = nn.AdaptiveMaxPool2d(1)
        self.fc1 = nn.Linear(256, 256)
        self.fc2 = nn.Linear(256, 5)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        x = self.pool(features).flatten(1)
        x = F.relu(self.fc1(x))
        return self.fc2(x)


class CoordinateHead(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(128, 64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(64, 32, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(32, 1, kernel_size=1)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.conv1(features))
        x = F.relu(self.conv2(x))
        return self.conv3(x).view(features.size(0), GRID_SIZE * GRID_SIZE)


class CNNPolicy(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = CNNBackbone()
        self.action_head = ActionHead()
        self.coord_head = CoordinateHead()

    def forward(self, x: torch.Tensor):
        final, mid = self.backbone(x)
        return self.action_head(final), self.coord_head(mid)


class SmallPolicyNet(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, len(ACTION_NAMES)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


@dataclass
class Experience:
    frame: np.ndarray
    action_idx: int
    reward: float
    coord_idx: Optional[int] = None


class MyAgent(Agent):
    MAX_ACTIONS = float("inf")
    TRAIN_EVERY = 4
    BATCH_SIZE = 64
    MAX_BUFFER = 1500
    STUCK_THRESHOLD = 8

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        seed = int(time.time() * 1000) + abs(hash(self.game_id)) % 100000
        random.seed(seed)
        np.random.seed(seed % (2 ** 32))
        torch.manual_seed(seed)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = CNNPolicy().to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=1e-3)
        self.buffer: list[Experience] = []
        self.prev_grid: Optional[list[list[int]]] = None
        self.prev_action_idx: Optional[int] = None
        self.prev_coord_idx: Optional[int] = None
        self.prev_level = 0
        self.step_count = 0
        self.steps_since_change = 0
        self.action_history: list[str] = []
        self.prior_model, self.prior_input_dim = self._try_load_prior()
        self.qwen_prior = QwenActionPrior(self.device)
        self.cached_qwen_prior = np.zeros(len(ACTION_NAMES), dtype=np.float32)
        self.cached_qwen_coord: Optional[tuple[int, int]] = None
        self.last_qwen_text = ""
        self.last_qwen_query_step = -999
        self.force_qwen_query = True

    def _try_load_prior(self):
        candidates = [
            "/kaggle/input/arc-agi-3-small-policy/small_policy_prior.pt",
            "/kaggle/input/arc-agi-3-small-policy-prior/small_policy_prior.pt",
            "/kaggle/input/small-policy-prior/small_policy_prior.pt",
            "/kaggle/working/small_policy_prior.pt",
        ]
        for path_str in candidates:
            path = Path(path_str)
            if not path.exists():
                continue
            payload = torch.load(path, map_location=self.device)
            model = SmallPolicyNet(int(payload["input_dim"]))
            model.load_state_dict(payload["model_state"])
            model.to(self.device)
            model.eval()
            print(f"Loaded distilled prior from {path}")
            return model, int(payload["input_dim"])
        print("No distilled prior found; using CNN only")
        return None, None

    def _record_experience(self, current_grid: list[list[int]]):
        if self.prev_grid is None or self.prev_action_idx is None:
            return
        changed = self.prev_grid != current_grid
        reward = 1.0 if changed else 0.0
        if changed:
            self.steps_since_change = 0
        else:
            self.steps_since_change += 1
        coord_idx = self.prev_coord_idx if self.prev_action_idx == 5 else None
        self.buffer.append(
            Experience(
                frame=np.array(self.prev_grid, dtype=np.int64),
                action_idx=self.prev_action_idx,
                reward=reward,
                coord_idx=coord_idx,
            )
        )
        if len(self.buffer) > self.MAX_BUFFER:
            self.buffer = self.buffer[-self.MAX_BUFFER:]

    def _train_cnn(self):
        if len(self.buffer) < 8:
            return
        batch = random.sample(self.buffer, min(self.BATCH_SIZE, len(self.buffer)))
        frames = []
        action_indices = []
        rewards = []
        coord_rows = []
        coord_targets = []
        for exp in batch:
            frames.append(grid_to_onehot(exp.frame.tolist(), torch.device("cpu")).squeeze(0).numpy())
            action_indices.append(exp.action_idx)
            rewards.append(exp.reward)
            if exp.coord_idx is not None:
                coord_rows.append(len(frames) - 1)
                coord_targets.append(exp.coord_idx)
        frames_t = torch.tensor(np.array(frames), device=self.device)
        action_indices_t = torch.tensor(action_indices, dtype=torch.long, device=self.device)
        rewards_t = torch.tensor(rewards, dtype=torch.float32, device=self.device)

        action_logits, coord_logits = self.model(frames_t)
        # Only train action head for ACTION1-5 (indices 0-4), skip ACTION6 (index 5)
        simple_mask = action_indices_t < action_logits.size(1)
        if simple_mask.any():
            safe_indices = action_indices_t.clamp(max=action_logits.size(1) - 1)
            selected_action_logits = action_logits.gather(1, safe_indices.unsqueeze(1)).squeeze(1)
            loss = F.binary_cross_entropy_with_logits(
                selected_action_logits[simple_mask], rewards_t[simple_mask]
            )
        else:
            loss = torch.tensor(0.0, device=self.device)

        if coord_rows:
            row_idx = torch.tensor(coord_rows, dtype=torch.long, device=self.device)
            coord_target_idx = torch.tensor(coord_targets, dtype=torch.long, device=self.device)
            coord_selected = coord_logits[row_idx]
            coord_labels = torch.zeros_like(coord_selected)
            coord_labels.scatter_(1, coord_target_idx.unsqueeze(1), 1.0)
            coord_rewards = rewards_t[row_idx].unsqueeze(1)
            loss = loss + 0.25 * F.binary_cross_entropy_with_logits(coord_selected, coord_labels * coord_rewards)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

    def _available_mask(self, latest_frame: FrameData) -> list[float]:
        available = available_action_names(latest_frame)
        return [1.0 if name in available else 0.0 for name in ACTION_NAMES]

    def _prior_scores(self, grid: list[list[int]], latest_frame: FrameData, diff_cells: int) -> np.ndarray:
        if self.prior_model is None:
            return np.zeros(len(ACTION_NAMES), dtype=np.float32)
        features = encode_policy_features(
            grid=grid,
            latest_frame=latest_frame,
            step_count=self.step_count,
            diff_cells=diff_cells,
            history=self.action_history,
        ).to(self.device)
        with torch.no_grad():
            logits = self.prior_model(features.unsqueeze(0))[0]
            probs = torch.softmax(logits, dim=0).cpu().numpy()
        return probs.astype(np.float32)



    def _should_query_qwen(self) -> bool:
        if not getattr(self.qwen_prior, '_available', False):
            return False
        if self.force_qwen_query:
            return True
        if self.steps_since_change >= self.STUCK_THRESHOLD and self.step_count - self.last_qwen_query_step >= 4:
            return True
        return False

    def _qwen_scores(self, current_grid: list[list[int]], latest_frame: FrameData, diff_cells: int) -> np.ndarray:
        if self._should_query_qwen():
            scores, coord, raw = self.qwen_prior.score(
                game_id=self.game_id,
                step_count=self.step_count,
                latest_frame=latest_frame,
                history=self.action_history,
                diff_cells=diff_cells,
                grid=current_grid,
            )
            if float(scores.sum()) > 0:
                self.cached_qwen_prior = scores
            if coord is not None:
                self.cached_qwen_coord = coord
            self.last_qwen_text = raw
            self.last_qwen_query_step = self.step_count
            self.force_qwen_query = False
        return self.cached_qwen_prior.copy()

    def _pick_action6_coord(self, coord_logits: torch.Tensor, grid: list[list[int]]) -> tuple[int, int]:
        heat = torch.sigmoid(coord_logits).view(GRID_SIZE, GRID_SIZE).detach().cpu().numpy()
        if self.cached_qwen_coord is not None:
            qx, qy = self.cached_qwen_coord
            if 0 <= qx < GRID_SIZE and 0 <= qy < GRID_SIZE:
                heat[qy, qx] += 0.35
        for obj in extract_objects(grid, limit=6):
            cy = int((obj["r_min"] + obj["r_max"]) / 2)
            cx = int((obj["c_min"] + obj["c_max"]) / 2)
            if 0 <= cy < GRID_SIZE and 0 <= cx < GRID_SIZE:
                heat[cy, cx] += 0.25
        idx = int(np.argmax(heat))
        y, x = divmod(idx, GRID_SIZE)
        return int(x), int(y)

    def _choose_action(self, current_grid: list[list[int]], latest_frame: FrameData) -> GameAction:
        x = grid_to_onehot(current_grid, self.device)
        self.model.eval()
        with torch.no_grad():
            action_logits, coord_logits = self.model(x)
            cnn_simple = torch.sigmoid(action_logits[0]).cpu().numpy()
            coord_probs = torch.sigmoid(coord_logits[0]).cpu().numpy()
        self.model.train()

        diff_cells = grid_diff_cells(self.prev_grid, current_grid)
        prior = self._prior_scores(current_grid, latest_frame, diff_cells)
        qwen_prior = self._qwen_scores(current_grid, latest_frame, diff_cells)
        mask = np.array(self._available_mask(latest_frame), dtype=np.float32)

        cnn_weight = 0.55 if self.steps_since_change >= self.STUCK_THRESHOLD else 0.75
        prior_weight = 0.45 if self.steps_since_change >= self.STUCK_THRESHOLD else 0.25
        blended = np.zeros(6, dtype=np.float32)
        blended[:5] = cnn_simple * cnn_weight
        topk = coord_probs[np.argpartition(coord_probs, -32)[-32:]] if coord_probs.size >= 32 else coord_probs
        blended[5] = float(topk.mean()) * cnn_weight
        blended += prior * prior_weight
        qwen_weight = 0.35 if self.steps_since_change >= self.STUCK_THRESHOLD else 0.10
        blended += qwen_prior * qwen_weight
        blended *= mask

        if blended.sum() <= 1e-8:
            valid = [i for i, keep in enumerate(mask.tolist()) if keep > 0]
            choice = random.choice(valid) if valid else 0
        else:
            epsilon = 0.20 if self.steps_since_change >= self.STUCK_THRESHOLD else 0.08
            if random.random() < epsilon:
                valid = [i for i, keep in enumerate(mask.tolist()) if keep > 0]
                choice = random.choice(valid) if valid else int(np.argmax(blended))
            else:
                choice = int(np.argmax(blended))

        if choice < 5:
            action = ACTION_MAP[choice]
            action.reasoning = f"hybrid choice={ACTION_NAMES[choice]} stuck={self.steps_since_change} qwen={self.last_qwen_text[:32]}"
            self.prev_action_idx = choice
            self.prev_coord_idx = None
            self.action_history.append(ACTION_NAMES[choice])
            return action

        action = GameAction.ACTION6
        x_coord, y_coord = self._pick_action6_coord(coord_logits[0], current_grid)
        action.set_data({"x": x_coord, "y": y_coord})
        action.reasoning = f"hybrid choice=ACTION6 x={x_coord} y={y_coord} stuck={self.steps_since_change} qwen={self.last_qwen_text[:32]}"
        self.prev_action_idx = 5
        self.prev_coord_idx = y_coord * GRID_SIZE + x_coord
        self.action_history.append("ACTION6")
        return action

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        return latest_frame.state is GameState.WIN

    def choose_action(self, frames: list[FrameData], latest_frame: FrameData) -> GameAction:
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            self.prev_grid = None
            self.prev_action_idx = None
            self.prev_coord_idx = None
            self.steps_since_change = 0
            self.cached_qwen_prior = np.zeros(len(ACTION_NAMES), dtype=np.float32)
            self.cached_qwen_coord = None
            self.force_qwen_query = True
            self.action_history.append("RESET")
            return GameAction.RESET

        current_grid = latest_frame.frame[-1]
        if latest_frame.levels_completed > self.prev_level:
            self.model = CNNPolicy().to(self.device)
            self.optimizer = optim.Adam(self.model.parameters(), lr=1e-3)
            self.buffer = []
            self.steps_since_change = 0
            self.force_qwen_query = True
            self.cached_qwen_coord = None
        self.prev_level = int(latest_frame.levels_completed)

        self._record_experience(current_grid)
        self.step_count += 1
        if self.step_count % self.TRAIN_EVERY == 0:
            self._train_cnn()

        action = self._choose_action(current_grid, latest_frame)
        self.prev_grid = [row[:] for row in current_grid]
        self.action_history = self.action_history[-12:]
        return action

    def cleanup(self, *args: Any, **kwargs: Any) -> None:
        return None
