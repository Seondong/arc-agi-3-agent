#!/usr/bin/env bash
# The whole distillation experiment, end to end, rerunnable as data accumulates.
#
#   export -> split by game -> baseline eval -> LoRA -> eval -> compare
#
# Every stage writes its numbers to artifacts/wm_sft/ so a rerun with more data
# can be compared against an earlier one rather than replacing it.
#
# Usage: scripts/wm/run_distill.sh [holdout_game] [iters]
set -uo pipefail
cd "$(dirname "$0")/../.."

HOLDOUT="${1:-cd82}"
ITERS="${2:-200}"
MODEL="/Users/sundong/Documents/arc-agi-3/models/qwen3.6-27b-mlx-4bit"
ADAPTER="artifacts/wm_sft/adapter-${HOLDOUT}"
STAMP="$(date +%m%d-%H%M)"

echo "════ 1. export every game's journal ════"
for g in ka59 tu93 m0r0 sk48 ft09 vc33 bp35 cd82 ls20; do
  uv run python scripts/wm/export_dataset.py --game "$g" >/dev/null 2>&1
done
uv run python - <<'PY'
import json, glob, collections
c = collections.Counter()
for f in glob.glob("artifacts/wm_dataset/*.jsonl"):
    for line in open(f):
        try: c[json.loads(line)["type"]] += 1
        except Exception: pass
print("  corpus:", dict(c), "total", sum(c.values()))
PY

echo "════ 2. split, holding out ${HOLDOUT} ════"
uv run python scripts/wm/build_sft.py --holdout "$HOLDOUT" 2>&1 | grep -vE "INFO"

TRAIN=$(wc -l < artifacts/wm_sft/train.jsonl | tr -d ' ')
TEST=$(wc -l < artifacts/wm_sft/test.jsonl | tr -d ' ')
if [ "$TRAIN" -lt 4 ]; then
  echo "  train has only ${TRAIN} example(s) — not a training set. Stopping."
  echo "  (repair pairs come from refutations; let the collection runs continue.)"
  exit 2
fi

echo "════ 3. LoRA (${ITERS} iters, prompt masked) ════"
uv run python -m mlx_lm lora \
  --model "$MODEL" --train --data artifacts/wm_sft \
  --fine-tune-type lora --mask-prompt --grad-checkpoint \
  --batch-size 1 --num-layers 8 --iters "$ITERS" \
  --learning-rate 1e-5 --max-seq-length 6144 \
  --steps-per-report 10 --steps-per-eval 50 \
  --adapter-path "$ADAPTER" 2>&1 | tail -25

echo "════ 4. eval: base vs tuned on the held-out game ════"
uv run python scripts/wm/eval_repair.py --tag "base-${HOLDOUT}-${STAMP}" \
  --max-tokens 2600 2>&1 | grep -vE "INFO" | tail -4
uv run python scripts/wm/eval_repair.py --tag "lora-${HOLDOUT}-${STAMP}" \
  --adapter "$ADAPTER" --max-tokens 2600 2>&1 | grep -vE "INFO" | tail -4

echo "════ 5. compare ════"
uv run python - "$HOLDOUT" "$STAMP" <<'PY'
import json, sys
from pathlib import Path
h, stamp = sys.argv[1], sys.argv[2]
for tag in (f"base-{h}-{stamp}", f"lora-{h}-{stamp}"):
    p = Path(f"artifacts/wm_sft/eval_{tag}.json")
    if p.exists():
        s = json.loads(p.read_text())["summary"]
        print(f"  {tag:26} replays {s['replays']}/{s['n']}  loads {s['loads']}/{s['n']}"
              f"  {s['mean_out_tokens']} tok  {s['mean_seconds']}s")
PY
