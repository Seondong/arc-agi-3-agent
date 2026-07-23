"""
CNN-based agent inspired by StochasticGoose (12.58%, ARC-AGI-3 preview 1st place).

Learns online during gameplay which actions cause frame changes.
Architecture:
- 4-layer CNN backbone (16ch one-hot -> 32 -> 64 -> 128 -> 256)
- Action head: MaxPool -> FC(512) -> 5 logits (ACTION1-5)
- Coordinate head: Conv(128->64->32->1) -> 64x64 logits (ACTION6 coordinates)
- Training: binary cross-entropy, reward=1.0 if frame changed, 0.0 if not
"""

import hashlib
import logging
import random
from collections import deque
from typing import Any, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from arcengine import FrameData, GameAction, GameState

from ..agent import Agent

logger = logging.getLogger(__name__)

GRID_SIZE = 64
NUM_COLORS = 16
MAX_FRAMES_WINDOW = 10
TRAIN_EVERY = 5
BATCH_SIZE = 64
ENTROPY_COEFF = 0.01
LEARNING_RATE = 1e-3

# Simple action indices: ACTION1=0, ACTION2=1, ..., ACTION5=4
SIMPLE_ACTIONS = [
    GameAction.ACTION1,
    GameAction.ACTION2,
    GameAction.ACTION3,
    GameAction.ACTION4,
    GameAction.ACTION5,
]

DEVICE = torch.device("cpu")


def frame_to_onehot(frame_grid: list[list[int]]) -> np.ndarray:
    """Convert a 2D grid (up to 64x64, values 0-15) to one-hot tensor of shape (16, 64, 64)."""
    h = len(frame_grid)
    w = len(frame_grid[0]) if h > 0 else 0
    onehot = np.zeros((NUM_COLORS, GRID_SIZE, GRID_SIZE), dtype=np.float32)
    for r in range(h):
        for c in range(w):
            val = frame_grid[r][c]
            if 0 <= val < NUM_COLORS:
                onehot[val, r, c] = 1.0
    return onehot


def frame_md5(frame_grid: list[list[int]]) -> str:
    """Compute MD5 hash of a frame grid for deduplication."""
    raw = str(frame_grid).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


