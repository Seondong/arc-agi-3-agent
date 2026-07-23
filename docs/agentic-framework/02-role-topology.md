<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 02. Role Topology

## 전체 구조

이 framework는 다섯 개의 큰 층으로 구성된다. `Perception`, `Hypothesis`, `Experimentation & World Modeling`, `Planning & Execution`, `Memory & Evaluation`이 그것이다. 중요한 점은 이 층들이 순차적으로만 동작하는 것이 아니라, 매 step마다 순환한다는 것이다. perception이 hypothesis를 갱신하고, hypothesis가 experiment design을 부르고, experiment 결과가 world model과 belief를 다시 수정하며, planning이 execution을 내보내고, execution 결과가 다시 perception과 memory로 들어온다.

사람이 새로운 게임에 적응하는 과정도 대체로 이 구조를 따른다. 처음에는 scene을 읽고, 익숙한 motif를 떠올리고, 무엇을 시험할지 고르고, 예상과 실제를 비교하고, 그에 맞춰 설명을 다시 쓰며, 어느 정도 확신이 생기면 비로소 구체적인 solve plan을 밀어붙인다. 따라서 역할 분해도 이 인간적 루프를 최대한 보존해야 한다.

## Layer 1: Perception

이 층은 raw grid를 바로 reasoning 입력으로 쓰지 않기 위해 존재한다. 역할은 scene을 정규화하고, object를 추출하고, 같은 object를 시간축으로 추적하고, 관계를 그래프로 만들고, 현재 어디에 주의를 둘지 결정하는 것이다. 이 층은 가능한 한 코드와 deterministic heuristic이 강하게 맡는 편이 좋다.

핵심 역할은 다음과 같다. `Scene Canonicalizer`, `Object Tracker`, `Relation Graph Builder`, `Attention Controller`, `Affordance Mapper`, 그리고 필요하다면 `Goal Surface Detector`다.

## Layer 2: Hypothesis

이 층은 현재 장면이 어떤 세계와 닮았는지 설명하는 계층이다. motif library를 참조해 장르 후보를 가져오고, 현재 관측을 그 장르들과 비교하고, 목표 상태를 추정하며, 경쟁 가설들의 belief state를 관리한다. 이 층은 deterministic code와 LLM reasoning이 섞여야 한다. catalog 자체는 코드/데이터로 두되, retrieval과 narrative explanation은 모델이 맡아도 좋다.

핵심 역할은 `Motif Librarian`, `Analogy Retriever`, `Goal Inferencer`, `Belief Ledger`, `Hypothesis Manager`다.

## Layer 3: Experimentation & World Modeling

이 층은 현재 belief state 아래에서 “무엇을 해보면 가장 많이 배울 수 있는가”를 결정하고, 관측 결과를 실행 가능한 규칙으로 옮기며, 반례가 생겼을 때 world model을 수정하는 역할을 맡는다. 이 층이 없으면 system은 멍청한 탐색기나 brittle한 planner가 된다.

핵심 역할은 `Experiment Designer`, `Mechanism Builder`, `Counterfactual Simulator`, `Surprise Auditor`, `World Model Editor`다.

## Layer 4: Planning & Execution

이 층은 언제 탐색할지, 언제 문제를 풀기 시작할지, 어느 중간 목표를 먼저 만들지, 실행 중에 드리프트가 생기면 어떻게 복구할지를 관리한다. 여기서 solve planner만 생각하면 안 된다. phase switching과 execution monitoring이 equally important하다.

핵심 역할은 `Phase Manager`, `Subgoal Compiler`, `Budget Controller`, `Planner`, `Execution Monitor`, `Recovery Manager`다.

## Layer 5: Memory & Evaluation

이 층은 두 가지 목표를 가진다. 하나는 현재 episode를 더 잘 풀기 위한 기억을 유지하는 것이고, 다른 하나는 이후 작은 모델에게 전이 가능한 데이터를 남기는 것이다. 또한 custom harness 결과와 canonical evaluation 결과를 분리해 추적하는 역할도 여기 들어간다.

핵심 역할은 `Episode Memory`, `Cross-Game Memory`, `Trajectory Curator`, `Teacher Module`, `Canonical Evaluator`, `Notebook Packager`다.

## 역할별 구현 성격

모든 역할을 LLM agent로 만들 필요는 없다. 오히려 다음처럼 나누는 것이 현실적이다.

- 코드/휴리스틱 우선: Scene Canonicalizer, Object Tracker, Relation Graph Builder, Budget Controller, Canonical Evaluator
- 코드 + 모델 혼합: Affordance Mapper, Goal Inferencer, Hypothesis Manager, Experiment Designer, Execution Monitor
- 모델 우선: Analogy Retriever, Surprise Auditor, Teacher Module
- 코드가 강하고 모델이 보조: Mechanism Builder, Counterfactual Simulator, Planner, Subgoal Compiler

## 최소 실행 루프

하나의 step에서 system이 수행하는 최소 루프는 다음과 같이 정리할 수 있다.

1. Scene Canonicalizer가 현재 grid를 정규화한다.
2. Object Tracker가 기존 identity와 연결한다.
3. Relation Graph Builder와 Affordance Mapper가 scene summary를 만든다.
4. Analogy Retriever와 Goal Inferencer가 motif/goal belief를 갱신한다.
5. Experiment Designer 또는 Planner가 다음 action 후보를 낸다.
6. Counterfactual Simulator가 top action들의 결과를 예측한다.
7. action을 실제로 수행한다.
8. Surprise Auditor가 예측과 실제의 차이를 해석한다.
9. World Model Editor와 Belief Ledger가 모델을 수정한다.
10. Execution Monitor가 phase 전환 또는 replanning 여부를 결정한다.
11. Trajectory Curator가 현재 step을 고밀도 데이터로 기록한다.

이 토폴로지는 narrative들에 이미 암묵적으로 존재하던 구조를 명시적 system design으로 다시 적은 것이다. 이후 문서들은 각 층을 더 자세히 나눈다.

