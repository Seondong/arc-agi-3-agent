<!-- [Mar 30] Created by SD with GPT-5.4. -->
# Recovery Cool-Off And Adaptive Attention

이번 단계에서는 phase-aware scheduling을 한 단계 더 구조화했다. 이전 단계에서는 queue policy가 `expected_mode`, 최근 `resolved_mode`, 그리고 progress/recovery history를 점수에 반영하도록 만들었다. 이것만으로도 꽤 유용했지만, 여전히 selection은 본질적으로 “점수가 높으면 고른다”는 틀에 머물러 있었다. ARC-AGI-3처럼 온라인 적응이 중요한 환경에서는 때때로 점수 이상의 scheduling rule이 필요하다. 특히 recovery 직후와 progress 직후는, 단순 가점/감점만으로는 부족한 경우가 있다.

첫 번째로 들어간 규칙은 `recovery cool-off`다. 최근 resolved mode가 `recovery`였고, 같은 게임에 대해 `epistemic` 또는 `recovery` 성격의 follow-up가 이미 pending queue 안에 존재한다면, solve-oriented `instrumental` item은 한 라운드 뒤로 미룬다. 이것은 단순한 penalty가 아니라 selection 단계의 구조적 defer다. 의도는 분명하다. plan failure나 severe surprise 직후에는 인간도 보통 다시 한 번 상태를 확인하고, 잘못된 가설을 좁히고, action semantics를 재점검한다. 그런데 scheduler가 숫자상 높은 `expected_information_gain`만 보고 solve attempt를 다시 뽑아버리면, recovery라는 상위 control signal이 무력화된다. 따라서 recovery 직후에는 적어도 한 번은 re-probe가 먼저 오도록 만드는 편이 더 인간적인 적응 루프에 가깝다.

두 번째로 들어간 규칙은 `adaptive per-game attention`이다. 최근 resolved mode가 `instrumental`이고, 실제로 `best_levels > 0` 같은 progress가 있었던 게임은 같은 라운드에서 더 많은 attention을 받아도 된다. 이를 위해 game별 batch cap을 고정값으로만 보지 않고, history에 따라 동적으로 늘릴 수 있게 했다. 현재 정책은 보수적으로 설계되어 있다. recovery 직후인 게임은 cap을 1로 낮춰서 과도한 parallel follow-up를 막고, instrumental progress가 있었던 게임은 cap을 최소 2까지 늘려서 같은 round에서 두 개의 solve-oriented branch를 더 볼 수 있게 한다. 이 규칙은 “지금 momentum이 붙은 게임을 조금 더 밀어보자”는 직관을 코드로 옮긴 것이다.

이 두 규칙은 서로 상반되지 않는다. recovery cool-off는 실패 직후의 과속을 막는 안전장치이고, adaptive attention은 progress가 붙은 게임에 더 많은 compute를 주는 가속 장치다. 하나는 brake이고 하나는 throttle에 가깝다. 둘 다 phase history를 scheduler의 구조적 규칙으로 올린다는 점에서 중요하다.

이번 단계에서는 이를 테스트로도 고정했다. 첫 번째 테스트는 recovery history가 있는 게임에서, batch size와 per-game cap이 충분히 커도 instrumental item이 한 라운드 defer되는지를 확인한다. 두 번째 테스트는 instrumental progress가 있었던 게임에서, 기본 `max_items_per_game=1`이어도 adaptive cap이 적용되어 같은 게임 item 두 개가 batch에 들어갈 수 있는지를 확인한다. 이 테스트들은 scheduler가 이제 단순 ranker가 아니라, phase continuity를 존중하는 bounded orchestrator가 되기 시작했음을 보여준다.

이 변화가 ARC-AGI-3 해결과 직접 연결되는 이유는 명확하다. 문제를 푼다는 것은 단지 좋은 probe를 고르는 것만이 아니라, “언제 물러서야 하고 언제 밀어붙여야 하는가”를 아는 것이다. recovery 직후에 한 번 더 살피는 것과, progress가 보일 때 한 번 더 밀어보는 것은 인간의 문제 해결에서도 매우 일반적인 패턴이다. 이번 scheduler 보강은 바로 그 패턴을 outer loop 차원에서 구현한 첫 번째 버전이라고 볼 수 있다.
