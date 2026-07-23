<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 17. Information-Gain-Aware Scheduling

이전 단계에서 unattended night loop는 `selector-aware`해졌다. 즉 `Experiment Designer`가 제안한 follow-up와 bootstrap reasoner가 제안한 follow-up를 provenance 차원에서 구분할 수 있게 되었다. 하지만 그 구조만으로는 아직 부족했다. 같은 `Experiment Designer` follow-up 안에서도 어떤 probe는 경쟁 가설을 거의 갈라놓지 못하고, 어떤 probe는 한 번의 실행으로 belief state를 크게 재편할 수 있다. 그러므로 scheduler는 “누가 제안했는가”뿐 아니라 “그 제안이 얼마나 많은 것을 배울 것으로 예상되는가”도 읽어야 한다.

이번 단계에서는 그 연결을 실제 코드로 관통시켰다. 먼저 [`agentic_supervisor.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_supervisor.py)의 `QueueItem`에 `expected_information_gain` 필드를 추가했다. supervisor는 `design_next_probe(...)` 또는 fallback bootstrap reasoner가 돌려준 `ProbeSuggestion.expected_information_gain` 값을 follow-up queue item에 그대로 싣는다. 따라서 follow-up queue는 이제 단순 action prefix 목록이 아니라, “이 action prefix를 이어서 실행하면 얼마만큼의 정보 획득이 기대되는가”라는 meta-signal까지 품은 work queue가 되었다.

그 다음 [`agentic_queue_policy.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_queue_policy.py)는 이 숫자를 직접 점수화한다. 현재 정책은 세 층으로 작동한다. 첫째, pending item 자체의 `expected_information_gain`이 높으면 기본 가점을 준다. 둘째, 아주 높은 probe는 추가 bonus를 받고, 반대로 depth가 이미 쌓인 follow-up인데 정보량이 너무 낮으면 소폭 penalty를 받는다. 셋째, game history 안에 최근 probe들이 남긴 기대 정보량 평균과 비교하여, 이번 probe가 그 baseline을 웃도는지 밑도는지를 본다. 즉 절대값과 상대값을 둘 다 본다.

이 상대 baseline이 중요한 이유는 게임별 phase 차이 때문이다. 어떤 게임은 아직 action semantics조차 거의 안 밝혀진 초반이라 0.45짜리 probe도 상당히 좋을 수 있다. 반면 어떤 게임은 이미 여러 discovery probe를 거쳐서, 0.45짜리는 이제 애매한 수준일 수 있다. 그래서 scheduler는 “0.45는 무조건 좋다”라고 보지 않고, 그 게임이 최근까지 어떤 수준의 probe를 받아왔는지와 함께 읽는다. 결국 이건 world-modeling loop를 더 인간답게 만드는 장치다. 사람도 새로운 게임을 할 때 단순히 “유용해 보이는 실험”이 아니라, “지금까지 해본 실험들에 비해 얼마나 더 결정적인 실험인가”를 감으로 판단한다.

또 하나의 실용적인 변화는 traceability다. `PendingAssessment.to_dict()`가 `expected_information_gain`을 노출하므로, `night_trace.jsonl`을 다음 날 열어보면 queue item별로 score, keep 여부, 이유 문자열과 함께 정보량 수치도 그대로 볼 수 있다. 이건 단순 편의가 아니다. unattended loop는 시간이 길어질수록 왜 어떤 아이템이 선택되었는지 설명 가능한 구조가 중요해진다. 그렇지 않으면 외형상 자동화만 되고, 실제로는 “왜 이렇게 돌았는지 아무도 모르는” black box가 된다.

지금 단계의 정책은 아직도 보수적이다. 기대 정보량은 여전히 proposal 단계의 heuristic estimate이지, 실제로 획득된 정보량이 아니다. 즉 world model이 probe를 과대평가하면 scheduler도 그 영향을 받을 수 있다. 하지만 이건 괜찮은 출발점이다. 우리가 필요한 것은 처음부터 완벽한 정보이론 시스템이 아니라, richer planner가 산출한 epistemic signal이 outer loop에서 증발하지 않도록 하는 연결이다. 그 연결이 생기면 이후엔 실제 실행 후의 surprise, belief revision magnitude, newly ruled-out hypotheses 같은 지표를 수집해 expectation calibration으로 넘어갈 수 있다.

정리하면, 이번 단계에서 night loop는 `planner provenance-aware`에서 한 걸음 더 나아가 `epistemic value-aware`한 구조가 되었다. 이제 follow-up queue는 단순 action backlog가 아니라, expected information gain을 담은 실험 우선순위 목록으로 진화하기 시작했다. 이건 나중에 `Experiment Designer`, future world-model planner, motif-specific local planners가 모두 병렬로 follow-up를 던지는 상황에서도 매우 중요한 기반이 된다. scheduler는 더 이상 “무슨 액션을 할 것인가”만 고르는 것이 아니라, “다음에 어떤 실험이 belief state를 가장 많이 바꿀 것인가”를 점점 더 직접적으로 고르게 된다.
