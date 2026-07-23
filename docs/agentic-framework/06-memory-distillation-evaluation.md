<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 06. Memory, Distillation, And Evaluation

## 기억은 부가 기능이 아니다

ARC-AGI-3에서 memory는 단순 편의 기능이 아니다. 현재 게임을 풀기 위한 episode memory와, 다음 게임에서 더 빨리 적응하기 위한 cross-game memory가 모두 필요하다. 또한 우리가 목표로 하는 것은 퍼즐을 푸는 것에 그치지 않고, 이 사고 구조를 나중에 작은 모델에 이식하는 것이므로, distillation 관점의 기록 체계도 필수다.

## Episode Memory

Episode Memory는 현재 게임 내부의 누적 관측을 저장한다. scene summary, object identity history, action/result pairs, active hypotheses, confidence traces, predicted vs actual differences, subgoal attempts, budget usage가 여기에 들어간다.

중요한 것은 raw log만 저장하지 않는 것이다. 같은 정보를 나중에 reasoning agent가 쉽게 다시 읽을 수 있는 structured form으로 남겨야 한다. 예를 들어 “현재 top motif”, “직전 surprise”, “현재 solve mode 여부”, “지금까지 확인된 action semantics” 같은 요약 슬롯이 있어야 한다.

## Cross-Game Memory

Cross-Game Memory는 여러 narrative와 플레이 경험에서 공통 구조를 뽑아내는 저장소다. 어떤 motif가 어떤 scene feature와 함께 등장했는지, 어떤 probe가 특히 diagnostic했는지, 어떤 surprise 패턴이 어떤 world-model patch로 이어졌는지, 어떤 실패 모드가 반복되는지를 축적해야 한다.

이 memory는 narrative corpus를 읽으며 사람이 “아, 이런 류 게임에서는 이걸 먼저 보지”라고 배우는 것과 같다. 나중에 small model distillation에서 실제로 전이하고 싶은 것도 대부분 이 계층의 지식이다.

## Trajectory Curator

Trajectory Curator는 실행 로그를 distillation-friendly example로 바꾸는 역할을 맡는다. narrative들이 이미 잘 보여주듯, 좋은 학습 데이터는 단순한 `state -> action` 쌍이 아니다. 훨씬 더 중요한 것은 `state summary -> motif belief -> active hypotheses -> chosen action -> prediction -> actual outcome -> surprise -> belief revision -> next mode`의 체인이다.

Curator는 특히 다음 순간을 강조해야 한다. motif가 바뀌는 순간, 핵심 action semantics가 밝혀진 순간, goal이 구체화된 순간, surprise로 인해 전략이 뒤집힌 순간, subgoal이 처음 성공한 순간이다. 이 전환점이 작은 모델에게 가장 비싼 supervision이 된다.

## Teacher Module

Teacher Module은 curated trajectory를 실제 학습 포맷으로 변환한다. 어떤 것은 classification task로, 어떤 것은 generation task로 내보내야 한다. 예를 들어 motif 분류, prediction-match 판정, surprise type 분류는 classification에 가깝다. 반면 next probe suggestion, belief revision explanation, subgoal narration은 generation에 가깝다.

Teacher는 또한 “무엇을 코드로 고정할지”를 구분해야 한다. object detection, diff computation, budget accounting, canonical evaluation은 굳이 모델이 배울 필요가 없다. 반대로 motif retrieval, explanation, surprise decomposition, probe selection은 모델이 배울 가치가 크다.

## Canonical Evaluator

custom harness와 실제 canonical path는 분리해서 관리해야 한다. 이번 프로젝트에서 scorecard URL 차이와 custom runner의 괴리를 겪은 만큼, evaluation 역할은 독립된 모듈로 둬야 한다. Canonical Evaluator는 공식 실행 경로에서 결과를 다시 검증하고, custom harness의 내부 metrics와 공인 evaluation 결과를 나란히 비교해야 한다.

이 역할이 있어야 “로컬에선 된다고 믿었는데 실제 경로에서는 다르다”는 상황을 줄일 수 있다.

## Notebook Packager

최종 목표 중 하나가 Kaggle notebook 제출이라면, memory/eval 층의 마지막에는 Notebook Packager가 있어야 한다. 이 컴포넌트는 world-model harness 전체를 Kaggle 런타임 제약 아래로 압축하는 역할을 맡는다. 어떤 역할은 제거되고, 어떤 것은 heuristic으로 바뀌고, 어떤 것은 small prior model로 남게 된다.

즉 packager는 단순 파일 복사가 아니라 “full harness에서 submission-time core를 추출하는 과정”이다.

## 평가 지표

이 framework는 단순 score만으로 평가하면 안 된다. 각 층에 맞는 지표가 필요하다. perception 층은 object stability와 region detection consistency, hypothesis 층은 motif calibration과 action semantics convergence, planning 층은 information gain efficiency와 subgoal success rate, memory 층은 distillation utility와 canonical-path agreement를 봐야 한다.

이 내부 지표가 있어야 단순히 한두 문제를 푸는 것이 아니라, framework 전체가 점진적으로 좋아질 수 있다.

## 첫 구현 우선순위

가장 먼저 필요한 것은 Episode Memory와 Trajectory Curator다. 이미 narrative들이 있는 만큼, 현재도 좋은 학습 재료가 쌓이고 있다. 그 다음 Canonical Evaluator를 분리하고, Cross-Game Memory와 Teacher Module을 붙이면 작은 모델 이식 경로가 훨씬 명확해진다. Notebook Packager는 마지막 단계지만, 설계는 지금부터 염두에 두는 것이 좋다.

