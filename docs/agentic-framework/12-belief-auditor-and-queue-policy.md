<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 12. Belief Auditor and Queue Policy

`agentic_night_loop.py`가 여러 round를 이어서 실행할 수 있게 되면서, 이제 새로운 문제가 생긴다. follow-up queue를 그냥 순서대로 다시 먹기만 하면, 루프는 길어질 수는 있어도 더 똑똑해지지는 않는다. 같은 game 안에서 비슷한 probe family를 반복하거나, 이미 본 action prefix를 메타데이터만 바꿔 다시 실행하거나, 정체된 경로를 계속 따라갈 위험이 있다. 그래서 night loop 위에는 최소한의 `Belief Auditor / Queue Policy`가 필요하다.

이번 단계에서 추가한 모듈은 [`agentic_queue_policy.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_queue_policy.py)다. 이 모듈은 아직 거대한 reasoning engine이 아니다. 대신 아주 작고 분명한 역할을 맡는다. 첫째, 이미 실행된 `(game_id, actions)` 시그니처를 기반으로 중복을 제거한다. 둘째, 이전 round들의 completed episode를 읽어서 game별 history를 구축한다. 셋째, pending queue의 각 item에 점수를 매겨서 어떤 probe를 지금 우선 실행할지 고른다.

현재 history는 매우 가벼운 형태다. 각 game에 대해 `completed_episodes`, `best_levels`, `stagnant_streak`, 최근 `probe_family`, 최근 `goal_hint` 정도만 본다. 그리고 manifest의 `observation_path`를 열어 `levels_completed`, `diff_summary`, `state`를 읽는다. 여기서 progress 판단도 아직 얇다. state가 `WON`이거나, `levels_completed`가 증가했거나, `diff_summary != INITIAL`이면 일단 progress의 신호로 본다. 반대로 이런 신호가 없으면 stagnant streak를 늘린다. 완벽한 판단은 아니지만, “같은 길에서 아무 변화도 없는 루프”를 줄이는 데는 충분하다.

pending item scoring 역시 명시적이다. fresh game이면 가점을 주고, `expected_mode == epistemic`이면 초반 unattended loop에서 유리하다고 보고 약간의 보너스를 준다. depth가 얕으면 감사와 해석이 쉬우므로 가점을 준다. 반대로 depth가 깊어질수록 점수를 깎는다. 최근에 같은 `probe_family`를 반복했다면 감점하고, 같은 `goal_hint`가 최근에 반복됐다면 또 감점한다. stagnant streak가 임계값 이상이면 추가 감점을 준다. 반대로 이전에 level progress를 보인 game이라면 다시 시도할 가치가 있으므로 약간의 보너스를 준다.

이후 `Experiment Designer`가 supervisor에 통합되면서, queue policy는 단순한 family 구분만으로는 부족해졌다. 현재 policy는 `experiment-designer-followup`를 별도로 우대한다. 이유는 명확하다. bootstrap follow-up는 주로 "아직 안 눌러본 ACTION을 눌러본다"는 수준의 probe를 의미하지만, experiment-designer follow-up는 경쟁 가설을 갈라놓기 위해 더 의도적으로 설계된 probe일 가능성이 높다. 그래서 지금은 같은 depth의 follow-up가 경쟁할 때, experiment-designer follow-up에 추가 가점을 주고, stagnation penalty도 완화한다. 즉 **정체된 game일수록 richer probe를 더 오래 살려두는 방향**으로 control-plane이 기울기 시작했다.

이 모듈이 night loop에 주는 가장 큰 변화는, 이제 batch selection이 단순 FIFO가 아니라는 점이다. loop는 먼저 pending queue를 평가하고, 각 item에 대해 `score`, `keep`, `reasons`를 만든다. 그리고 그 결과를 바탕으로 batch를 고른다. 여기서 `max_items_per_game` 제한도 걸 수 있어서, 한 round 안에서 같은 game만 너무 많이 뽑히지 않게 할 수 있다. 이건 cross-game diversity를 확보하는 데 중요하다. 여러 게임에 걸쳐 밤새 돌아가게 하려면, 특정 게임의 정체가 전체 budget을 다 잡아먹지 않도록 막아야 하기 때문이다.

또 하나 중요한 점은 이 policy가 black box가 아니라는 것이다. `agentic_night_loop.py`는 각 round의 `night_trace.jsonl`에 `queue_assessments`를 남긴다. 즉 다음 날 아침에는 단순히 “무엇이 실행되었는가”만이 아니라, “왜 그것이 선택되었고 다른 후보는 왜 밀렸는가”도 볼 수 있다. 이건 나중에 Claude의 세계모델 reasoning이나 더 강한 auditor를 붙일 때 매우 중요하다. 먼저 얇은 휴리스틱이라도, selection rationale이 외재화되어 있어야 교체와 개선이 가능하기 때문이다.

이 policy는 아직 초기 버전이다. 여전히 많은 한계가 있다. `diff_summary != INITIAL`을 progress로 보는 기준은 너무 느슨할 수 있다. 어떤 게임에서는 단순 변화가 오히려 함정일 수도 있다. 또 현재는 scene semantics를 깊게 읽지 않고, 주로 run-level metadata와 아주 얕은 observation summary만 사용한다. 그래서 장기적으로는 belief ledger 안의 motif confidence 변화, surprise frequency, object count shift, controllable-object confidence 같은 더 풍부한 신호를 policy에 집어넣어야 한다.

그럼에도 불구하고 지금 이 단계는 의미가 크다. 이제 unattended loop는 단순 반복이 아니라, 최소한 “새로운 게임을 조금 더 우선하고, 같은 경로의 헛발질은 조금 덜 하도록” 방향을 갖게 되었다. 즉 control-plane이 처음으로 `selective`해진 것이다. 이 선택성이 있어야 이후 truly adaptive outer loop, motif-aware scheduler, retry/rollback policy로 자연스럽게 이어질 수 있다.
