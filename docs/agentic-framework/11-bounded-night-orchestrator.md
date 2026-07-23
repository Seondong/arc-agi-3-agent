<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 11. Bounded Night Orchestrator

`agentic_supervisor.py`가 생기면서 우리는 이미 `observe -> infer -> suggest -> enqueue`의 한 사이클을 자동화할 수 있게 되었다. 하지만 그 상태만으로는 아직 “밤새 일하는 루프”라고 부르기 어렵다. 여전히 사람이 한 번 supervisor를 실행하고, 그 결과로 나온 `followups.jsonl`을 다시 집어넣어 다음 round를 수동으로 시작해야 하기 때문이다. 그래서 그 위에 한 층 더 필요한 것이 bounded night orchestrator다.

이번 단계에서 추가한 스크립트는 [`agentic_night_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_night_loop.py)다. 이 스크립트의 목적은 매우 단순하다. seed queue에서 시작해, 한 round의 supervisor 실행 결과에서 나온 follow-up probe를 다시 다음 round의 pending queue로 넘기고, 이를 몇 차례 반복하는 것이다. 다만 여기서 중요한 건 “완전 자율성”보다 “bounded autonomy”다. 지금 단계에서는 자기 자신을 무한히 재귀 호출하는 루프보다, 멈춤 조건이 명확한 짧은 자율 루프가 더 중요하다.

이 orchestrator는 다음 일을 한다. 먼저 seed queue를 읽는다. 그 다음 이미 실행된 적이 있는 `(game_id, actions)` 시그니처를 기준으로 중복을 제거한다. 여기서 `queue_id`, `notes`, `tags` 같은 메타데이터는 중복 판정에 포함하지 않는다. 이유는 같은 probe path를 다른 말로 여러 번 실행하는 것을 막기 위해서다. 그런 뒤 deduplicated pending queue에서 `items-per-round`만큼의 batch를 뽑아 supervisor에 넘긴다. supervisor가 round를 끝내면 manifest와 follow-up queue를 읽고, 새로 제안된 probe를 다음 round pending으로 연결한다.

즉 이 스크립트가 자동화하는 것은 아래 루프다.

1. pending queue에서 중복 없는 batch를 고른다.
2. `agentic_supervisor.py`를 한 round 실행한다.
3. manifest와 follow-up probe를 수집한다.
4. 이미 본 action prefix는 버리고, 새로운 follow-up만 다음 round로 넘긴다.
5. round trace와 seen signatures를 영속적으로 저장한다.
6. round limit, queue exhaustion, 또는 supervisor failure가 발생하면 멈춘다.

이 구조가 중요한 이유는, 이제 artifact가 더 분명한 계층으로 쌓이기 때문이다. 각 round는 `rounds/round_000`, `rounds/round_001`처럼 자기 디렉토리를 갖고, 그 안에 입력 queue, supervisor manifest, follow-up queue, episode artifacts가 남는다. 동시에 run root에는 전체 실행을 요약하는 `night_trace.jsonl`, `night_summary.json`, `seen_signatures.json`이 남는다. 그래서 다음 날 아침에 “밤새 무엇이 돌았고, 어디서 멈췄으며, 어떤 probe family가 반복됐는지”를 한 눈에 파악할 수 있다.

예를 들어 아래처럼 실행할 수 있다.

```bash
/Users/sundong/Documents/arc-agi-3/.venv312-qwen/bin/python \
  /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_night_loop.py \
  --seed-queue /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_queue_smoke.jsonl \
  --run-root /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_night_loop_sk48 \
  --rounds 2 \
  --items-per-round 1 \
  --max-followup-depth 1 \
  --python-bin /Users/sundong/Documents/arc-agi-3/.venv312-qwen/bin/python
```

이 예시에서는 seed queue의 `RESET` probe부터 시작해서, round 0이 끝나면 supervisor가 제안한 다음 probe가 round 1의 pending queue로 이어진다. 만약 `max-followup-depth=1`이라면 그 다음엔 더 깊은 follow-up은 생성하지 않으므로 루프가 자연스럽게 멈춘다. 즉 이 orchestrator는 “자율성”을 depth와 round budget 안에 가둔 형태로 제공한다.

중요하게도, 이 스크립트는 아직 solve-oriented planning을 하지 않는다. world model을 길게 업데이트하지도 않고, failure recovery를 지능적으로 하지도 않으며, LLM이 직접 hypothesis를 장문으로 수정하지도 않는다. 현재 역할은 더 겸손하다. **밤새 여러 번의 bootstrap probe를 안전하게 쌓고, 그 흔적을 다음 단계 reasoning이 소비할 수 있게 남기는 것**이다. 하지만 이 기능은 생각보다 크다. 왜냐하면 이제부터는 Observer/Theorist/Skeptic/Recorder가 각각 round 단위 artifact를 읽고, “어느 probe family가 계속 재발했고, 어디서 hypothesis가 제자리걸음을 했는가”를 더 정교하게 분석할 수 있기 때문이다.

다음 단계는 두 갈래로 나뉜다. 하나는 이 orchestrator 안에 richer stop/retry policy를 넣는 것이다. 예를 들어 동일한 motif family에서 연속 세 번 progress가 없으면 queue family를 바꾸거나, 특정 game의 depth가 너무 깊어지면 다른 game으로 전환하는 식의 control-plane 정책이 들어갈 수 있다. 다른 하나는 supervisor와 orchestrator 사이에 lightweight Belief Auditor를 둬서, follow-up를 무조건 다 넘기는 대신 “이 probe는 정보량이 너무 낮다”거나 “이미 비슷한 evidence가 충분하다”고 판단되면 다음 round로 보내지 않게 하는 것이다.

정리하면, `agentic_night_loop.py`는 완전한 자율 해결 엔진은 아니다. 하지만 지금까지 만든 episode memory, belief ledger, trajectory curator, supervisor를 실제로 “더 오래 일하는 루프”로 엮는 첫 번째 실행 계층이다. 이 구조가 있어야 이후에 더 강한 Theorist/Skeptic reasoning, motif-aware scheduler, cross-game memory policy를 단계적으로 올릴 수 있다.
