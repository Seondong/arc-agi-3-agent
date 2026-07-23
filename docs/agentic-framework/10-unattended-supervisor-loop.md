<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 10. Unattended Supervisor Loop

## 왜 이 단계가 필요한가

이제 `Episode Memory + Belief Ledger + Trajectory Curator`의 저장소 계층이 생겼으니, 그 위에 실제로 밤새 돌릴 수 있는 바깥 루프가 필요하다. 물론 이 루프가 “완전 자율적으로 새로운 reasoning을 8시간 동안 발명한다”는 뜻은 아니다. 현재 현실적인 목표는 더 제한적이다. **작업 큐를 읽고, 각 작업을 structured episode로 남기고, 실패와 성공을 manifest로 기록하는 unattended outer loop를 만드는 것**이다.

이 단계의 의의는 크다. 그동안은 사람이 하나씩 `harness.py`를 실행하고, 콘솔을 보고, 수동으로 narrative를 쓰고, 필요한 경우 기억 구조를 덧붙였다. 이제부터는 적어도 그 바깥 반복, 즉 “작업을 꺼내고 → replay를 실행하고 → observation을 떨구고 → ledger와 trace를 bootstrap하고 → manifest를 남기는 일”은 자동화할 수 있다.

## 새로 추가한 스크립트

이번 단계에서 다음 스크립트를 추가했다.

- [`agentic_supervisor.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_supervisor.py)

이 스크립트는 JSONL work queue를 읽는다. 각 줄은 하나의 bootstrap task다. 예를 들어:

```json
{"queue_id":"q-sk48-0001","game_id":"sk48","actions":["RESET","ACTION1"],"motif_names":["threading"],"tags":["nightly","bootstrap"],"notes":["Initial upward probe."]}
```

이 task를 읽으면 supervisor는 다음을 수행한다.

1. episode 디렉토리를 만든다.
2. `harness.py --agentic-out`으로 final observation을 저장한다.
3. observation에서 heuristic bootstrap belief ledger를 만든다.
4. lightweight Theorist/Skeptic pass로 다음 probe 후보를 제안한다.
5. decision record와 compact trajectory trace를 append한다.
6. 필요하면 follow-up queue에 다음 probing task를 적재한다.
7. manifest에 `planned / started / completed / failed` 상태를 남긴다.

즉 지금의 supervisor는 아직 “완전 solver”는 아니지만, 더 이상 단순 episode factory만도 아니다. 현재는 observation 직후에 motif, goal belief, action semantic guess를 만든 뒤, 그 상태에서 다음 epistemic probe를 제안하는 얇은 reasoning pass까지 포함한다. 이 reasoning은 휴리스틱 수준이지만, 밤새 돌아가는 바깥 루프 안에서 “다음에 뭘 해볼지”를 구조적으로 남긴다는 점에서 중요하다.

## queue와 manifest의 역할

queue는 앞으로 Claude나 다른 agent가 밤 사이에 계속 쌓아 넣을 수 있는 작업 목록이다. 반면 manifest는 supervisor가 실제로 무엇을 했는지 기록하는 실행 로그다. 이 둘을 분리한 이유는, 나중에 queue generation과 execution을 서로 다른 프로세스나 agent가 맡을 수 있게 하기 위해서다.

현재 manifest에는 다음 정보가 기록된다.

- episode_id
- queue_id
- game_id
- status
- tags
- motif_names
- actions
- episode_root
- observation_path
- command
- 성공/실패 시 stdout/stderr tail
- belief/decision/trace 파일 경로
- next_probe 요약
- follow-up queue emission 여부와 payload

이 정도면 내일 아침에 무엇이 돌아갔는지 빠르게 훑어보기 충분하다.

## 사용 예시

예를 들어 아래처럼 queue를 만들어 둘 수 있다.

```bash
cat > artifacts/agentic_queue.jsonl <<'EOF'
{"queue_id":"q-sk48-0001","game_id":"sk48","actions":["RESET"],"motif_names":["threading"],"tags":["nightly","bootstrap"],"notes":["Initial scene capture."]}
{"queue_id":"q-re86-0001","game_id":"re86","actions":["RESET","ACTION1"],"motif_names":["click-semantics","navigation"],"tags":["nightly"],"notes":["Probe vertical move semantics."]}
EOF
```

그 다음 supervisor를 돌린다.

```bash
/Users/sundong/Documents/arc-agi-3/.venv312-qwen/bin/python \
  /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_supervisor.py \
  --queue /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_queue.jsonl \
  --followup-queue /Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_followups.jsonl \
  --max-followup-depth 1 \
  --python-bin /Users/sundong/Documents/arc-agi-3/.venv312-qwen/bin/python
```

이렇게 하면 episode 디렉토리와 manifest가 차곡차곡 쌓이고, 각 completed episode마다 다음 probe 후보가 follow-up queue에 한 단계 더 적재될 수 있다. `--max-followup-depth`를 둔 이유는, 아직은 bounded loop가 필요하기 때문이다. 무한히 자기 자신을 재귀적으로 증식시키는 supervisor는 지금 단계에서 바람직하지 않다.

## 이 supervisor가 아직 하지 않는 것

중요하게도, 지금 supervisor는 아직 다음 일을 하지 않는다.

- LLM을 호출해 rich natural-language Theorist/Skeptic reasoning을 생성하지 않는다.
- follow-up queue를 즉시 다시 소비하며 자기 자신을 완전 재귀적으로 돌리지는 않는다.
- 실패 task를 재계획하지 않는다.
- solve plan을 길게 전개하지 않는다.

이건 의도된 제한이다. 지금은 “밤새 도는 반복 구조”와 “얇은 belief/probe bootstrap”를 먼저 만드는 단계고, 그 위에 richer reasoning loop를 올리는 건 다음 단계다.

## 다음 단계

가장 자연스러운 다음 단계는 두 가지다.

첫째, queue item을 richer하게 만들어서 `expected_mode`, `goal_hint`, `probe_family` 같은 메타데이터를 넣는 것이다.

둘째, follow-up queue를 다시 소비하는 별도 scheduler를 만들어서, bounded depth 안에서 `observe -> infer -> suggest -> enqueue` 사이클을 계속 굴리는 것이다.

즉 현재 supervisor는 control-plane의 가장 바깥 고리를 자동화했고, 그 안에 아주 얇은 cognitive-plane bootstrap을 넣은 상태다. 이 고리가 있어야, 이후 정말로 8시간짜리 unattended workflow에 가까운 구조를 단계적으로 만들 수 있다.
