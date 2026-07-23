<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 33. World Model Export and Distillation Design

이 문서는 Claude가 solver 내부에 추가한 `DynamicsRule`, `InteractionRule`, `Region`, `GoalSurface.internal_pattern`를 shared artifact, unattended scheduling, SFT distillation까지 일관되게 흐르게 만들기 위한 구현 설계안이다. 여기서 핵심 원칙은 두 가지다. 첫째, solver 내부의 rich structure를 그대로 증발시키지 않는다. 둘째, trace와 SFT prompt는 여전히 compact해야 하므로 raw structure 전체를 dump하지 않고 top-k summary로만 내린다.

## 목표

현재 solver는 step마다 `belief_state` 안에 richer world model을 생성하기 시작했다. 이건 아주 좋은 변화다. 하지만 지금 상태로는 이 구조가 `belief.json`에만 안정적으로 남고, trace / night-loop / SFT export 쪽에서는 거의 읽히지 않는다. 따라서 목표는 다음 네 가지다.

1. world-model 구조를 shared schema에서 canonical하게 표현한다.
2. trace row가 compact summary를 통해 dynamics / interaction / region / reference pattern을 함께 담게 한다.
3. SFT export가 small model에게 유용한 world-model summary를 prompt에 포함하게 한다.
4. night-loop / queue-policy가 “새 rule 발견”, “새 interaction 발견”, “region 구조 안정화”를 epistemic gain signal로 읽게 한다.

## 현재 상태

현재 기준으로 `DynamicsRule`, `InteractionRule`, `Region`은 shared schema에 이미 존재하고, `solve_loop.py`도 그것들을 belief ledger에 채운다. 따라서 `belief.json`은 이미 이 world-model 구조를 담는다. 반면 `TrajectoryRecord`에는 이 구조를 위한 slot이 없고, `convert_episodes_to_sft.py`도 이를 formatter로 내려주지 않는다. `GoalSurface.internal_pattern`는 perception local structure에는 있지만 shared schema로는 아직 빠져 있으므로, solver perception과 export 사이의 가장 큰 단절 지점이다.

## 설계 원칙

첫째, trace에는 **summary만** 넣는다. DynamicsRule 20개, InteractionRule 20개를 raw JSON으로 넣으면 `episode_trace.jsonl`이 곧바로 비대해지고 queue policy가 읽기 어려워진다. trace는 compact telemetry여야 한다. 따라서 trace는 top-k summary 라인만 남기고, full structure는 `belief.json`에만 둔다.

둘째, SFT prompt에도 **summary만** 넣는다. 작은 모델에게 필요한 것은 full rule table보다 “지금 어떤 action rule이 꽤 확실한지”, “어떤 interaction이 핵심인지”, “공간 구조가 어떻게 보이는지”, “reference pattern이 무엇인지”다. 따라서 SFT에는 top-2 또는 top-3 정도의 compact line이 적절하다.

셋째, schema 추가는 solver 표현과 최대한 맞닿게 하되, GPT export 층이 임의로 새로운 semantics를 발명하지 않는다. canonical meaning은 solver 쪽에서 정하고, export는 그 meaning을 압축해 전달하는 역할만 맡는다.

## 제안 1. Shared schema 보강

### 1a. `ReferencePatternSummary`

가장 먼저 추가해야 할 shared 구조는 reference / goal surface content다. 추천 shape는 다음과 같다.

- `surface_id: str`
- `kind: Literal["reference_box", "target_marker", "energy_bar", "unknown"]`
- `row_min`, `row_max`, `col_min`, `col_max`
- `pattern_rows: list[str] = []`
- `pattern_description: str = ""`
- `confidence: float = 0.5`

여기서 `pattern_rows`는 raw 2D int array 대신 compact row-string으로 두는 편이 낫다. 예를 들어 `["2222", "2002", "2002", "2222"]`처럼 아주 작은 패턴만 허용하고, 큰 패턴은 `pattern_description`으로만 남기면 된다. solver perception 내부에서 쓰는 full `internal_pattern: list[list[int]]`는 local detail로 유지해도 좋지만, shared layer로는 compact summary를 내리는 것이 낫다.

### 1b. 중기 후보 구조

지금 당장 필수는 아니지만 다음 라운드에서 고려할 수 있는 구조는 `AffordanceBelief`와 `PredictionRecord`다.

`AffordanceBelief`는 object/region에 대해 `pushable`, `clickable`, `traversable`, `connector`, `collectible`, `triggerable` 같은 affordance를 confidence와 함께 유지하는 구조다. role score보다 한 단계 semantic하게 올라간 표현이므로 subgoal planner와 experiment designer를 narrative 쪽 이상형에 더 가깝게 만들 수 있다.

`PredictionRecord`는 action 직전에 world model이 무엇을 기대했는가를 구조화한다. expected affected pids, expected region, expected interaction, expected goal progress, source(module)를 담으면 `prediction -> outcome -> surprise -> revision` 체인이 artifact에서 더 완전해진다.

## 제안 2. Trace summary 확장

`TrajectoryRecord`에는 raw lists 대신 compact summary slot을 추가한다. 추천 필드는 다음과 같다.

- `dynamics_rule_summary: list[str]`
- `interaction_rule_summary: list[str]`
- `region_summary: list[str]`
- `reference_pattern_summary: str | None`

생성 규칙은 아래처럼 보수적으로 한다.

