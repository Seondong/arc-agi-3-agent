"""[Mar 29] Created by SD with GPT-5.4.

Train a compact Qwen SFT adapter on ARC-AGI-3 action summaries.

Expected input format:
    JSONL rows with:
      {
        "messages": [
          {"role": "system", "content": "..."},
          {"role": "user", "content": "..."},
          {"role": "assistant", "content": "ACTION3"}
        ],
        "metadata": {...}
      }

This script is intentionally small and dependency-light. It uses a masked
causal-LM objective so only assistant tokens contribute to the loss.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader, Dataset


IGNORE_INDEX = -100


def require_qwen_deps() -> tuple[Any, Any, Any, Any, Any]:
    try:
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            get_cosine_schedule_with_warmup,
        )
    except ImportError as exc:
        raise SystemExit(
            "Missing Qwen training dependencies. "
            "Install with `uv sync --extra qwen`."
        ) from exc
    return AutoModelForCausalLM, AutoTokenizer, LoraConfig, TaskType, get_cosine_schedule_with_warmup, get_peft_model


def format_conversation(tokenizer: Any, messages: list[dict[str, str]]) -> tuple[str, str]:
    prompt_messages = messages[:-1]
    answer_message = messages[-1]
    if answer_message["role"] != "assistant":
        raise ValueError("Last message must be assistant.")

    if hasattr(tokenizer, "apply_chat_template"):
        prompt_text = tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        answer_text = answer_message["content"] + tokenizer.eos_token
    else:
        prompt_text = "\n".join(
            f"{msg['role'].upper()}: {msg['content']}" for msg in prompt_messages
        ) + "\nASSISTANT: "
        answer_text = answer_message["content"] + tokenizer.eos_token
    return prompt_text, answer_text


class SFTDataset(Dataset):
    def __init__(self, path: Path, tokenizer: Any, max_length: int, limit: int = 0):
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if limit > 0:
            rows = rows[:limit]
        samples = []
        for row in rows:
            messages = row["messages"]
            prompt_text, answer_text = format_conversation(tokenizer, messages)
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            answer_ids = tokenizer(answer_text, add_special_tokens=False)["input_ids"]
            input_ids = (prompt_ids + answer_ids)[:max_length]
            labels = ([IGNORE_INDEX] * len(prompt_ids) + answer_ids)[:max_length]
            attention_mask = [1] * len(input_ids)
            samples.append(
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "labels": labels,
                }
            )
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, list[int]]:
        return self.samples[idx]


@dataclass
class Collator:
    tokenizer: Any

    def __call__(self, batch: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        pad_id = self.tokenizer.pad_token_id
        max_len = max(len(item["input_ids"]) for item in batch)
        input_ids = []
        attention_mask = []
        labels = []
        for item in batch:
            pad = max_len - len(item["input_ids"])
            input_ids.append(item["input_ids"] + [pad_id] * pad)
            attention_mask.append(item["attention_mask"] + [0] * pad)
            labels.append(item["labels"] + [IGNORE_INDEX] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def evaluate(model: Any, loader: DataLoader, device: torch.device) -> float:
    model.eval()
    total_loss = 0.0
    total_items = 0
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            output = model(**batch)
            batch_size = int(batch["input_ids"].size(0))
            total_loss += float(output.loss.item()) * batch_size
            total_items += batch_size
    return total_loss / max(total_items, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--train-jsonl", type=Path, default=Path("artifacts/policy_data/sft_train.jsonl"))
    parser.add_argument("--valid-jsonl", type=Path, default=Path("artifacts/policy_data/sft_valid.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/qwen_sft_adapter"))
    parser.add_argument("--max-length", type=int, default=768)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-train-samples", type=int, default=0)
    parser.add_argument("--max-valid-samples", type=int, default=0)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    args = parser.parse_args()

    torch.manual_seed(args.seed)

    (
        AutoModelForCausalLM,
        AutoTokenizer,
        LoraConfig,
        TaskType,
        get_cosine_schedule_with_warmup,
        get_peft_model,
    ) = require_qwen_deps()

    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if torch.cuda.is_available():
        model_dtype = torch.float16
    elif torch.backends.mps.is_available():
        model_dtype = torch.float32
    else:
        model_dtype = torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        trust_remote_code=True,
        torch_dtype=model_dtype,
    )
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.to(device)
    print(f"training_device={device} dtype={model_dtype}")

    train_ds = SFTDataset(
        args.train_jsonl,
        tokenizer,
        args.max_length,
        limit=args.max_train_samples,
    )
    valid_ds = SFTDataset(
        args.valid_jsonl,
        tokenizer,
        args.max_length,
        limit=args.max_valid_samples,
    )
    collator = Collator(tokenizer)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=collator)
    valid_loader = DataLoader(valid_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collator)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = max(1, (len(train_loader) * args.epochs) // max(args.grad_accum, 1))
    warmup_steps = int(total_steps * args.warmup_ratio)
    scheduler = get_cosine_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    best_valid = float("inf")
    global_step = 0
    model.train()

    for epoch in range(1, args.epochs + 1):
        optimizer.zero_grad()
        for step, batch in enumerate(train_loader, start=1):
            batch = {k: v.to(device) for k, v in batch.items()}
            output = model(**batch)
            loss = output.loss / args.grad_accum
            loss.backward()

            if step % args.grad_accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                global_step += 1

        valid_loss = evaluate(model, valid_loader, device)
        print(f"epoch={epoch:02d} valid_loss={valid_loss:.4f} steps={global_step}")
        if valid_loss < best_valid:
            best_valid = valid_loss
            args.output_dir.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(args.output_dir)
            tokenizer.save_pretrained(args.output_dir)
            meta = {
                "base_model": args.model,
                "best_valid_loss": best_valid,
                "max_length": args.max_length,
                "train_jsonl": str(args.train_jsonl),
                "valid_jsonl": str(args.valid_jsonl),
            }
            (args.output_dir / "training_meta.json").write_text(
                json.dumps(meta, indent=2) + "\n",
                encoding="utf-8",
            )

    print(f"saved_adapter={args.output_dir} best_valid_loss={best_valid:.4f}")


if __name__ == "__main__":
    main()
