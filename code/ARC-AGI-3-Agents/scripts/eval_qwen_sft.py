"""[Mar 29] Created by SD with GPT-5.4.

Evaluate a compact Qwen SFT adapter on ARC-AGI-3 action summaries.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import torch


ACTION_NAMES = ["ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6"]


def require_deps() -> tuple[Any, Any, Any]:
    try:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise SystemExit(
            "Missing evaluation dependencies. Install with `uv sync --extra qwen`."
        ) from exc
    return AutoModelForCausalLM, AutoTokenizer, PeftModel


def extract_action(text: str) -> str | None:
    match = re.search(r"\bACTION([1-6])\b", text.upper())
    if not match:
        return None
    return f"ACTION{match.group(1)}"


def build_prompt(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    prompt_messages = messages[:-1]
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    return "\n".join(
        f"{msg['role'].upper()}: {msg['content']}" for msg in prompt_messages
    ) + "\nASSISTANT: "


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument("--eval-jsonl", type=Path, default=Path("artifacts/policy_data/sft_valid.jsonl"))
    parser.add_argument("--max-new-tokens", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    AutoModelForCausalLM, AutoTokenizer, PeftModel = require_deps()
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    tokenizer = AutoTokenizer.from_pretrained(args.adapter_dir, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if torch.cuda.is_available():
        model_dtype = torch.float16
    elif torch.backends.mps.is_available():
        model_dtype = torch.float32
    else:
        model_dtype = torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        trust_remote_code=True,
        torch_dtype=model_dtype,
    )
    model = PeftModel.from_pretrained(model, args.adapter_dir)
    model.to(device)
    model.eval()

    rows = [
        json.loads(line)
        for line in args.eval_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit > 0:
        rows = rows[: args.limit]

    correct = 0
    total = 0

    for row in rows:
        prompt = build_prompt(tokenizer, row["messages"])
        target = row["messages"][-1]["content"]
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        gen = tokenizer.decode(
            output[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        ).strip()
        pred_action = extract_action(gen)
        target_action = extract_action(target)
        if pred_action is not None and pred_action == target_action:
            correct += 1
        total += 1

    acc = correct / total if total else 0.0
    print(json.dumps({"total": total, "correct": correct, "action_acc": acc}, indent=2))


if __name__ == "__main__":
    main()
