<!-- [Mar 31] Created by SD with GPT-5.4. -->
# World-Model Trace, SFT, and Metrics Wiring

Claude가 `schemas.py`와 `solve_loop.py`에 추가한 `DynamicsRule`, `InteractionRule`, `Region`, `ReferencePatternSummary`는 이제 solver 내부에만 머무르지 않고, trace / distillation / unattended scheduling까지 흐를 수 있는 상태가 되었다. 이번 작업의 목적은 새 world-model 구조를 raw 그대로 복제하는 것이 아니라, 각 층이 감당할 수 있는 **compact summary와 aggregate metric**으로 번역하는 것이었다.

첫 번째로 한 일은 trace wiring이다. `TrajectoryRecord`에는 이제 `dynamics_rule_summary`, `interaction_rule_summary`, `region_summary`, `reference_pattern_summary`가 들어간다. `TrajectoryCurator`는 `BeliefLedger`에서 confidence 기준 top-k rule과 salient region을 골라 한 줄 요약으로 바꾼다. 즉 `belief.json`에는 풍부한 구조가 남고, `episode_trace.jsonl`에는 빠르게 읽을 수 있는 compact view가 남는다. 이로써 trace는 여전히 가볍지만, “지금 solver가 어떤 실행 규칙과 공간 구조를 믿고 있는가”를 잃지 않게 됐다.

두 번째는 SFT export wiring이다. `convert_episodes_to_sft.py`는 기존의 object summary, role candidates, belief diff 위에 다음 줄들을 더 출력한다.

- `Dynamics: ...`
- `Interactions: ...`
- `Regions: ...`
- `Reference pattern: ...`

중요한 점은 여기서도 raw 구조를 통째로 싣지 않는다는 것이다. Dynamics는 top-2 rule만, Interactions도 top-2만, Regions는 salient top-3만, Reference pattern은 top-1만 실린다. 이것은 Qwen 같은 작은 모델에게 필요한 것이 “전체 solver 상태 dump”가 아니라 “행동을 고르는 데 직접 도움이 되는 world-model summary”이기 때문이다.

세 번째는 unattended metrics와 queue scheduling wiring이다. `agentic_episode_metrics.py`는 이제 parent belief와 current belief를 비교해 다음을 계산한다.

- `rule_discovery_score`
- `new_dynamics_rules_count`
- `new_interaction_rules_count`
- `new_region_count`
- `reference_pattern_update_count`

이 값들은 observation-only actual information gain과 별도로, “이번 episode가 world model을 얼마나 확장했는가”를 측정하는 epistemic signal이다. `agentic_trace_enricher.py`는 이 메트릭들을 `episode_metrics.json`과 manifest row에 기록한다. 이어서 `agentic_queue_policy.py`는 recent rule discovery가 높은 게임에 대해 epistemic / recovery probe를 더 우대하고, level progress가 아직 없는 상태에서 성급한 instrumental push를 조금 눌러준다. 즉 unattended loop는 이제 scene change와 belief revision뿐 아니라 **rule discovery 자체**를 attention signal로 읽는다.

이 변경으로 얻는 실질적 효과는 세 가지다. 첫째, Claude가 만든 world-model 구조가 trace에서 증발하지 않는다. 둘째, distillation dataset이 object role뿐 아니라 executable rule과 reference pattern까지 담게 된다. 셋째, night loop가 “무언가 바뀌었는가”뿐 아니라 “무언가를 배웠는가”를 더 정확히 추적할 수 있게 된다.

현재 범위는 intentionally conservative하다. `AffordanceBelief`, `PredictionRecord`, 더 정교한 region stabilization metric은 아직 넣지 않았다. 이번 단계는 새 structure를 전 파이프라인에 안전하게 흘리는 데 집중했다. 다음 단계는 이 신호들을 더 적극적으로 ব্যবহার해서 revision-aware probe selection과 subgoal execution scoring을 강화하는 일이다.
