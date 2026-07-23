<!-- [Mar 30] Created by SD with GPT-5.4. -->
# Phase-Aware Queue Scheduling

이번 단계에서는 `Phase Manager`를 supervisor에 연결한 것에서 한 걸음 더 나아가, 그 결과가 실제 queue scheduling에도 영향을 주게 만들었다. 이전까지의 queue policy는 주로 freshness, stagnation, probe family diversity, expected information gain, actual information gain baseline을 기준으로 pending item을 정렬했다. 이 기준들은 모두 유효했지만, 아직 “지금 이 게임이 탐색이 필요한 상태인지, solve를 계속 밀어야 하는 상태인지, 아니면 recovery 직후라서 다시 probing으로 물러나야 하는지”를 직접 반영하지는 못했다.

ARC-AGI-3에서 이 차이는 중요하다. recovery 직후의 게임에서 solve-oriented follow-up를 곧바로 밀어붙이면, system은 방금 깨진 hypothesis 위에 다시 plan을 얹을 가능성이 높다. 반대로 어느 정도 progress가 보였고 최근 phase도 instrumental이었던 게임에 계속 epistemic probe만 던지면, world model이 이미 충분히 괜찮은데도 solve phase로 넘어가지 못하고 시간을 낭비할 수 있다. 따라서 unattended outer loop는 단순히 “정보량 높은 probe”만 좋아해서는 안 되고, “지금 어떤 종류의 probe가 phase상 맞는가”까지 함께 봐야 한다.

그래서 queue policy의 `GameHistory`에는 `recent_resolved_modes`와 `recent_phase_transition_reasons`를 추가했다. 이제 completed episode manifest를 읽을 때, 각 게임이 최근에 어떤 mode로 끝났는지와 왜 그 mode에 있었는지를 history로 유지한다. 여기서 mode는 `epistemic`, `instrumental`, `recovery`의 셋이고, reason은 `Phase Manager`가 남긴 transition explanation이다.

이 history를 바탕으로 scheduling 규칙도 조금 더 인간적인 형태가 되었다. 첫째, 최근 resolved mode가 `recovery`였다면, 같은 게임의 새로운 `epistemic` follow-up에는 보너스를 준다. 이는 사람이 실패 직후 바로 다시 solve를 강행하기보다, 무엇이 틀렸는지 한 번 더 확인하고 작은 probe를 던지는 행동과 비슷하다. 둘째, recovery 직후의 `instrumental` follow-up에는 감점을 준다. 이 감점은 “지금은 다시 해결에 들어갈 때가 아니다”라는 얇은 안전장치 역할을 한다.

반대로 최근 resolved mode가 `instrumental`이고 실제 level progress도 있었다면, 새로운 `instrumental` follow-up에는 보너스를 준다. 이 경우는 이미 solve phase가 어느 정도 맞았다는 뜻이므로, 또 한 번의 solve-oriented attempt가 더 가치 있을 수 있다. 같은 조건에서 `epistemic` follow-up는 아주 약하게 감점된다. 여기서 중요한 점은 epistemic probing 자체를 부정하는 것이 아니라, progress가 있었던 게임에서 탐색 일변도로 되돌아가는 현상을 완화하려는 것이다.

이 규칙은 expected information gain과 경쟁 관계가 아니다. 오히려 둘은 서로 보완적이다. information gain은 “이 probe가 배움에 얼마나 도움이 되는가”를 말하고, phase-aware scheduling은 “지금 이 타이밍에 이런 종류의 probe가 맞는가”를 말한다. 따라서 높은 gain이라도 recovery 직후의 solve attempt는 약간 눌리고, 적당한 gain이라도 recovery 이후의 re-probe는 더 오래 살아남을 수 있다. 이것은 단순 휴리스틱처럼 보이지만, 실제로는 control-plane의 상태를 outer loop의 scheduling으로 전달하는 첫 번째 통로다.

이번 단계에서는 이 정책을 두 개의 테스트 시나리오로 고정했다. 첫 번째는 recovery 직후 epistemic re-probe가 instrumental follow-up보다 우선되어야 하는 경우다. 두 번째는 prior progress가 있었을 때 instrumental follow-up가 epistemic probe보다 우선되어야 하는 경우다. 이 테스트들은 결국 scheduler가 단지 숫자 점수만 보는 것이 아니라, phase continuity와 failure recovery라는 더 상위의 control signal을 읽고 있음을 보장한다.

결국 이번 작업의 의미는, unattended loop가 이제 “어떤 action prefix가 더 새롭고 gain이 큰가”만 보는 것이 아니라, “이 게임은 지금 어떤 종류의 일감을 받아야 하는가”를 조금 더 이해하기 시작했다는 데 있다. 이것은 완전한 planner는 아니지만, solver로 가는 방향에서 매우 중요한 중간 단계다. 다음에는 이 resolved mode history를 단지 queue ordering에 쓰는 것을 넘어, `follow-up depth`, `per-game batch allowance`, `recovery cooling-off` 같은 더 구조적인 scheduling 규칙으로 확장할 수 있다.