class CNNBackbone(nn.Module):
    """4-layer CNN backbone: 16ch one-hot -> 32 -> 64 -> 128 -> 256."""

    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(NUM_COLORS, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.conv4 = nn.Conv2d(128, 256, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(32)
        self.bn2 = nn.BatchNorm2d(64)
        self.bn3 = nn.BatchNorm2d(128)
        self.bn4 = nn.BatchNorm2d(256)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Returns (final_features [B,256,64,64], mid_features [B,128,64,64])."""
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        mid = F.relu(self.bn3(self.conv3(x)))
        out = F.relu(self.bn4(self.conv4(mid)))
        return out, mid


class ActionHead(nn.Module):
    """MaxPool -> FC(512) -> 5 logits for ACTION1-5."""

    def __init__(self) -> None:
        super().__init__()
        self.pool = nn.AdaptiveMaxPool2d(1)
        self.fc1 = nn.Linear(256, 512)
        self.fc2 = nn.Linear(512, 5)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(x).view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        return self.fc2(x)  # (B, 5)


class CoordinateHead(nn.Module):
    """Conv(128->64->32->1) -> 64x64 logits for ACTION6 coordinates."""

    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(128, 64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(64, 32, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(32, 1, kernel_size=3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = self.conv3(x)  # (B, 1, 64, 64)
        return x.view(x.size(0), GRID_SIZE * GRID_SIZE)  # (B, 4096)


class CNNModel(nn.Module):
    """Full model combining backbone + action head + coordinate head."""

    def __init__(self) -> None:
        super().__init__()
        self.backbone = CNNBackbone()
        self.action_head = ActionHead()
        self.coord_head = CoordinateHead()

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        final_feat, mid_feat = self.backbone(x)
        action_logits = self.action_head(final_feat)  # (B, 5)
        coord_logits = self.coord_head(mid_feat)  # (B, 4096)
        return action_logits, coord_logits


class Experience:
    """Single experience tuple."""

    def __init__(
        self,
        state: np.ndarray,
        action_type: str,
        action_idx: int,
        reward: float,
        md5: str,
    ) -> None:
        self.state = state  # (16, 64, 64)
        self.action_type = action_type  # "simple" or "coord"
        self.action_idx = action_idx  # 0-4 for simple, 0-4095 for coord
        self.reward = reward  # 1.0 if frame changed, 0.0 if not
        self.md5 = md5  # for deduplication


class CNNAgent(Agent):
    """
    CNN-based agent that learns online which actions cause frame changes.

    Inspired by StochasticGoose (12.58%, ARC-AGI-3 preview 1st place).
    """

    MAX_ACTIONS = 500

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.model: Optional[CNNModel] = None
        self.optimizer: Optional[optim.Adam] = None
        self.experience_buffer: deque[Experience] = deque(maxlen=5000)
        self.seen_hashes: set[str] = set()
        self.step_count: int = 0
        self.prev_frame_grid: Optional[list[list[int]]] = None
        self.prev_action: Optional[GameAction] = None
        self.prev_action_type: Optional[str] = None
        self.prev_action_idx: Optional[int] = None
        self.prev_onehot: Optional[np.ndarray] = None
        self.last_levels_completed: int = 0
        self._init_model()

    def _init_model(self) -> None:
        """Initialize or reset the CNN model and optimizer."""
        self.model = CNNModel().to(DEVICE)
        self.model.train()
        self.optimizer = optim.Adam(self.model.parameters(), lr=LEARNING_RATE)
        self.experience_buffer.clear()
        self.seen_hashes.clear()
        self.step_count = 0
        self.prev_frame_grid = None
        self.prev_action = None
        self.prev_action_type = None
        self.prev_action_idx = None
        self.prev_onehot = None

    def _get_current_grid(self, latest_frame: FrameData) -> Optional[list[list[int]]]:
        """Extract the current grid from frame data."""
        if latest_frame.frame and len(latest_frame.frame) > 0:
            return latest_frame.frame[-1]
        return None

    def _get_available_simple_actions(self, latest_frame: FrameData) -> list[int]:
        """Get indices of available simple actions (ACTION1-5)."""
        available = latest_frame.available_actions or []
        indices = []
        for i, action in enumerate(SIMPLE_ACTIONS):
            if action.value in available:
                indices.append(i)
        return indices

    def _is_action6_available(self, latest_frame: FrameData) -> bool:
        """Check if ACTION6 is available."""
        available = latest_frame.available_actions or []
        return GameAction.ACTION6.value in available

    def _store_experience(self, current_grid: list[list[int]]) -> None:
        """Store the previous step's experience if frame changed or not."""
        if self.prev_onehot is None or self.prev_action_type is None:
            return

        # Compute reward: 1.0 if frame changed, 0.0 if not
        prev_md5 = frame_md5(self.prev_frame_grid) if self.prev_frame_grid else ""
        curr_md5 = frame_md5(current_grid)
        reward = 1.0 if prev_md5 != curr_md5 else 0.0

        # Deduplication: use hash of (state_md5, action_type, action_idx)
        exp_key = f"{prev_md5}_{self.prev_action_type}_{self.prev_action_idx}"
        exp_hash = hashlib.md5(exp_key.encode()).hexdigest()

        if exp_hash not in self.seen_hashes:
            self.seen_hashes.add(exp_hash)
            exp = Experience(
                state=self.prev_onehot,
                action_type=self.prev_action_type,
                action_idx=self.prev_action_idx,  # type: ignore[arg-type]
                reward=reward,
                md5=exp_hash,
            )
            self.experience_buffer.append(exp)

    def _train_step(self) -> None:
        """Train the model on a batch from the experience buffer."""
        if len(self.experience_buffer) < 4:
            return

        batch_size = min(BATCH_SIZE, len(self.experience_buffer))
        batch = random.sample(list(self.experience_buffer), batch_size)

        # Separate simple action experiences and coordinate experiences
        simple_exps = [e for e in batch if e.action_type == "simple"]
        coord_exps = [e for e in batch if e.action_type == "coord"]

        assert self.model is not None
        assert self.optimizer is not None

        total_loss = torch.tensor(0.0, device=DEVICE)

        if simple_exps:
            states = torch.tensor(
                np.stack([e.state for e in simple_exps]), device=DEVICE
            )
            action_logits, _ = self.model(states)
            # Binary cross-entropy with sigmoid for each action
            probs = torch.sigmoid(action_logits)

            targets = torch.zeros_like(action_logits)
            for i, exp in enumerate(simple_exps):
                targets[i, exp.action_idx] = exp.reward

            bce_loss = F.binary_cross_entropy(probs, targets)
            # Entropy regularization: encourage exploration
            entropy = -(probs * torch.log(probs + 1e-8) + (1 - probs) * torch.log(1 - probs + 1e-8))
            entropy_bonus = entropy.mean()
            total_loss = total_loss + bce_loss - ENTROPY_COEFF * entropy_bonus

        if coord_exps:
            states = torch.tensor(
                np.stack([e.state for e in coord_exps]), device=DEVICE
            )
            _, coord_logits = self.model(states)
            probs = torch.sigmoid(coord_logits)

            targets = torch.zeros_like(coord_logits)
            for i, exp in enumerate(coord_exps):
                targets[i, exp.action_idx] = exp.reward

            bce_loss = F.binary_cross_entropy(probs, targets)
            entropy = -(probs * torch.log(probs + 1e-8) + (1 - probs) * torch.log(1 - probs + 1e-8))
            entropy_bonus = entropy.mean()
            total_loss = total_loss + bce_loss - ENTROPY_COEFF * entropy_bonus

        if total_loss.requires_grad:
            self.optimizer.zero_grad()
            total_loss.backward()
            self.optimizer.step()

    def _choose_with_model(self, latest_frame: FrameData) -> GameAction:
        """Use the CNN model to choose an action based on current frame."""
        current_grid = self._get_current_grid(latest_frame)
        if current_grid is None:
            # Fallback to random
            return self._random_action(latest_frame)

        onehot = frame_to_onehot(current_grid)
        state_tensor = torch.tensor(onehot, device=DEVICE).unsqueeze(0)

        available_simple = self._get_available_simple_actions(latest_frame)
        has_action6 = self._is_action6_available(latest_frame)

        assert self.model is not None
        self.model.eval()
        with torch.no_grad():
            action_logits, coord_logits = self.model(state_tensor)
            action_probs = torch.sigmoid(action_logits[0])  # (5,)
            coord_probs = torch.sigmoid(coord_logits[0])  # (4096,)
        self.model.train()

        # Mask unavailable simple actions
        masked_simple_probs = torch.zeros(5, device=DEVICE)
        for idx in available_simple:
            masked_simple_probs[idx] = action_probs[idx]

        # Decide between simple action and ACTION6
        # Use max probability across available actions to pick type
        best_simple_prob = masked_simple_probs.max().item() if available_simple else 0.0
        best_coord_prob = coord_probs.max().item() if has_action6 else 0.0

        # Add exploration noise
        explore_prob = max(0.1, 1.0 - self.step_count / 200.0)

        if random.random() < explore_prob:
            # Random exploration
            return self._random_action(latest_frame)

        if best_simple_prob >= best_coord_prob and available_simple:
            # Sample from simple action probabilities
            probs_np = masked_simple_probs.cpu().numpy()
            total = probs_np.sum()
            if total < 1e-8:
                idx = random.choice(available_simple)
            else:
                probs_np = probs_np / total
                idx = np.random.choice(5, p=probs_np)
                if idx not in available_simple:
                    idx = random.choice(available_simple)

            action = SIMPLE_ACTIONS[idx]
            action.reasoning = f"CNN model chose {action.name} (p={action_probs[idx].item():.3f})"

            self.prev_onehot = onehot
            self.prev_frame_grid = current_grid
            self.prev_action = action
            self.prev_action_type = "simple"
            self.prev_action_idx = idx
            return action

        elif has_action6:
            # Sample coordinate from probability distribution
            probs_np = coord_probs.cpu().numpy()
            total = probs_np.sum()
            if total < 1e-8:
                flat_idx = random.randint(0, GRID_SIZE * GRID_SIZE - 1)
            else:
                probs_np = probs_np / total
                flat_idx = np.random.choice(GRID_SIZE * GRID_SIZE, p=probs_np)

            y = int(flat_idx // GRID_SIZE)
            x = int(flat_idx % GRID_SIZE)

            action = GameAction.ACTION6
            action.set_data({"x": x, "y": y})
            action.reasoning = f"CNN model chose ACTION6 at ({x}, {y})"

            self.prev_onehot = onehot
            self.prev_frame_grid = current_grid
            self.prev_action = action
            self.prev_action_type = "coord"
            self.prev_action_idx = flat_idx
            return action

        else:
            return self._random_action(latest_frame)

    def _random_action(self, latest_frame: FrameData) -> GameAction:
        """Fall back to a random available action."""
        current_grid = self._get_current_grid(latest_frame)
        onehot = frame_to_onehot(current_grid) if current_grid else None

        available_simple = self._get_available_simple_actions(latest_frame)
        has_action6 = self._is_action6_available(latest_frame)

        candidates: list[str] = []
        if available_simple:
            candidates.append("simple")
        if has_action6:
            candidates.append("coord")

        if not candidates:
            # Nothing available, try ACTION1
            action = GameAction.ACTION1
            action.reasoning = "No actions available, trying ACTION1"
            return action

        choice = random.choice(candidates)

        if choice == "simple":
            idx = random.choice(available_simple)
            action = SIMPLE_ACTIONS[idx]
            action.reasoning = f"Random exploration: {action.name}"

            if onehot is not None:
                self.prev_onehot = onehot
                self.prev_frame_grid = current_grid
                self.prev_action = action
                self.prev_action_type = "simple"
                self.prev_action_idx = idx
            return action
        else:
            x = random.randint(0, GRID_SIZE - 1)
            y = random.randint(0, GRID_SIZE - 1)
            flat_idx = y * GRID_SIZE + x
            action = GameAction.ACTION6
            action.set_data({"x": x, "y": y})
            action.reasoning = f"Random exploration: ACTION6 at ({x}, {y})"

            if onehot is not None:
                self.prev_onehot = onehot
                self.prev_frame_grid = current_grid
                self.prev_action = action
                self.prev_action_type = "coord"
                self.prev_action_idx = flat_idx
            return action

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        """Done when we win the game."""
        return latest_frame.state is GameState.WIN

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        """Choose an action using the CNN model or random exploration."""

        # Handle game start / game over -> RESET
        if latest_frame.state in [GameState.NOT_PLAYED, GameState.GAME_OVER]:
            action = GameAction.RESET
            action.reasoning = "Reset to start/restart game"
            self.prev_action = None
            self.prev_action_type = None
            return action

        # Check for level change -> reset model and buffer
        if latest_frame.levels_completed > self.last_levels_completed:
            logger.info(
                f"Level changed ({self.last_levels_completed} -> {latest_frame.levels_completed}), resetting model"
            )
            self.last_levels_completed = latest_frame.levels_completed
            self._init_model()

        # Get current grid
        current_grid = self._get_current_grid(latest_frame)

        # Store experience from previous action
        if current_grid is not None and self.prev_action is not None:
            self._store_experience(current_grid)

        # Train every N steps
        self.step_count += 1
        if self.step_count % TRAIN_EVERY == 0 and len(self.experience_buffer) >= 4:
            self._train_step()

        # Keep only sliding window of frames (memory efficiency)
        if len(frames) > MAX_FRAMES_WINDOW:
            # We cannot modify the frames list directly (it's the agent's self.frames),
            # but we only use latest_frame for decisions anyway.
            pass

        # Choose action with model
        return self._choose_with_model(latest_frame)
