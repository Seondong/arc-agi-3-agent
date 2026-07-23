<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 27. Solve Loop Night Loop Integration

이번 단계의 목적은 간단했다. 앞서 `solve_loop -> supervisor` 브리지는 만들어졌지만, bounded night loop 관점에서는 아직 한 가지 중요한 구멍이 있었다. queue item이 같은 `game_id`와 같은 `actions`를 갖고 있으면, 그것이 `bootstrap` 실행인지 `solve_loop` 실행인지 구분되지 않은 채 중복으로 취급될 수 있었다. 즉 “같은 action prefix지만 다른 runner”라는 의미 차이가 queue identity와 orchestration 계층에서 충분히 드러나지 않았다.

이 문제를 해결하기 위해 먼저 `queue_signature`를 강화했다. 이제 signature는 단순히 `game_id + actions`만 보지 않고, `runner`와 solve-loop의 경우 `max_steps`까지 반영한다. 그 결과 같은 `["RESET"]` prefix라도 `bootstrap` seed episode와 `solve_loop` episode는 서로 다른 queue item으로 살아남을 수 있다. 이는 단순 기술적 수정처럼 보이지만, 실제로는 매우 중요하다. 앞으로 night loop는 “같은 게임에 대해 bootstrap probing을 먼저 하고, solver run을 따로 돌린다”는 운영 전략을 표현할 수 있어야 하기 때문이다.

또한 `agentic_night_loop.py`가 supervisor를 호출할 때 `--solver-wrapper-path`를 명시적으로 전달하도록 바꿨다. 이전에는 night loop가 supervisor를 실행할 수는 있었지만, solve-loop runner를 위한 wrapper path가 build path에 직접 드러나지 않았다. 이제는 orchestrator가 supervisor를 부를 때 harness path와 solver wrapper path를 함께 넘기므로, bootstrap item과 solve-loop item이 한 queue 안에 섞여 있어도 supervisor가 어느 runner를 어떻게 실행해야 하는지 더 명시적으로 알 수 있다.

가시성도 같이 보강했다. queue policy assessment와 round trace에는 이제 `runner`와 `max_steps`가 함께 남는다. 덕분에 night loop trace를 읽을 때 “왜 이 item이 선택되었는가”뿐 아니라 “이 item이 bootstrap probing이었는지, solve-loop attempt였는지”까지 한 번에 해석할 수 있다. 이것은 이후 mixed queue scheduling을 튜닝할 때 중요한 관찰 포인트가 된다.

작은 dry-run smoke도 수행했다. 같은 `sk48`와 같은 `["RESET"]` prefix를 공유하지만 `runner`가 다른 두 item, 즉 하나는 `bootstrap`, 다른 하나는 `solve_loop(max_steps=12)`인 seed queue를 만들고, 1라운드 night loop를 `--dry-run`으로 돌렸다. 결과는 기대한 대로였다. 두 item 모두 batch에 살아남았고, `night_trace.jsonl`의 `selected_items`에도 둘 다 별개 항목으로 기록되었다. 이 smoke는 우리가 의도한 통합이 실제로 작동한다는 것을 보여준다. 즉 이제 night loop는 “같은 prefix지만 다른 runner”를 충돌 없이 함께 다룰 수 있다.

이 단계의 의미는 구조적이다. 지금부터는 outer loop가 bootstrap episode만 돌리는 시스템이 아니라, solver episode도 같은 attention policy 안으로 서서히 끌어들일 수 있는 시스템이 되었다. 아직 queue policy가 bootstrap과 solve-loop의 상대적 우선순위를 정교하게 다루는 수준까지는 아니지만, 적어도 그 차이를 표현할 수 있는 identity와 실행 경로는 마련되었다. 이것은 향후 Claude가 perception, belief revision, subgoal planning을 개선했을 때, 그 solver 결과를 unattended night loop 안으로 더 자연스럽게 흡수하는 기반이 된다.
