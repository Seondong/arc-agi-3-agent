<!-- [Mar 29] Created by SD with GPT-5.4. -->
# Qwen Hybrid Design

이 문서는 ARC-AGI-3 Kaggle 제출에서 `Qwen 0.8B`급 모델을 어디에 쓰는지, 그리고 왜 CNN과 분리해야 하는지를 고정하는 설계 문서다.

## 목표

Qwen의 역할은 unseen game을 단독으로 푸는 메인 에이전트가 아니다.

Qwen의 역할:

- compact state summary를 보고 다음 행동 타입 prior를 제공한다
- stuck 상태에서 exploration bias를 바꾼다
- 후보 행동을 rerank 한다
- `ACTION6`의 정확한 좌표 생성보다는 `ACTION6`를 시도할 가치가 있는지 판단한다

Qwen이 잘 못할 가능성이 큰 역할:

- 긴 tool loop 운영
- full 64x64 grid를 직접 읽고 장기 계획 수립
- 안정적인 JSON/function calling
- unseen mechanic의 깊은 개념화

## Inference 흐름

unseen task가 들어오면 추천 흐름은 아래와 같다.

1. CNN/탐색기가 짧은 탐색을 수행한다.
2. 최근 step들에서 action history, diff, object summary를 만든다.
3. Qwen은 compact prompt를 보고 다음 행동 분포를 제안한다.
4. 실제 실행 액션은 CNN 점수와 Qwen prior를 섞어서 선택한다.
5. `ACTION6`이 선택되면 좌표는 CNN heatmap 또는 object-center heuristic이 정한다.
6. 일정 step 동안 변화가 없으면 Qwen 비중을 높인다.

## Qwen 입력 포맷

입력은 grid 전체가 아니라 아래 요약만 사용한다.

- game id
- current step
- current level
- available actions
- recent actions 3~5개
- last diff cell count
- top objects 6~8개
- optional: level progress 여부

예시:

```text
Game: tn36
Step: 14
Level: 0
Available actions: ACTION1, ACTION2, ACTION3, ACTION6
Recent actions: RESET, ACTION1, ACTION1, ACTION6
Diff cells after previous step: 0
Objects: v9:n12@r10-15c20-27; v1:n2@r32-33c11-12

Choose the next action. Reply with either ACTION1-5 or ACTION6 x=<int> y=<int>.
```

## Qwen 출력 포맷

짧고 파싱 쉬운 포맷만 사용한다.

- `ACTION1`
- `ACTION4`
- `ACTION6 x=18 y=42`

설명문, JSON, tool schema는 쓰지 않는다.

## Score blending

추천 blending:

- 기본 상태: `0.75 * CNN + 0.25 * Qwen`
- stuck 상태: `0.55 * CNN + 0.45 * Qwen`
- Qwen이 없으면 `1.0 * CNN`

stuck 판정 예:

- 8 step 이상 meaningful diff 없음
- 같은 action type 반복
- level progress 없음

## ACTION6 처리

Qwen 0.8B에게 좌표 전체를 맡기지 않는다.

권장 방식:

- Qwen은 `ACTION6` 여부만 bias
- 좌표는 CNN heatmap top-k 평균 또는 object center heuristic 사용
- 클릭 후보를 3~8개 만들고, 필요하면 Qwen이 후보 중 타입만 밀어준다

## SFT 목적

SFT 목표는 “게임 해결 능력 증류”가 아니라 “작은 행동 prior 증류”다.

즉 학습 목적은:

- 지금 어떤 행동 타입이 유망한지 맞추기
- stuck에서 다른 행동 타입으로 전환하기
- 클릭형과 이동형을 구분하기

학습 목적이 아닌 것:

- full planner 학습
- chain-of-thought 학습
- long horizon memory 학습

## 데이터 생성

이미 compact SFT 데이터는 [`build_policy_datasets.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/build_policy_datasets.py) 가 생성한다.

출력:

- [`sft_train.jsonl`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/policy_data/sft_train.jsonl)
- [`sft_valid.jsonl`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/policy_data/sft_valid.jsonl)

## SFT 학습

LoRA adapter 기준:

```bash
uv sync --extra qwen
UV_CACHE_DIR=/Users/sundong/Documents/arc-agi-3/.uv-cache \
uv run scripts/train_qwen_sft.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --train-jsonl artifacts/policy_data/sft_train.jsonl \
  --valid-jsonl artifacts/policy_data/sft_valid.jsonl \
  --output-dir artifacts/qwen_sft_adapter
```

0.8B급을 쓸 경우에도 원칙은 같다.

## SFT 평가

adapter를 학습한 뒤에는 action-only 정확도를 먼저 본다.

```bash
UV_CACHE_DIR=/Users/sundong/Documents/arc-agi-3/.uv-cache \
uv run scripts/eval_qwen_sft.py \
  --base-model Qwen/Qwen2.5-0.5B-Instruct \
  --adapter-dir artifacts/qwen_sft_adapter \
  --eval-jsonl artifacts/policy_data/sft_valid.jsonl
```

## Kaggle 적용 방식

Kaggle에서는 Qwen을 “항상 매 step 호출”하지 않는 쪽이 더 안전하다.

추천:

- 게임 시작 직후 1회
- stuck 상태 진입 시 1회
- 레벨 전환 직후 1회

그 외 step은 CNN만 사용한다.

## 추천 실험 순서

1. 현재 compact SFT 데이터로 작은 Qwen LoRA를 학습한다.
2. action-only output 정확도를 본다.
3. unseen public 25개 재플레이에서 CNN+Qwen 혼합 성능을 본다.
4. 호출 빈도를 줄인 버전과 비교한다.
5. 성능이 나오면 Kaggle asset으로 adapter를 올린다.
