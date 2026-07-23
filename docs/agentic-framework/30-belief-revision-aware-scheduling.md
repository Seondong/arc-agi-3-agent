<!-- [Mar 31] Created by SD with GPT-5.4. -->
# Belief-Revision-Aware Scheduling

이번 단계에서는 unattended outer loop가 `expected_information_gain`뿐 아니라, 최근 episode가 실제로 belief를 얼마나 흔들었는지도 queue policy에서 읽도록 연결했다. 핵심 의도는 간단하다. 어떤 게임에서 최근 probe들이 가설을 많이 버리게 만들고 motif confidence를 크게 움직였다면, 아직 세계 모델이 형성 중이라는 뜻이므로 다음 attention을 다시 epistemic probing 쪽에 더 배분하는 편이 합리적이다. 반대로 belief가 아직 크게 흔들리는 상태에서 곧바로 instrumental push를 반복하면, solver는 아직 정리되지 않은 이론 위에서 조급하게 exploit하려 들 가능성이 크다.

이 연결은 두 층에서 일어났다. 먼저 `agentic_episode_metrics.py`는 trace tail에 이미 직접 기록되어 있는 `belief_revision_score`, `hypothesis_pruning_count`, `surprise_magnitude`, `belief_revision_summary`, `suggested_hypotheses`, `motif_updates`, `anchoring_alerts`를 읽어, belief ledger 비교가 불가능한 경우에도 trace-only fallback으로 revision estimate를 복구할 수 있게 되었다. 이건 solve loop가 richer revision artifact를 남기기 시작한 현재 구조와 잘 맞는다. 즉 outer loop는 더 이상 belief JSON diff만 볼 필요가 없고, solver가 스스로 요약한 epistemic movement를 바로 사용할 수 있다.

그 다음 `agentic_queue_policy.py`는 manifest history에서 `belief_revision_score`와 `hypothesis_pruning_count`를 recent baseline으로 저장한다. 이 baseline은 세 방향으로 queue scoring에 반영된다. 첫째, belief revision이 큰 게임에서는 `epistemic`과 `recovery` probe에 보너스를 준다. 둘째, level progress가 아직 없는데 belief revision이 계속 큰 상태라면 `instrumental` follow-up에는 작은 패널티를 준다. 셋째, recent pruning count가 양수인 게임은 “이 probe 계열이 실제로 가설을 줄이고 있다”는 뜻이므로 epistemic follow-up에 추가 보너스를 준다.

이 변화가 중요한 이유는 scheduler가 이제 단순히 “예상상 좋아 보이는 probe”를 고르는 수준을 넘어서기 때문이다. 이제는 “실제로 최근에 많이 배운 게임”과 “아직 이론이 불안정한 게임”을 구분할 수 있고, 그 차이를 attention policy에 반영할 수 있다. 즉 experiment designer가 주는 proposal quality와 solve loop가 남기는 revision artifact가 outer loop에서 서로 닿기 시작한 셈이다.

테스트는 두 갈래로 고정했다. 첫째, `test_agentic_episode_metrics.py`에서 belief ledger가 없어도 trace-only revision signal이 살아남는다는 걸 확인한다. 둘째, `test_agentic_night_loop.py`에서는 belief revision이 큰 recent history가 있을 때, expected gain이 조금 더 높은 instrumental item보다 epistemic reprobe가 실제로 우선 선택되고, 이유 문자열에도 revision/pruning 기반 판단이 남는다는 걸 검증한다.
