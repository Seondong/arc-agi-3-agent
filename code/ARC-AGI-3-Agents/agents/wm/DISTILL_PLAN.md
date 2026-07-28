# Distillation plan — from frontier byproducts to a Kaggle-deployable model

Written 2026-07-29, before implementation, after reading three harnesses
(PRO-LONG, baseline1/ewma_sv, duck-harness). This file is the plan of record; it
is meant to survive a cleared context and to be checked against afterwards.

---

## 1. The target we are actually aiming at

The Kaggle competition rerun has **no internet**. No Claude, no GPT, no
OpenRouter. One open-weight model on one GPU, 25 games, and a wall clock.

duck-harness is the only one of the three studied harnesses that lives there:
`Qwen3.6-27B-FP8` on vLLM, 20 passes per game, 45 minutes per game, scoring
1.600 mean on the run bundled with the repo. That is the shape of the thing we
have to produce.

Everything else this project has built — Claude Code as a brain, the executable
world model, the replay verifier — is *upstream* of that. It is how we generate
training data, not what gets deployed.

## 2. Where we actually stand

Measured, not estimated:

```
corpus            509 pairs   predict 251 · probe 222 · plan 15 · analyse 15 · repair 6
games attempted   9 of 25
levels cleared    tu93 9/9, vc33 2/7, m0r0 2/?, ft09 1/6, sk48 1/?, four at zero
hardware          M4 Max, 64GB unified, no CUDA
```

Three problems, in order of severity.

**The corpus is in the wrong format.** Our pairs describe a six-method Python
module (`reconstruct/step/render/is_goal/fingerprint/ignore`). A model deployed
in the Duck speaks something else entirely: a `python` tool call against a
runtime that hands it `current_frame.segmentation`, `history`, `action(...)`,
plus a seven-slot textual note. Nothing we have is in that shape.

**The corpus is far too small.** 509 pairs, of which the only type that teaches
model-*writing* is `repair`, at 6. A LoRA on 6 examples memorises 6 examples.

**We are missing the layer all three harnesses have.** PRO-LONG keeps
`notes.md`, baseline1 keeps `world_model.md` plus a per-level reasoning log,
Duck keeps a seven-slot note with `goal_model` and `open_questions` as named
fields. We keep only the code. Three independent implementations converged on
carrying *unsettled* knowledge alongside settled knowledge; we carry only
settled knowledge, and our brain starts every call with no memory at all.

That third one is also the direct explanation of the KA59 failure. The dynamics
were right — models replayed 74/74 steps cell-exactly — and the gate stopped
four times on `status predicted=LEVEL_COMPLETED actual=RUNNING`. A goal model
that nobody was maintaining as its own artifact.

## 3. What to distil, and into what

Rejected: **retarget the corpus to Duck's tool-call format.** We would be
synthesising the mapping from our runtime to theirs, and grading it with
nothing. Fabricated supervision.

Rejected: **build our own Kaggle harness end to end.** That is reinventing the
Duck with less evidence, and it postpones any measurement.

**Chosen: distil the one capability our data uniquely carries, and measure it
with the verifier we already trust.**

Of the three harnesses only baseline1 and ours can produce a `repair` pair —
refuted source, the cells the verifier pointed at, corrected source — because
only those two run a replay verifier. The Duck has no verifier and cannot
generate that sentence. So the thing worth distilling is exactly the thing the
deployment target cannot teach itself:

> given a world model and a pointed counterexample, write the corrected model.

And it is scoreable **locally and objectively**, with no GPU cluster and no
game API: run the model's output through `run_backtest` against recorded
timelines. Green or not green. That is the eval.

## 4. The experiment

Base model: `lmstudio-community/Qwen3.6-27B-MLX-4bit` — the same base as
duck-harness (Qwen3.6-27B), quantised for Apple Silicon because vLLM is CUDA
only. Deviation from duck-harness noted; the architecture and size match.

```
                 held-out repair tasks, scored by run_backtest
                                  |
  base Qwen3.6-27B  ───────────────┤   ← baseline, no training
  base + LoRA(ours) ───────────────┘   ← the treatment
```

Metrics, in order of how much they mean:

| metric | why |
|---|---|
| replays green | objective; the verifier decides, not us |
| rounds to green | a wrong model holding a counterexample is not a failure |
| syntactically loadable | a 27B that cannot emit a valid module is unusable |
| output length | drift toward rambling is a known SFT failure |

Held-out split by **game**, not by pair: training on ka59 and testing on ka59 is
memorisation. With repair pairs this scarce, leave-one-game-out is the honest
protocol.

## 5. Phases and what each has to show

**Phase 0 — collect (running).** Two streams of `autosolve` over ka59, ft09,
vc33, cd82, bp35. Repair pairs come from refutations, not from wins, so games we
cannot solve still pay. Success: repair count materially above 6.

**Phase 1 — convert.** `scripts/wm/build_sft.py`: journal → chat-format JSONL.
System prompt is the model contract; user turn is evidence + pointed bug +
current source; assistant turn is the corrected source. Success: a sample round
trips and the assistant turn actually loads as a module.

**Phase 2 — the model runs at all.** Load the 4-bit 27B under MLX, generate
once, measure tokens/sec and peak memory. Success: it answers, and memory fits.

**Phase 3 — baseline.** Base model on held-out repair tasks, scored by
`run_backtest`. Success: a number, whatever it is.

**Phase 4 — LoRA.** `mlx_lm.lora` on the converted set. Success: loss decreases
and the adapter loads.

**Phase 5 — compare.** Same eval, same tasks, tuned vs base.

**Phase 6 — write it down.** A page next to the three comparisons, with the
numbers and with whatever failed.

## 6. What is likely to go wrong

Stated in advance so the result cannot be reinterpreted afterwards.

- **Six repair pairs cannot move a 27B.** Most likely outcome is no measurable
  difference, or degradation. If so, the finding is about the corpus, and the
  pipeline is still the deliverable.
- **4-bit quantisation may not emit valid Python reliably.** If the base model
  cannot produce a loadable module at all, the eval floors at zero and the
  comparison says nothing. Check this in Phase 2, before spending hours.
- **MLX is not vLLM.** Nothing measured here transfers to Kaggle throughput.
  This is an experiment about whether the data teaches anything, not about
  deployment performance.
- **A LoRA that improves repair may damage general ability.** Not measured
  tonight; noted as an open risk.

## 7. What this does not do

It does not produce a Kaggle submission. It does not touch the Duck's runtime.
It does not test whether a distilled model plays games better — only whether it
repairs world models better, which is the one thing our data is actually about.

Those are the next steps, and they depend on this one producing a signal.
