<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 16. Selector-Aware Scheduling

`Experiment Designer`가 supervisor에 통합되면서, 이제 unattended loop 안에는 두 종류의 다음 probe가 공존하게 되었다. 하나는 bootstrap reasoner가 주는 기본 discovery probe이고, 다른 하나는 Claude가 설계한 hypothesis-discriminating probe다. 이 둘이 동일한 수준의 follow-up로 취급되면, richer planner를 붙인 효과가 scheduler 단계에서 희석될 수 있다. 그래서 이번 단계에서는 queue policy를 selector-aware하게 바꾸었다.

핵심 변화는 [`agentic_queue_policy.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_queue_policy.py)에 있다. 이제 game history는 단순히 `recent_probe_families`와 `recent_goal_hints`뿐 아니라, `recent_next_probe_selectors`, `experiment_designer_followups`, `bootstrap_followups`도 추적한다. supervisor manifest에 `next_probe_selector`가 남고, follow-up item에 `probe_family`가 `experiment-designer-followup` 또는 `bootstrap-followup`로 들어가므로, scheduler는 이 차이를 읽을 수 있다.

현재 점수 정책은 명시적이다. `experiment-designer-followup`는 기본적으로 추가 가점을 받는다. 또한 최근 history에 experiment designer selector가 거의 등장하지 않았으면, selector diversity bonus를 더 준다. 반대로 stagnation streak가 임계값을 넘은 게임이라도, experiment-designer follow-up에는 stagnation penalty를 완화해서 적용한다. 이유는 간단하다. 정체된 게임일수록 “또 하나의 기본 probe”보다 “경쟁 가설을 갈라놓는 richer probe”를 더 오래 살려두는 편이 가치가 크기 때문이다.

이 변화는 단순한 우선순위 조정 이상의 의미를 갖는다. 지금까지 night loop는 fresh seed와 follow-up 사이를 조절하는 수준이었다. 이제부터는 같은 follow-up들 사이에서도 “어떤 내부 planner가 제안했는가”를 기준으로 다르게 다룰 수 있다. 즉 control-plane이 처음으로 planner provenance를 반영하기 시작한 것이다. 이건 나중에 여러 planner가 병렬로 제안하는 구조로 확장할 때 매우 중요하다. 예를 들어 bootstrap reasoner, experiment designer, future world-model planner가 서로 다른 follow-up를 던지더라도, scheduler가 provenance-aware하게 선택할 수 있어야 한다.

또 하나 중요한 점은, 이 selector-aware 정책이 traceable하다는 것이다. `night_trace.jsonl`에는 여전히 각 pending item의 `score`와 `reasons`가 남는다. 따라서 다음 날 결과를 읽을 때, “왜 experiment-designer follow-up가 bootstrap-followup보다 먼저 살아남았는가”를 그대로 확인할 수 있다. 선택 정책을 외재화해두면, 이후 실제 성능과의 상관을 보고 가중치를 조정하기가 훨씬 쉬워진다.

지금 단계의 정책은 아직 단순하다. `experiment-designer-followup`라는 문자열 기반 family label에 크게 의존하고 있고, probe의 실제 내용이나 information gain 수치를 직접 읽지는 않는다. 그러나 이 정도만으로도 중요한 첫 걸음이다. 이제 outer loop는 단순히 action prefix를 반복하는 구조가 아니라, **planner quality의 차이를 scheduling에서 반영하는 구조**로 이동하기 시작했다. 이 기반 위에서 다음 단계는 자연스럽다. supervisor가 manifest에 남긴 `expected_information_gain`과 richer probe schema를 queue policy가 직접 읽어, selector 이름이 아니라 실제 예상 정보량을 반영하는 방향으로 발전할 수 있다.
