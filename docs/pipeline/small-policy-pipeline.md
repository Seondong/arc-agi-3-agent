<!-- [Mar 29] Created by SD with GPT-5.4. -->
# Small Policy Pipeline

25개 trajectory 로그를 바로 `Qwen3.5-0.8B` 엔드투엔드 플레이 SFT에 쓰기보다는, 먼저 압축된 상태 요약 기반의 작은 정책 prior를 만들고 Kaggle 제출에서 CNN과 섞는 흐름이다.

## 1. Dataset 생성

`code/ARC-AGI-3-Agents` 기준:

```bash
uv run scripts/build_policy_datasets.py \
  --input-dir data \
  --output-dir artifacts/policy_data
```

생성물:

- `artifacts/policy_data/policy_train.jsonl`
- `artifacts/policy_data/policy_valid.jsonl`
- `artifacts/policy_data/sft_train.jsonl`
- `artifacts/policy_data/sft_valid.jsonl`
- `artifacts/policy_data/metadata.json`

설명:

- `policy_*.jsonl`: 작은 MLP prior 학습용
- `sft_*.jsonl`: 나중에 Qwen instruction tuning에 바로 넣기 위한 compact SFT 포맷

## 2. 작은 prior 학습

```bash
uv run scripts/train_small_policy.py \
  --train-jsonl artifacts/policy_data/policy_train.jsonl \
  --valid-jsonl artifacts/policy_data/policy_valid.jsonl \
  --output artifacts/small_policy_prior.pt
```

출력:

- `artifacts/small_policy_prior.pt`

이 파일은 Kaggle Notebook에서 optional asset으로 로드할 수 있다.

## 3. Qwen SFT로 확장

`sft_train.jsonl` / `sft_valid.jsonl`는 compact state summary 기반이라 0.8B급 모델에도 원본 grid 전체보다 훨씬 유리하다.

권장:

- full grid 대신 objects, available actions, recent action history만 사용
- 출력 형식은 `ACTION3` 또는 `ACTION6 x=12 y=31`처럼 짧게 유지
- fine-tuned Qwen은 메인 정책이 아니라 reranker 또는 stuck-breaker로 사용

## 4. Kaggle 제출

루트의 [`kaggle_submission.ipynb`](/Users/sundong/Documents/arc-agi-3/kaggle_submission.ipynb)는 다음 흐름을 따른다.

- 기본 정책: 온라인 CNN
- 보조 정책: `small_policy_prior.pt`가 있으면 action prior를 가산
- fallback: prior가 없으면 CNN만으로 제출 가능

## 5. 추천 운영 방식

1. 더 많은 trajectory를 수집한다.
2. 레벨 진행 또는 diff가 있는 step 비중을 늘린다.
3. 작은 prior를 반복 학습한다.
4. 충분한 데이터가 쌓이면 compact SFT로 Qwen 0.8B를 추가한다.
