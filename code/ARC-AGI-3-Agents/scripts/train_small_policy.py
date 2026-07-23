"""[Mar 29] Created by SD with GPT-5.4.

Train a lightweight policy prior from compact ARC-AGI-3 trajectories.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F


ACTION_VOCAB = ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6"]
STATE_VOCAB = ["NOT_FINISHED", "GAME_OVER", "WIN"]
HISTORY_VOCAB = ["<PAD>", "RESET", *ACTION_VOCAB]
ACTION_TO_ID = {name: idx for idx, name in enumerate(ACTION_VOCAB)}
STATE_TO_ID = {name: idx for idx, name in enumerate(STATE_VOCAB)}
HISTORY_TO_ID = {name: idx for idx, name in enumerate(HISTORY_VOCAB)}


def encode_example(row: dict[str, Any]) -> tuple[list[float], int]:
    vec: list[float] = []
    vec.extend(float(x) for x in row.get("available_mask", [0] * 6))

    step = float(row.get("step", 0))
    level = float(row.get("level", 0))
    diff_cells = float(row.get("diff_cells", 0))
    levels_before = float(row.get("levels_before", 0))
    levels_after = float(row.get("levels_after", 0))

    vec.extend(
        [
            min(step / 200.0, 1.0),
            min(level / 10.0, 1.0),
            min(diff_cells / 512.0, 1.0),
            min(levels_before / 10.0, 1.0),
            min(levels_after / 10.0, 1.0),
            float(row.get("quality", 0.0)),
        ]
    )

    state_one_hot = [0.0] * len(STATE_VOCAB)
    state_name = str(row.get("state_after", "NOT_FINISHED"))
    state_one_hot[STATE_TO_ID.get(state_name, 0)] = 1.0
    vec.extend(state_one_hot)

    history = list(row.get("history", []))[-4:]
    history = ["<PAD>"] * (4 - len(history)) + history
    for item in history:
        one_hot = [0.0] * len(HISTORY_VOCAB)
        one_hot[HISTORY_TO_ID.get(item, 0)] = 1.0
        vec.extend(one_hot)

    objects = list(row.get("objects", []))[:8]
    for obj in objects:
        count = float(obj.get("count", 0))
        value = int(obj.get("value", 0))
        r_min = float(obj.get("r_min", 0))
        r_max = float(obj.get("r_max", 0))
        c_min = float(obj.get("c_min", 0))
        c_max = float(obj.get("c_max", 0))

        value_one_hot = [0.0] * 16
        if 0 <= value < 16:
            value_one_hot[value] = 1.0
        vec.extend(value_one_hot)
        vec.extend(
            [
                min(math.log1p(count) / 5.0, 1.0),
                r_min / 63.0,
                r_max / 63.0,
                c_min / 63.0,
                c_max / 63.0,
            ]
        )

    missing = 8 - len(objects)
    if missing > 0:
        vec.extend([0.0] * missing * (16 + 5))

    return vec, int(row["action_id"])


class PolicyDataset(torch.utils.data.Dataset):
    def __init__(self, path: Path):
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        encoded = [encode_example(row) for row in rows]
        self.features = torch.tensor([item[0] for item in encoded], dtype=torch.float32)
        self.labels = torch.tensor([item[1] for item in encoded], dtype=torch.long)

    def __len__(self) -> int:
        return int(self.labels.shape[0])

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.features[idx], self.labels[idx]


class SmallPolicyNet(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.15),
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, len(ACTION_VOCAB)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def evaluate(model: SmallPolicyNet, loader: torch.utils.data.DataLoader, device: torch.device) -> dict[str, float]:
    model.eval()
    total = 0
    correct = 0
    total_loss = 0.0
    with torch.no_grad():
        for features, labels in loader:
            features = features.to(device)
            labels = labels.to(device)
            logits = model(features)
            loss = F.cross_entropy(logits, labels)
            total_loss += float(loss.item()) * labels.size(0)
            pred = logits.argmax(dim=1)
            correct += int((pred == labels).sum().item())
            total += int(labels.size(0))
    if total == 0:
        return {"loss": 0.0, "acc": 0.0}
    return {"loss": total_loss / total, "acc": correct / total}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-jsonl", type=Path, default=Path("artifacts/policy_data/policy_train.jsonl"))
    parser.add_argument("--valid-jsonl", type=Path, default=Path("artifacts/policy_data/policy_valid.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/small_policy_prior.pt"))
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_ds = PolicyDataset(args.train_jsonl)
    valid_ds = PolicyDataset(args.valid_jsonl)
    train_loader = torch.utils.data.DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    valid_loader = torch.utils.data.DataLoader(valid_ds, batch_size=args.batch_size)

    model = SmallPolicyNet(input_dim=int(train_ds.features.shape[1])).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)

    best_acc = -1.0
    best_state = None

    for epoch in range(1, args.epochs + 1):
        model.train()
        for features, labels in train_loader:
            features = features.to(device)
            labels = labels.to(device)
            logits = model(features)
            loss = F.cross_entropy(logits, labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        train_metrics = evaluate(model, train_loader, device)
        valid_metrics = evaluate(model, valid_loader, device)
        print(
            f"epoch={epoch:02d} "
            f"train_loss={train_metrics['loss']:.4f} train_acc={train_metrics['acc']:.4f} "
            f"valid_loss={valid_metrics['loss']:.4f} valid_acc={valid_metrics['acc']:.4f}"
        )
        if valid_metrics["acc"] >= best_acc:
            best_acc = valid_metrics["acc"]
            best_state = {
                "model_state": model.state_dict(),
                "input_dim": int(train_ds.features.shape[1]),
                "action_vocab": ACTION_VOCAB,
                "state_vocab": STATE_VOCAB,
                "history_vocab": HISTORY_VOCAB,
                "valid_acc": best_acc,
            }

    if best_state is None:
        raise SystemExit("No model state was saved.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, args.output)
    print(f"saved={args.output} valid_acc={best_acc:.4f}")


if __name__ == "__main__":
    main()
