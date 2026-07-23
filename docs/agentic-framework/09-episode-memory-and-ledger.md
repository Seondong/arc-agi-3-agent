<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 09. Episode Memory And Belief Ledger

## 왜 이 문서가 필요한가

`08-control-plane-and-cognitive-plane.md`에서 정리한 것처럼, 지금 가장 먼저 구현할 가치가 큰 것은 `Episode Memory + Belief Ledger + Trajectory Curator`다. 이유는 간단하다. 이 세 가지가 있어야 control-plane의 역할들 사이 대화와 cognitive-plane의 상태 표현이 같은 저장소 위에 모일 수 있기 때문이다. 다시 말해, 이 셋은 multi-agent solver의 첫 번째 공통 인터페이스다.

이번 단계에서 실제 코드도 이미 들어갔다. 이 문서는 그 코드가 어디에 있고, 어떤 파일을 만들고, 어떤 식으로 사용할 수 있는지를 정리해둔 메모다.

## 현재 추가된 코드 위치

새 스키마와 메모리 코드는 다음 파일들에 들어 있다.

- [`schemas.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/schemas.py)
- [`memory.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/memory.py)
- [`__init__.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/__init__.py)

또한 harness에서 최종 frame을 structured observation으로 떨굴 수 있도록 [`harness.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/harness.py)에 `--agentic-out` 옵션을 추가했다.

## 핵심 스키마

현재 정의된 주요 모델은 다음과 같다.

- `ObjectSummary`
  grid 안의 하나의 non-background object를 bounding box와 cell count 기준으로 요약한다.
- `ObservationSnapshot`
  한 step에서의 structured scene snapshot이다. `game_id`, `step_index`, `state`, `available_actions`, `diff_summary`, `value_histogram`, `objects`, `compressed_grid`, `map2d` 등을 담는다.
- `MotifBelief`
  motif 이름, confidence, evidence를 담는다.
- `HypothesisEntry`
  경쟁 가설 하나를 담는다.
- `GoalBelief`
  현재 유력한 목표 해석을 담는다.
- `BeliefLedger`
  episode 내 현재 살아 있는 motif, hypothesis, goal, action semantics 후보를 관리한다.
- `DecisionRecord`
  어떤 phase에서 어떤 action을 왜 골랐는지 기록한다.
- `TrajectoryRecord`
  distillation용 compact step record다.
- `EpisodeMetadata`
  episode 단위 메타데이터다.

## EpisodeMemoryStore

`EpisodeMemoryStore`는 structured episode 디렉토리를 만든다. 생성되면 대략 이런 구조가 된다.

```text
<root>/<episode_id>/
  episode.json
  episode_trace.jsonl
  steps/
    step_0000.observation.json
    step_0000.belief.json
    step_0000.decision.json
    ...
```

이 구조가 중요한 이유는, 나중에 Observer, Theorist, Skeptic, Executor, Recorder가 서로 다른 파일을 읽고 쓸 수 있기 때문이다. 즉 control-plane의 대화가 파일 단위로 끊기면서도, cognitive state는 episode 디렉토리 안에서 일관되게 보존된다.

## bootstrap_belief_ledger

아직 belief를 자동으로 똑똑하게 만드는 단계는 아니다. 하지만 `bootstrap_belief_ledger(...)`를 통해 observation snapshot에서 최소한의 ledger를 만들 수 있게 해두었다. 이는 narrative 기반 운영에서 특히 중요하다. 사람이 먼저 motif 후보를 적어 넣고, 그 뒤에 agent가 점진적으로 confidence와 hypothesis를 채우는 방식으로 출발할 수 있기 때문이다.

## TrajectoryCurator

`TrajectoryCurator`는 현재 observation, belief, decision을 받아 compact distillation step으로 압축한다. 지금 단계에서는 아주 화려한 요약기를 넣지 않았지만, 이미 다음 체인을 저장할 수 있다.

`state_summary -> motif_beliefs -> active_hypotheses -> action_taken -> prediction -> actual_diff -> surprise -> dynamics_revision`

이것이 앞으로 small-model distillation의 기본 형태가 된다.

## harness.py의 새 출력 경로

이제 [`harness.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/harness.py)는 아래처럼 최종 frame의 structured observation을 바로 JSON으로 저장할 수 있다.

```bash
uv run harness.py \
  --game sk48 \
  --actions '["RESET","ACTION1"]' \
  --agentic-out artifacts/agentic/sk48_step1.observation.json
```

이 파일은 `ObservationSnapshot` 포맷으로 저장된다. 즉 기존의 사람이 읽는 console 출력과, 앞으로 agent들이 읽을 structured input을 동시에 얻을 수 있다.

## 지금 이 구현의 의미

이 구현은 solver가 갑자기 강해졌다는 뜻은 아니다. 그러나 아주 중요한 전환점이다. 전에는 좋은 narrative와 좋은 철학이 있었지만, 그 철학이 저장될 상태 구조가 없었다. 이제는 최소한의 공통 상태 형식이 생겼다. 이건 나중에 어떤 role agent를 만들든 간에 계속 재사용할 수 있는 기반이 된다.

## 다음 단계

가장 자연스러운 다음 단계는 세 가지다.

첫째, Observer가 `ObservationSnapshot`을 더 풍부하게 채우도록 `Scene Canonicalizer`와 `Object Tracker`를 붙인다.

둘째, Theorist/Skeptic가 `BeliefLedger`를 실제로 읽고 쓰도록 prompt/schema를 정한다.

셋째, Executor가 `DecisionRecord`를 남기고, Recorder가 `TrajectoryCurator`를 통해 `episode_trace.jsonl`을 자동 생산하도록 연결한다.

즉 지금 추가된 코드는 framework의 완성본이 아니라, 여러 역할이 같은 episode 위에서 협업할 수 있게 만드는 첫 번째 저장소 계층이다.

