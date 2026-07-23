<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 13. Three-Game Night Loop Integration

이번 단계에서는 `agentic_supervisor.py`, `agentic_night_loop.py`, `agentic_queue_policy.py`가 실제로 함께 맞물리는지를 보기 위해, 세 개의 게임에 대한 소규모 통합 테스트를 수행했다. 목적은 대량 실행이 아니라, 지금까지 만든 바깥 루프가 **한 게임 전용 부트스트랩 장치**를 넘어, 여러 게임 사이에서 seed와 follow-up를 섞어 처리할 수 있는지를 확인하는 것이었다.

사용한 seed queue는 [`agentic_queue_three_game_integration.jsonl`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_queue_three_game_integration.jsonl) 이다. 여기에는 세 게임이 들어 있다.

- `g50t` with seeded motifs `maze-navigation`, `track-building`
- `re86` with seeded motifs `click-semantics`, `coordinate-selection`
- `sk48` with seeded motifs `threading`, `assembly`

실행은 다음과 같은 설정으로 이루어졌다.

- rounds: 3
- items-per-round: 2
- max-followup-depth: 1
- max-items-per-game: 1
- stagnation-threshold: 2

실제 산출물 루트는 [`agentic_night_loop_three_game_smoke`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_night_loop_three_game_smoke) 이고, 전체 요약은 [`night_summary.json`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_night_loop_three_game_smoke/night_summary.json), round별 의사결정 흔적은 [`night_trace.jsonl`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_night_loop_three_game_smoke/night_trace.jsonl)에 남아 있다.

결과는 다음과 같았다. 총 3라운드가 실행되었고, 6개의 episode가 completed 되었다. failed episode는 없었다. stop reason은 `no_followups_remaining`이었다. 즉 seed 3개와 depth-1 follow-up 3개를 모두 소비한 뒤 자연스럽게 멈췄다.

이 테스트에서 특히 중요한 건 **선택 순서**였다. round 0에서는 세 seed가 모두 fresh였기 때문에, batch size 2 제한 아래에서 `g50t`, `re86`가 먼저 실행되고 `sk48`은 remainder로 남았다. 여기서 핵심은 round 1이다. round 1 시작 시점의 pending queue에는 `sk48` seed와 `g50t`, `re86`의 follow-up가 있었다. 이때 queue policy는 깊이 0의 fresh seed인 `sk48`을 먼저 선택했고, 남은 slot 하나에는 `g50t`의 follow-up를 배치했다. `re86`의 follow-up는 round 2로 밀렸다. 이는 policy가 단순 FIFO가 아니라, **fresh game을 더 높은 점수로 우선하고, follow-up는 그 다음으로 다루는 방식**으로 실제 동작했음을 보여준다.

round별로 보면 흐름은 아래와 같았다.

1. round 0: `g50t RESET`, `re86 RESET`
2. round 1: `sk48 RESET`, `g50t RESET ACTION1`
3. round 2: `re86 RESET ACTION1`, `sk48 RESET ACTION1`

이 순서는 [`night_trace.jsonl`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_night_loop_three_game_smoke/night_trace.jsonl)에 그대로 남아 있다. 각 round trace에는 `selected_items`와 `queue_assessments`가 함께 기록되므로, 단순히 무엇이 실행되었는지뿐 아니라 왜 그것이 선택되었는지도 나중에 재구성할 수 있다.

follow-up 생성도 의도대로 작동했다. 예를 들어 round 0의 follow-up queue는 [`round_000/followups.jsonl`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_night_loop_three_game_smoke/rounds/round_000/followups.jsonl)에 남아 있으며, `g50t`와 `re86` 모두 `["RESET", "ACTION1"]` 형태의 depth-1 epistemic probe를 받았다. 이후 round 1에서 `sk48` seed가 처리되면서 `sk48` 역시 같은 형식의 follow-up를 생성했고, 그것이 round 2에서 소비되었다.

구조화 데이터 생산 관점에서 보면, 이번 3게임 소규모 통합 테스트는 이미 꽤 유의미하다. episode 디렉토리 기준으로 6개의 독립 episode가 생성되었고, 각 episode에는 observation, belief, decision, episode trace가 남았다. round-level 파일까지 합치면 `rounds/` 아래에 총 38개의 파일이 생성되었다. 즉 단순 성공/실패 로그가 아니라, 이후 Claude나 다른 agent가 읽을 수 있는 structured artifact corpus가 실제로 축적되기 시작한 것이다.

이 실험이 보여준 가장 중요한 사실은 두 가지다. 첫째, 현재 outer loop는 더 이상 단일 게임의 bootstrap 실험에 머물지 않고, 여러 게임에 걸친 bounded unattended workflow로 작동할 수 있다. 둘째, queue policy가 실제로 cross-game scheduling에 영향을 주기 시작했다. 아직은 휴리스틱 기반 점수이지만, 이것만으로도 “같은 game의 follow-up만 계속 추격하는 루프”를 피하고, fresh seed와 follow-up를 더 균형 있게 섞는 동작이 나왔다.

물론 한계도 분명하다. 아직 progress 판정이 `diff_summary != INITIAL` 같은 얕은 신호에 의존하고 있고, belief ledger 내부의 motif confidence 변화나 surprise frequency는 policy에 들어가지 않았다. 또한 현재는 depth 1까지만 허용했기 때문에, truly longer-horizon unattended loop를 검증한 것은 아니다. 하지만 그럼에도 불구하고 이번 통합 테스트는 “루프가 여러 게임을 넘나들며 스스로 다음 작업을 정리할 수 있다”는 첫 번째 운영 증거로 충분하다.

다음 단계는 자연스럽다. 이 3게임 hand-written seed queue를 넘어, Claude가 작성한 `harness narrative` 문서들에서 초기 motif와 첫 probe를 자동으로 읽어 **seed queue compiler**를 만드는 것이다. 그게 생기면 지금 만든 night loop는 25개 게임까지도 사람이 손으로 JSONL을 쓰지 않고 바로 돌려볼 수 있게 된다.
