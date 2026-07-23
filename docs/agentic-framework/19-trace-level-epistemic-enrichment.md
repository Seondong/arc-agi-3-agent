<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 19. Trace-Level Epistemic Enrichment

이전 단계에서 night loop는 expected information gain과 actual information gain baseline까지 보게 되었다. 하지만 중요한 문제가 하나 남아 있었다. scheduler는 점점 smarter해지고 있는데, 정작 episode trace 자체는 여전히 “무슨 액션을 했고 화면이 어떻게 바뀌었는가” 수준에 머무르고 있었다. 이 상태에선 다음 날 기록을 읽어도, 그 probe가 belief state를 얼마나 흔들었는지, planner가 얼마나 과신했는지, world model이 실제로 얼마나 수정되었는지를 trace 자체만으로는 바로 알기 어려웠다.

그래서 이번 단계에서는 trace를 post-hoc하게 풍부하게 만드는 enrichment pass를 추가했다. 핵심 아이디어는 단순하다. supervisor가 episode를 만들고 난 직후에는 parent episode와의 비교 정보가 충분하지 않을 수 있다. 하지만 night loop는 round가 끝날 때 전체 manifest history를 갖고 있으므로, 그 시점에는 `parent_episode_id`를 따라 올라가 current observation, parent observation, current belief, parent belief, trace tail을 모두 비교할 수 있다. 즉 epistemic metrics는 supervisor의 순간적 시야보다 night loop의 post-hoc 시야에서 더 정확히 계산할 수 있다.

이를 위해 [`agentic_episode_metrics.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_episode_metrics.py)에 actual gain 계산 외에 belief revision 계산을 추가했다. 이 모듈은 motif confidence shift, hypothesis confidence shift, hypothesis pruning/discard, goal confidence shift, 그리고 expected-vs-actual information gain gap을 바탕으로 `belief_revision_score`, `hypothesis_pruning_count`, `surprise_magnitude`를 추정한다. 중요한 점은 여기서 surprise를 단지 텍스트 이벤트로만 보지 않는다는 것이다. planner가 `0.75`의 정보를 얻을 것이라고 기대했는데 실제로는 `0.0`이었다면, 그 gap 자체가 이미 epistemic surprise다.

그 다음 [`agentic_trace_enricher.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_trace_enricher.py)가 round 종료 후 completed rows를 순회하며, 이 metrics를 각 episode의 trace와 별도 `episode_metrics.json`에 기록한다. `TrajectoryRecord` 스키마도 확장되어, 이제 trace에는 `surprise_magnitude`, `active_hypothesis_count`, `discarded_hypothesis_count`, `hypothesis_pruning_count`, `belief_revision_score`, `belief_revision_reasons`, `actual_information_gain`, `actual_information_gain_reasons`가 직접 들어간다. 즉 trace가 더 이상 단순 trajectory log가 아니라, epistemic accounting ledger에 가까워지기 시작한 것이다.

이 구조의 장점은 두 가지다. 첫째, scheduler와 trace가 같은 개념어를 공유하게 된다. queue policy가 actual gain baseline을 보고 probe를 고르는데, 이제 trace에도 그 actual gain이 남으니 다음 날 사람이 읽을 때 같은 프레임으로 이해할 수 있다. 둘째, later-stage distillation에도 유리하다. 작은 모델에게 단순 action sequence만 주는 것보다, “이 probe는 실제로 정보가 거의 없었고 planner가 과신했다”는 label까지 붙어 있는 데이터가 훨씬 가치가 크다.

`sk48` smoke run에서도 이 변화가 명확했다. `["RESET", "ACTION6"]` episode는 planner가 `expected_information_gain=0.75`로 봤지만, 실제로는 `NO CHANGE`였고 actual gain은 `0.0`으로 계산되었다. 그 결과 trace에는 `surprise_magnitude=0.75`, `belief_revision_score=0.0`, `actual_information_gain=0.0`이 직접 기록되었다. 다시 말해, loop는 이제 “이 probe는 명백한 과신이었다”를 추상적으로 느끼는 것이 아니라, 구조화된 숫자로 남길 수 있게 되었다.

아직도 발전 여지는 많다. 현재 belief revision은 parent/child belief JSON 비교를 기반으로 한 heuristic score이지, 진짜 posterior KL divergence는 아니다. 또 hypothesis pruning 역시 status와 존재 여부를 기준으로 보는 단순한 근사다. 그러나 이 단계의 목적은 그보다 앞선다. 지금 필요한 것은 world-modeling loop가 적어도 “나는 얼마나 배웠고, 얼마나 놀랐는가”를 trace 차원에서 스스로 적어두게 만드는 것이다. 그 구조가 생기면 나중에 더 정교한 Bayesian-ish metrics나 learned evaluator를 얹는 것이 훨씬 쉬워진다.

정리하면, 이번 단계는 unattended outer loop를 단순 scheduler에서 **자기 회고가 가능한 epistemic process**로 옮기는 작업이었다. 이제 episode 하나하나는 action log를 넘어서, expectation, outcome, surprise, revision이 함께 기록된 실험 기록이 된다. 이건 다음 단계인 belief-ledger diff 강화, hypothesis-pruning-aware distillation, and planner calibration의 기반이다.
