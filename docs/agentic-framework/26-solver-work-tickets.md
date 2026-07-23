<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 26. Solver Work Tickets

이 문서는 [`25-solver-priority-handoff.md`](/Users/sundong/Documents/arc-agi-3/docs/agentic-framework/25-solver-priority-handoff.md)에서 정리한 solver 우선순위 세 개를, 실제 구현 가능한 작업 티켓 단위로 잘게 분해한 것이다. 목적은 단순하다. “perception을 강화한다”, “belief revision을 잘하게 만든다”, “subgoal planning을 넣는다” 같은 큰 문장은 방향을 잡는 데는 좋지만, 바로 코드로 옮기기에는 너무 넓다. 따라서 여기서는 각 우선순위를 파일 단위, 기능 단위, 테스트 단위로 내려서, Claude가 읽고 스스로 다음 작업을 고르기 쉽도록 만든다.

이 문서는 새로운 아키텍처 제안서가 아니다. 이미 합의된 방향을 구현 티켓으로 번역한 실행 문서에 가깝다. 따라서 각 티켓에는 가능한 한 다음 요소를 포함한다. 무엇을 바꿔야 하는지, 어느 파일이 주 대상인지, 완료 기준이 무엇인지, 그리고 GPT scaffold 쪽에서 어떤 seam 지원이 필요한지다.

## Priority 1. Perception / Object Persistence

이 우선순위의 핵심은 “scene을 object 집합으로 본다”에서 한 단계 더 나아가, “같은 object가 step을 거치며 어떻게 유지되고 바뀌는지 추적한다”로 옮겨가는 것이다. solve-loop가 매 step을 새 픽셀 배열처럼 다시 읽으면 hypothesis가 잘 쌓이지 않는다. 반대로 object persistence가 생기면 controllable object, goal candidate, blocker, clickable target을 훨씬 더 안정적으로 다룰 수 있다.

### Ticket P1-1. Persistent Object Identity

- 권장 담당: Claude 주도
- 주 파일: [`perception.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/perception.py), 필요 시 [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py)
- 목표: step `t`와 `t+1` 사이에서 “같은 object”를 연결할 수 있는 persistent id 또는 tracking key를 부여한다.
- 구현 아이디어:
  - 색, bounding box, 면적, 중심 좌표, shape fingerprint를 이용한 matching heuristic을 만든다.
  - 완벽한 tracking이 아니어도 좋으니, 같은 object가 유지/이동/분할/소멸 중 어느 쪽인지 분류 가능해야 한다.
  - 새로 생긴 object와 사라진 object를 명시적으로 구분한다.
- 완료 기준:
  - perception 결과에 object id가 안정적으로 포함된다.
  - 연속 step diff에서 “어떤 object가 영향을 받았는가”를 object id 기준으로 설명할 수 있다.
  - 최소 unit test 또는 fixture 테스트가 생긴다.

### Ticket P1-2. Controllable / Goal / Blocker Candidate Scoring

- 권장 담당: Claude 주도
- 주 파일: [`perception.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/perception.py)
- 목표: object summary에 `controllable_candidate`, `goal_candidate`, `blocker_candidate`, `click_candidate` 같은 role score를 넣는다.
- 구현 아이디어:
  - 최근 action 이후 실제로 변한 object는 controllable 가능성이 올라간다.
  - 도달 대상처럼 보이는 isolated target, special color cluster, boundary-near marker 등은 goal-like score를 준다.
  - path를 막는 물체, 충돌 후 변화가 일어나는 물체는 blocker score를 준다.
  - `ACTION6`와 함께 자주 바뀌는 위치는 click candidate로 반영한다.
- 완료 기준:
  - object summary에 역할 점수 필드가 추가된다.
  - solve-loop나 belief에서 이 역할 점수를 참조하는 첫 wiring이 생긴다.

### Ticket P1-3. Relation Graph Stabilization

