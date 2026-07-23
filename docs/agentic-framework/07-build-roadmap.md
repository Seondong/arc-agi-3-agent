<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 07. Build Roadmap

## 왜 구현 순서가 중요한가

이 framework는 한 번에 완성하기엔 크다. 따라서 어떤 역할부터 구현해야 가장 빨리 가치가 나오고, 어떤 역할은 나중으로 미뤄도 되는지를 분명히 해야 한다. narrative들을 읽고 느낀 점은, 초반에는 “생각을 더 잘하게 만드는 구조”를 먼저 넣는 것이 중요하고, 이후에야 “그 생각을 자동화하는 모델”을 붙이는 것이 맞다는 것이다.

## Phase 0: 기존 harness를 망가뜨리지 않는 최소 확장

이 단계의 목표는 현재 Claude harness와 narrative workflow를 유지하면서, framework의 핵심 슬롯만 도입하는 것이다. Scene Canonicalizer의 최소 버전, Episode Memory, Belief Ledger, Trajectory Curator를 먼저 넣는다. 즉 지금 사람이 수동으로 하고 있는 `scene summary`, `motif beliefs`, `hypothesis list`, `prediction`, `surprise note`를 구조화된 파일로 남기게 한다.

이 단계가 끝나면, 비록 solve 능력은 크게 늘지 않아도 이후 모든 agent 구현의 공통 데이터 인터페이스가 생긴다.

## Phase 1: Perception Stack 구축

다음은 Scene Canonicalizer, Object Tracker, Relation Graph Builder, Goal Surface Detector를 코드 중심으로 구현한다. 이 단계는 가장 boring해 보이지만 실제론 가장 중요하다. scene representation이 흔들리면 뒤의 motif, planning, distillation이 전부 흔들린다.

여기서는 완벽한 semantic understanding보다 stable representation이 더 중요하다. 배경 분리, connected component 기반 object extraction, persistent ID, relation graph 생성만 안정되어도 큰 진전이다.

## Phase 2: Hypothesis Stack 구축

이 단계에서는 Motif Librarian, Analogy Retriever, Belief Ledger의 강화, Goal Inferencer의 초판을 만든다. 처음에는 top-3 motif retrieval과 evidence tagging만으로도 충분하다. 중요한 것은 model이 똑똑해지는 것보다, 가설 공간이 명시적으로 살아 있게 되는 것이다.

이 단계가 끝나면 system은 더 이상 단순 action tester가 아니라, “내가 지금 어떤 세계를 의심하고 있는가”를 외부에 설명할 수 있게 된다.

## Phase 3: Experimentation & World Model Stack

Experiment Designer, Mechanism Builder, Counterfactual Simulator, Surprise Auditor를 붙인다. 이 단계부터 world-model agent라는 이름이 실제로 어울리기 시작한다. probe의 질이 올라가고, 관측이 단순 로그가 아니라 규칙 수정 신호가 된다.

이 단계에선 아직 solve rate보다 `잘 실패하는가`가 더 중요하다. 즉 잘못된 가설을 빨리 죽이고, surprise를 근거 있게 해석하고, working theory를 점차 정제하는 능력을 보는 것이 맞다.

## Phase 4: Planning & Execution Stack

Phase Manager, Budget Controller, Subgoal Compiler, Planner, Execution Monitor, Recovery Manager를 붙인다. 이때부터는 narrative에 적힌 solve 초안이 실제 자동 계획으로 옮겨가기 시작한다.

초기엔 아주 얕은 planning만으로도 충분하다. 중요한 것은 planner의 깊이보다, epistemic mode와 instrumental mode를 헷갈리지 않는 것이다. execution monitor와 recovery manager는 초기부터 넣는 편이 좋다. 안 그러면 one-shot lucky solve만 나오고 재현성이 떨어진다.

## Phase 5: Cross-Game Memory & Distillation

여기서는 Cross-Game Memory와 Teacher Module을 붙인다. 각 게임에서 나온 motif, failure mode, 좋은 probe, belief revision 사례를 묶어 작은 모델용 학습셋으로 만든다. 이 단계가 되어야 비로소 “특정 게임을 푸는 에이전트”에서 “새 게임에 더 빨리 적응하는 시스템”으로 넘어간다.

## Phase 6: Canonical Evaluation & Kaggle Packaging

마지막으로 Canonical Evaluator와 Notebook Packager를 다듬는다. custom harness와 공식 경로의 차이를 줄이고, full framework에서 submission-time에 유지할 core를 추려낸다. 여기서부터는 solve capability뿐 아니라 runtime, stability, reproducibility가 중요해진다.

## 어떤 agent에게 무엇을 맡길 것인가

실제로 여러 agent에게 병렬로 맡긴다면 다음 식의 분업이 자연스럽다.

- Agent A: Perception stack 전담
- Agent B: Motif/Belief stack 전담
- Agent C: Experiment/World Model stack 전담
- Agent D: Planning/Execution stack 전담
- Agent E: Memory/Distillation/Evaluation stack 전담

이 분업의 장점은 write scope와 개념 scope가 비교적 분리된다는 점이다. perception이 안정되면 hypothesis가 쉬워지고, hypothesis가 명시되면 planning이 쉬워지고, 모든 것이 기록되면 distillation이 쉬워진다.

## 가장 먼저 실질적으로 만들 것

지금 당장 하나만 고르라면, 나는 `structured episode memory + belief ledger + trajectory curator`를 먼저 만들겠다. 이유는 간단하다. 이것은 현재 narrative 방식과 가장 잘 맞물리고, 사람의 수동 reasoning을 거의 그대로 시스템 인터페이스로 옮길 수 있으며, 이후 어떤 agent를 붙이더라도 공통 입력/출력으로 재사용할 수 있기 때문이다. 그 다음 순서는 Scene Canonicalizer, Object Tracker, Experiment Designer가 좋다.

## 최종 메모

이 roadmap의 목적은 처음부터 완전한 agent society를 만들자는 것이 아니다. 오히려 서술형 harness narrative에서 이미 드러난 인간적 적응 구조를, 너무 일찍 단순화하거나 통째로 신경망에 던져버리지 않기 위해, 필요한 기능을 명시적으로 보존하는 데 있다. 우리가 만들고 싶은 것은 “정답을 맞힌 모델”이 아니라, “새로운 게임 앞에서 점점 더 잘 적응하는 기계”다.

