<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 18. Actual Information-Gain Calibration

`expected_information_gain`를 queue까지 전달한 것만으로는 아직 반쪽짜리였다. planner가 어떤 probe를 매우 유망하다고 예측하더라도, 실제로 실행해 보면 아무 변화도 없는 경우가 있기 때문이다. unattended loop가 길어질수록 중요한 것은 “planner가 뭐라고 말했는가”만이 아니라, “그 planner의 최근 제안들이 실제로 얼마나 많은 정보를 줬는가”이다. 그래서 이번 단계에서는 expected signal 위에 **realized information-gain surrogate**를 얹었다.

핵심 구현은 [`agentic_episode_metrics.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_episode_metrics.py)에 있다. 이 모듈은 completed episode row와 그 parent episode row를 비교해 actual information gain을 추정한다. 현재 surrogate는 완전한 정보이론량이 아니라, unattended loop에서 충분히 쓸 수 있는 구조화된 근사치다. 구체적으로는 `levels_completed` 증가, `state` 변화, `diff_summary` 안의 changed-cell 수, `available_actions` 집합 변화, object count 변화, value histogram shift, 그리고 trace의 `surprise`/`dynamics_revision` 신호를 종합해 0.0~1.0 사이 값으로 정규화한다.

이 설계의 중요한 철학은 “실제 정보획득은 parent 대비 비교에서만 말이 된다”는 점이다. root bootstrap episode는 비교 기준이 없으므로 actual gain이 없다. 반면 follow-up episode는 명확하다. 같은 game에 대해 `["RESET"]` 다음 `["RESET", "ACTION6"]`를 실행했는데 observation이 사실상 동일하다면, planner가 아무리 `expected_information_gain=0.75`라고 말했어도 realized gain은 거의 0에 가까워야 한다. 반대로 action 이후 새로운 object가 나타나거나, available action set이 바뀌거나, hypothesis를 강하게 흔드는 surprise가 관찰되면 실제 gain이 높게 잡혀야 한다.

이 actual metric은 [`agentic_queue_policy.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_queue_policy.py)에 바로 연결된다. 이제 `GameHistory`는 `recent_expected_information_gains`뿐 아니라 `recent_actual_information_gains`도 유지한다. 그리고 pending probe를 평가할 때, 가능하면 최근 actual baseline과 비교한다. 즉 현재 probe가 “최근 이 게임에서 실제로 얻었던 정보량 수준”보다 얼마나 나은지, 혹은 그보다도 못한지를 본다. actual baseline이 없을 때만 예전 expected baseline 비교로 fallback 한다.

이 변화의 의미는 꽤 크다. outer loop는 이제 planner의 자기평가를 그대로 믿지 않는다. 대신 최근 episode들의 realized gain을 통해 planner를 간접적으로 calibration한다. 예를 들어 어떤 game에서 최근 몇 개 follow-up가 모두 `NO CHANGE`를 만들었다면, history의 actual gain baseline은 낮게 유지된다. 그 상태에서 새로운 high-gain probe가 들어오면 강한 bonus를 받고, 반대로 또 하나의 애매한 probe는 쉽게 우선순위를 얻지 못한다. 이건 완벽한 self-correction은 아니지만, planner의 optimism bias를 outer loop가 일정 부분 견제하기 시작했다는 뜻이다.

실제로 `sk48` smoke run에서도 이 구조가 바로 보인다. `["RESET"]` 뒤의 `["RESET", "ACTION6"]` follow-up는 planner가 `expected_information_gain=0.75`로 평가했지만, 실제 observation에서는 `NO CHANGE`가 나왔고, history의 `recent_actual_information_gains`는 `[0.0]`이 되었다. 이건 앞으로 이어질 `["RESET", "ACTION6", ...]` 계열 follow-up들을 평가할 때 매우 중요한 baseline이 된다. 즉 loop는 이제 “ACTION6 probe는 원래 좋다고 들었다”가 아니라 “하지만 방금 이 게임에서 ACTION6 probe는 실제로 거의 아무것도 알려주지 않았다”를 기억할 수 있게 되었다.

아직 남은 한계도 분명하다. 현재 actual gain은 scene-level surrogate이지, belief-level 정확한 posterior reduction은 아니다. 다시 말해, world model 내부에서 몇 개 가설이 실제로 제거되었는지, motif confidence가 얼마나 재편되었는지까지는 아직 직접 반영되지 않는다. 그러나 이번 단계의 목적은 일단 unattended loop가 expectation과 outcome의 차이를 기억하게 만드는 것이다. 이 차이가 생기면 다음 단계는 자연스럽다. 이후에는 belief ledger diff, hypothesis pruning count, surprise magnitude 같은 더 직접적인 epistemic signal을 trajectory curator가 구조화해서 저장하도록 확장할 수 있다.

정리하면, 이번 단계에서 night loop는 planner provenance-aware, expected-value-aware 단계를 지나 **realized-value-aware** 구조로 진입했다. 이제 queue policy는 단순히 “좋아 보이는 probe”를 고르는 것이 아니라, “최근 이 게임에서 실제로 배움이 있었던 probe 패턴과 비교해 이번 probe가 얼마나 더 나은가”를 보기 시작한다. 이것이 있어야 unattended loop가 단순 반복이 아니라, 조금씩 더 덜 멍청해지는 방향으로 학습할 수 있다.