- 권장 담당: Claude 주도
- 주 파일: [`perception.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/perception.py)
- 목표: object 간 관계를 좀 더 명시적인 relation graph로 만든다.
- 구현 아이디어:
  - adjacency, containment, nearest-neighbor, line-of-sight, axis alignment, same-color group 같은 관계를 relation edge로 만든다.
  - solver가 “이 object는 저 object를 향해 이동하는가”, “이 object를 치면 저 group이 변하는가”를 reasoning할 수 있는 기반을 만든다.
- 완료 기준:
  - relation graph 또는 relation summary가 perception 결과에 포함된다.
  - 최소 1개 이상의 hypothesis가 relation graph를 직접 참조한다.

### Ticket P1-4. Perception Regression Fixtures

- 권장 담당: Claude 주도, GPT 보조 가능
- 주 파일: [`tests/unit/`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/tests/unit)
- 목표: perception이 좋아졌는지 확인할 고정 fixture 테스트를 만든다.
- 구현 아이디어:
  - `sk48`, `sp80` 등 대표 step pair를 fixture로 고른다.
  - “object count가 최소한 이 정도는 유지되어야 한다”, “controllable candidate가 비어 있지 않아야 한다” 같은 약한 불변식을 둔다.
- 완료 기준:
  - perception 변경 후 회귀 여부를 빠르게 확인할 test file이 생긴다.

## Priority 2. Belief Revision Wiring

이 우선순위의 핵심은 surprise를 “로그 메시지”가 아니라 “belief state를 바꾸는 사건”으로 만드는 것이다. 실제로 solver가 나아지려면, 틀린 예측은 가설을 죽이고, 맞은 예측은 confidence를 올리고, 애매한 예측은 probe 방향을 바꿔야 한다.

### Ticket B2-1. Hypothesis Pruning Rules

- 권장 담당: Claude 주도
- 주 파일: [`surprise_auditor.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/surprise_auditor.py), [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py)
- 목표: failed prediction 이후 어떤 hypothesis를 얼마나 깎을지 규칙화한다.
- 구현 아이디어:
  - predicted affected object와 actual affected object가 다르면 관련 hypothesis confidence 감소
  - expected action semantics와 실제 결과가 크게 어긋나면 semantics hypothesis status를 `weakened` 또는 `rejected`로 전환
  - repeated surprise가 누적되면 motif confidence까지 내려간다.
- 완료 기준:
  - surprise 이후 belief ledger의 hypothesis confidence가 실제로 바뀐다.
  - 그 변화가 trace나 belief artifact에 구조적으로 남는다.

### Ticket B2-2. Action Semantics Confidence Update

- 권장 담당: Claude 주도
- 주 파일: [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py), [`bootstrap_reasoner.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/bootstrap_reasoner.py)
- 목표: `ACTION1~ACTION7`에 대한 의미 추정이 누적 evidence로 업데이트되게 만든다.
- 구현 아이디어:
  - 반복적으로 비슷한 change를 일으키는 action은 semantics confidence를 올린다.
  - noop 또는 unrelated diff가 반복되면 semantics confidence를 낮춘다.
  - reversible pair나 click-target specificity 같은 구조적 signal을 semantics 메모에 반영한다.
- 완료 기준:
  - action semantics가 static bootstrap 설명이 아니라 step을 거치며 진화한다.
  - next probe나 instrumental action choice가 이 confidence를 참조한다.

### Ticket B2-3. Belief Diff Export

- 권장 담당: Claude 주도, GPT 보조
- 주 파일: [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py), 필요 시 GPT 쪽 [`schemas.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/schemas.py), [`memory.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/memory.py)
- 목표: “무엇이 바뀌었는지”를 belief diff 형태로 구조화한다.
- 구현 아이디어:
  - hypothesis added / weakened / rejected / strengthened count
  - motif confidence delta
  - goal belief delta
  - action semantics delta
- 완료 기준:
  - belief artifact나 trace에 diff block이 추가된다.
  - GPT 쪽 queue policy / dataset export가 이 diff를 읽을 수 있다.

### Ticket B2-4. Revision-Aware Probe Selection

- 권장 담당: Claude 주도
- 주 파일: [`experiment_designer.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/experiment_designer.py), [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py)
- 목표: belief revision 결과가 다음 probe를 실제로 바꾸게 한다.
- 구현 아이디어:
  - recently rejected hypothesis를 가장 빨리 다시 가르는 probe는 피한다.
  - weakened semantics를 재검증하는 probe는 우선순위를 올린다.
  - strong confirmed motif와 충돌하는 exploratory probe는 줄인다.
- 완료 기준:
  - surprise 이후 chosen probe distribution이 달라진다.
  - regression test나 trace 예시에서 그 변화가 드러난다.

## Priority 3. Subgoal Planning

이 우선순위의 핵심은 epistemic probing 이후 “무엇을 달성해야 하는가”를 더 구체적으로 만드는 것이다. solver가 언제까지나 probe만 잘해선 점수를 못 낸다. 어느 순간부터는 중간 목표를 만들고, 그 목표를 달성하는 작은 plan을 실행해야 한다.

### Ticket S3-1. Subgoal Schema

