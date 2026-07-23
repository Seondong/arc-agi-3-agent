<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 05. Planning And Execution

## planning은 solve-only가 아니다

많은 시스템이 planner를 “정답 행동열을 찾는 모듈”로만 생각한다. 하지만 harness narrative들을 읽어 보면, 실제로 중요한 것은 solve planner 하나가 아니다. 처음엔 무엇을 시험할지 정하는 experiment designer가 필요하고, 어느 순간부터 solve mode로 넘어갈지 정하는 phase manager가 필요하며, 계획이 틀어졌을 때 즉시 복구하는 execution monitor가 필요하다.

## Phase Manager

Phase Manager는 현재 시스템이 epistemic mode, instrumental mode, recovery mode 중 어디에 있는지를 관리한다. epistemic mode에서는 정보 획득이 최우선이다. instrumental mode에서는 목표 달성이 우선이다. recovery mode에서는 직전 가설이나 plan이 깨졌을 때 손실을 줄이기 위해 다시 local probing으로 후퇴한다.

이 전환은 감이 아니라 신호 기반이어야 한다. hypothesis entropy, 최근 예측 정확도, 남은 에너지, goal confidence, 최근 surprise 강도 같은 값이 전환 조건이 된다.

## Experiment Designer

Experiment Designer는 “지금 어떤 행동을 해야 가장 많이 배울 수 있는가”를 고른다. 사람은 새 게임을 배울 때 무작정 랜덤 액션을 던지지 않는다. action semantics를 가장 잘 드러내는 실험, 경쟁 가설을 가장 많이 가르는 실험, 부작용이 적은 실험을 우선한다.

이 컴포넌트는 candidate action set에 대해 expected information gain을 평가해야 한다. 처음엔 정교한 수치 모델이 없어도 된다. “가설을 몇 개 가르는가”, “되돌리기 쉬운가”, “큰 비용 없이 수행 가능한가” 정도의 heuristic 점수로 시작할 수 있다.

## Budget Controller

ARC-AGI-3는 실험 비용이 있는 환경이다. 에너지, 스텝 수, action budget이 모두 중요하다. 따라서 planner 옆에는 반드시 Budget Controller가 있어야 한다. 이 역할은 현재 예산 아래에서 exploration allowance와 execution reserve를 분리해 관리한다.

예를 들어 남은 에너지가 충분하면 epistemic probing을 허용하고, 빠듯하면 solve-oriented 행동에 더 큰 가중치를 준다. narrative들이 말하는 “탐색 vs 실행의 트레이드오프”를 실제 규칙으로 옮기는 계층이다.

## Subgoal Compiler

Subgoal Compiler는 현재 world model과 goal belief를 받아 중간 목표를 만든다. 사람은 문제를 풀 때 거의 항상 중간 목표를 만든다. 특정 물체 높이까지 이동, 특정 블록 한 개만 정렬, 스위치 한 번만 누르기, 특정 marker 하나만 토글하기 같은 것이 여기에 해당한다.

이 역할이 없으면 planner는 너무 긴 action chain을 한 번에 뽑아내려 하고 brittle해지기 쉽다. 특히 sorting, threading, multi-stage interaction 게임에서 subgoal compiler는 필수다.

## Planner

Planner는 현재 phase에 따라 두 가지 역할을 번갈아 한다. epistemic mode에서는 probe plan을, instrumental mode에서는 solve plan을 만든다. solve plan도 full-depth exhaustive search일 필요는 없다. 현재 belief가 불확실하다면 shallow lookahead와 reranking만으로도 충분히 유용할 수 있다.

Planner는 deterministic search와 model-based heuristics를 섞는 것이 좋다. 공간 이동은 BFS/DFS/A*로 처리하고, action semantics가 애매한 부분은 world model과 belief scores를 참고해 후보를 정렬한다.

## Execution Monitor

Execution Monitor는 실행 중에 “계획대로 되고 있는가”를 감시한다. action이 성공했는지, predicted subgoal progress가 실제로 일어났는지, drift가 있는지, 예상치 못한 side effect가 발생했는지 판단한다.

이 컴포넌트는 단순 logging이 아니다. monitor는 plan continuation, local repair, full replanning 중 어느 쪽으로 갈지 결정해야 한다. 이 층이 있어야 long action chain도 견고해진다.

## Recovery Manager

Recovery Manager는 plan failure 이후 무엇을 할지 정한다. 직전 subgoal까지 되돌아갈지, belief를 부분적으로 reset할지, motif 경쟁 구조를 다시 넓힐지, 추가 probe를 넣을지 결정해야 한다. 많은 narrative가 surprise 대응을 잘 적어두었지만, 그것을 solve phase 복구 전략까지 연결한 문서는 상대적으로 적었다. framework에서는 이 역할을 독립시켜야 한다.

## 실행 루프 예시

실행 루프는 다음처럼 생각할 수 있다. Phase Manager가 현재 mode를 결정한다. Budget Controller가 허용 예산을 계산한다. epistemic mode라면 Experiment Designer가 probe를 고른다. instrumental mode라면 Subgoal Compiler와 Planner가 행동열을 낸다. action이 실행되면 Execution Monitor가 drift를 보고, 필요하면 Recovery Manager가 mode를 되돌리거나 belief update를 요청한다.

## 첫 구현 우선순위

처음부터 모든 planner를 만들 필요는 없다. 가장 먼저 필요한 것은 Budget Controller와 Phase Manager다. 그 다음 간단한 Experiment Designer를 붙이고, solve phase용 Subgoal Compiler와 Planner를 얹는 것이 좋다. Execution Monitor와 Recovery Manager는 첫 성공 trajectory가 나온 뒤 곧바로 붙여야 한다. 그래야 brittle한 one-off solver가 아니라 점점 더 견고한 agent로 갈 수 있다.