- dynamics rules: confidence 높은 상위 2개
- interaction rules: confidence 높은 상위 2개
- regions: role이 명확한 상위 3개 (`play_area`, `barrier`, `reference`, `energy_display`)
- reference pattern: 하나만

예시:

`Dynamics: ACTION1->move ctrl up ~5 (c0.95,v6) | ACTION3->move ctrl left ~5 (c0.87,v4)`

`Interactions: P_ctrl push P_box (c0.71) | P_switch trigger P_door (c0.63)`

`Regions: play_area[r8-49,c6-55,trv=1] | barrier[v5] | energy_display[v11]`

`Reference pattern: 4x4 2222/2002/2002/2222 | hollow square target`

이 summary는 `TrajectoryCurator`가 `BeliefLedger`를 읽어 생성하는 편이 가장 자연스럽다. solver가 raw rule을 만들고, curator가 top-k summary를 뽑는 구조가 역할 분리도 깔끔하다.

## 제안 3. SFT compact state 포맷

`convert_episodes_to_sft.py`의 `build_compact_state(...)`에는 다음 라인을 추가하는 것이 좋다.

1. `Dynamics: ...`
2. `Interactions: ...`
3. `Regions: ...`
4. `Reference pattern: ...`

### 권장 formatter

`Dynamics: ACTION1->move ctrl up ~5 (c0.95,v6) | ACTION5->toggle target (c0.62,v3)`

여기서 `(c0.95,v6)`는 confidence 0.95, verified 6회를 뜻한다.

`Interactions: P_ctrl push P_box (c0.71) | P_switch trigger P_gate (c0.63)`

`Regions: play_area[r8-49,c6-55,trv=1] | barrier[v5] | reference[v2]`

`Reference pattern: 4x4 2222/2002/2002/2222 | hollow square target`

### 토큰 예산 규칙

- dynamics: top 2
- interactions: top 2
- regions: top 3
- reference pattern: 최대 1
- pattern rows는 8x8 이하만 허용, 그 이상은 description만 사용

이렇게 하면 Qwen 0.8B / 4B 쪽 compact state budget을 크게 깨지 않으면서도, 작은 모델이 “이 world model이 현재 무엇을 알고 있는가”를 훨씬 직접적으로 읽을 수 있다.

## 제안 4. Night-loop / queue-policy signal

현재 outer loop는 belief revision, actual information gain, phase 같은 신호를 주로 읽는다. 여기에 world-model-specific novelty를 추가하면 epistemic scheduling이 훨씬 좋아진다. 추천 signal은 아래와 같다.

- `new_dynamics_rules_count`
- `new_interaction_rules_count`
- `region_count_delta`
- `reference_pattern_changed: bool`
- `stable_region_roles_count`

이 값은 `agentic_episode_metrics.py`에서 parent-child episode 비교로 계산하면 된다. 예를 들어 이전 episode에는 dynamics rule이 1개였는데 이번 episode에서 3개로 늘었으면, 이것은 strong epistemic gain이다. 반대로 rule count가 늘지 않고 region도 그대로이며 surprise도 낮다면, 같은 family의 reprobe를 계속 밀 이유는 줄어든다.

`agentic_queue_policy.py`에서는 이를 다음처럼 읽는 것이 자연스럽다.

- `new_dynamics_rules_count > 0` 이면 epistemic follow-up 유지
- `new_interaction_rules_count > 0` 이면 같은 object pair 관련 probe를 조금 더 살려둠
- `regions`가 안정되고 `reference_pattern`까지 확보되면 instrumental push 가점
- `reference_pattern_changed`가 발생하면 recovery보다 epistemic re-interpretation 우선

즉 outer loop가 단순 revision-aware를 넘어 **rule-discovery-aware scheduler**가 되는 것이다.

## 권장 구현 순서

1. Claude가 `ReferencePatternSummary` canonical shape를 정한다.
2. GPT가 `TrajectoryRecord` summary field와 `TrajectoryCurator` summary builder를 추가한다.
3. GPT가 `convert_episodes_to_sft.py`에 `Dynamics / Interactions / Regions / Reference pattern` compact formatter를 추가한다.
4. GPT가 `agentic_episode_metrics.py`와 `agentic_queue_policy.py`에 rule/region novelty signal을 연결한다.
5. 마지막으로 regression test를 추가한다.

## 테스트 기준

최소 회귀 기준은 다음과 같다.

- fresh episode 한 개를 돌렸을 때 `belief.json`에 `dynamics_rules`, `interaction_rules`, `regions`가 존재한다.
- 같은 episode의 `episode_trace.jsonl`에 top-k summary가 기록된다.
- `convert_episodes_to_sft.py` 출력에 `Dynamics:`, `Interactions:`, `Regions:` 라인이 생긴다.
- small fixture에서 `reference_box`가 있을 경우 `Reference pattern:` 라인이 생긴다.
- episode metrics가 새 rule discovery를 actual information gain surrogate에 반영한다.

## 분업 제안

안전한 분업은 다음과 같다.

- Claude 담당:
  - `ReferencePatternSummary` canonical shape 결정
  - solver perception에서 reference / affordance semantics의 의미 정리
- GPT 담당:
  - trace summary slot
  - SFT compact formatter
  - queue-policy / metrics wiring
  - regression test and artifact verification

이 구도로 가면 solver 내부 표현과 export 표현이 충돌하지 않고, 동시에 새 world-model 구조가 unattended loop와 distillation dataset까지 자연스럽게 이어질 수 있다.
