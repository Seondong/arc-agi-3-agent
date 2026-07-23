<!-- [Mar 30] Created by SD with GPT-5.4. -->
# Phase Manager Bootstrap Wiring

이번 단계의 핵심은 Claude가 만든 `Phase Manager`를 단순한 독립 모듈로 두지 않고, GPT가 관리하던 unattended outer loop에 실제로 연결하는 것이었다. 그동안 `phase_manager.py`는 테스트 가능한 상태로 존재했지만, supervisor와 night loop는 여전히 모든 episode를 사실상 `epistemic` bootstrap으로만 취급하고 있었다. 즉 control-plane 문서와 cognitive/data-plane 문서가 코드 레벨에서는 아직 완전히 만난 상태가 아니었다.

이번 wiring에서 가장 중요했던 판단은, `Phase Manager`가 보는 `actions_tested`를 그대로 `BeliefLedger.action_semantics`의 크기에 의존하게 두면 안 된다는 점이었다. bootstrap ledger는 관측 가능한 `available_actions`를 바탕으로 의미 후보를 채우기 때문에, 아직 실제로 시도하지 않은 action까지 이미 “tested”처럼 보이게 만들 수 있다. 그렇게 되면 충분한 confidence만 생겼을 때 agent가 실제 probe가 거의 없는 상태에서도 너무 빨리 `instrumental`로 승격될 위험이 있다. 이것은 phase logic 자체의 문제라기보다, Claude가 만든 phase logic과 GPT가 만든 bootstrap ledger 사이의 seam 문제였다.

그래서 supervisor에는 `evaluate_bootstrap_phase(...)`라는 얇은 phase adapter를 추가했다. 이 adapter는 queue item의 실제 action prefix와 observation의 action history를 합쳐서, 실제로 실행된 action만 순서대로 추려낸다. 그리고 phase 평가용으로는 bootstrap ledger를 복사한 뒤, `action_semantics`를 이 실제 executed prefix 기준으로 다시 제한한다. 즉 `Phase Manager`는 이제 “게임이 원래 지원하는 action 수”가 아니라 “우리가 이 episode에서 실제로 만져본 action 수”를 보고 phase를 판단하게 된다.

이 adapter는 phase의 초기 상태도 queue item의 `expected_mode`에서 받아온다. 그래서 이후 recovery나 instrumental follow-up가 queue에 들어오더라도, outer loop는 그 의도를 잃지 않고 phase를 이어서 해석할 수 있다. 현재는 아직 full recovery loop까지 닫혀 있지는 않지만, 적어도 queue가 “이 follow-up는 무슨 성격의 작업인가”를 잃어버리지 않게 되었다는 점이 중요하다.

실제 연결 결과로, supervisor는 bootstrap observation을 읽은 뒤 belief ledger를 만든 다음 바로 phase를 평가하고, 그 결과를 `belief.mode`, `DecisionRecord.mode`, trace의 `planning_mode`, follow-up item의 `expected_mode`에 반영한다. 또한 phase transition reason과 budget-aware `exploration_guidance(...)`도 decision notes와 manifest에 남긴다. 따라서 이후 scheduler나 distillation pipeline은 더 이상 “이 episode가 무슨 phase에서 나온 것인지”를 추측할 필요가 없다.

이번 단계에서 함께 추가된 테스트도 매우 중요하다. 첫 번째 테스트는 고의로 `available_actions`가 많은 관측과 과신된 hypothesis를 넣되, 실제 executed prefix는 `RESET` 하나뿐인 상황을 만든다. 이 경우 phase는 그대로 `epistemic`에 남아야 한다. 이 테스트는 supervisor-phase seam이 제대로 고쳐졌는지를 직접 검증한다. 두 번째 테스트는 실행 prefix가 충분히 풍부하고 hypothesis confidence도 높을 때, phase가 `instrumental`로 승격되는지를 확인한다. 즉 우리는 “Phase Manager가 존재한다”만 테스트한 것이 아니라, “outer loop에 연결되었을 때 올바른 증거를 보고 phase를 판단한다”를 테스트했다.

결론적으로 이번 wiring은 새로운 큰 기능을 하나 더 얹은 것이 아니라, 이미 있던 control-plane 자산을 outer loop와 안전하게 연결한 작업이다. 이 단계가 중요한 이유는, 앞으로 queue policy가 `expected_mode`, `resolved_mode`, `recovery` 힌트, `instrumental` follow-up를 실제로 다르게 취급하려면 먼저 phase가 artifact에 안정적으로 기록되어야 하기 때문이다. 즉 이번 작업은 다음 단계의 planning-aware scheduling을 위한 기반 공사에 가깝다.