- 권장 담당: Claude 주도
- 주 파일: [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py), 필요 시 [`schemas.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/schemas.py)
- 목표: solver 내부에서 다룰 subgoal 구조를 정의한다.
- 구현 아이디어:
  - `subgoal_type`, `target_object_id`, `target_region`, `priority`, `confidence`, `rationale` 정도를 가진다.
  - 예시 subgoal: `reach_goal_region`, `clear_path`, `activate_switch`, `align_with_target`, `test_click_target`
- 완료 기준:
  - solve-loop가 phase가 instrumental일 때 active subgoal을 갖는다.

### Ticket S3-2. Candidate Subgoal Generation

- 권장 담당: Claude 주도
- 주 파일: [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py)
- 목표: 현재 belief와 perception에서 2~3개의 후보 subgoal을 생성한다.
- 구현 아이디어:
  - controllable object와 goal-like object가 있으면 `reach` 류 subgoal 생성
  - blocker가 있으면 `clear_path` subgoal 생성
  - click target이 의심되면 `activate` 또는 `test_click_target` subgoal 생성
- 완료 기준:
  - instrumental phase에서 raw action 대신 subgoal shortlist가 먼저 만들어진다.

### Ticket S3-3. Subgoal-to-Action Outline

- 권장 담당: Claude 주도
- 주 파일: [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py), 필요 시 [`experiment_designer.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/experiment_designer.py)
- 목표: subgoal을 2~5 step 수준의 action outline으로 내린다.
- 구현 아이디어:
  - 예: `clear_path`면 blocker 쪽 probe/action sequence
  - 예: `reach_goal_region`이면 navigation bias sequence
  - 예: `activate_switch`면 click or contact 유도 sequence
- 완료 기준:
  - decision record 또는 trace에 “현재 subgoal”과 “action outline”이 남는다.
  - plan failure 시 recovery 전환 이유가 더 선명해진다.

### Ticket S3-4. Subgoal Regression / Success Criteria

- 권장 담당: Claude 주도, GPT 보조 가능
- 주 파일: [`tests/unit/`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/tests/unit)
- 목표: subgoal planner가 최소한 “무의미한 action spam”보다는 낫다는 걸 확인할 테스트를 만든다.
- 구현 아이디어:
  - fake belief/perception fixture를 넣고, 예상되는 subgoal type이 생성되는지 확인
  - progress history가 있을 때 instrumental phase에서 subgoal이 비어 있지 않은지 확인
- 완료 기준:
  - subgoal generation / selection의 최소 regression test가 생긴다.

## GPT Integration Tickets

위 세 우선순위는 기본적으로 Claude가 주도하는 것이 자연스럽지만, GPT가 바로 받아줄 seam 작업도 미리 적어두는 것이 좋다. 아래 티켓들은 solver core가 아니라 integration/support 성격이다.

### Ticket G-1. Belief Diff Trace Support

- 권장 담당: GPT
- 주 파일: [`schemas.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/schemas.py), [`memory.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/memory.py), [`agentic_trace_enricher.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_trace_enricher.py)
- 목표: Claude가 belief diff를 내보내기 시작하면, 그것을 trace/dataset/export 쪽에서 바로 받도록 만든다.

### Ticket G-2. Solver Episode Scheduling Hooks

- 권장 담당: GPT
- 주 파일: [`agentic_supervisor.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_supervisor.py), [`agentic_night_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_night_loop.py), [`agentic_queue_policy.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_queue_policy.py)
- 목표: solver episode가 더 풍부한 phase/subgoal/belief info를 남기면, 그걸 queue policy가 읽어 attention을 조절하게 만든다.

### Ticket G-3. Distillation Export Upgrade

- 권장 담당: GPT
- 주 파일: [`convert_episodes_to_sft.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/convert_episodes_to_sft.py) 또는 후속 export 스크립트
- 목표: improved solver episode를 SFT/trajectory dataset으로 더 잘 내보낸다.

## 운영 원칙

이 티켓들의 핵심은 “큰 철학을 바로 코드로 쓰기 쉬운 단위로 바꾸는 것”이다. 실제 진행 시에는 세 우선순위를 동시에 다루기보다, 다음 순서를 권장한다.

1. `P1-1`, `P1-2`
2. `B2-1`, `B2-2`
3. `S3-1`, `S3-2`
4. 그다음에야 `B2-3`, `B2-4`, `S3-3`, `S3-4`

즉 먼저 더 잘 보고, 그다음 더 잘 믿음을 고치고, 마지막에 더 잘 계획하게 만드는 순서다. 이 순서를 어기면 subgoal planner를 넣어도 perception과 belief가 약해서 금방 흔들릴 가능성이 높다.
