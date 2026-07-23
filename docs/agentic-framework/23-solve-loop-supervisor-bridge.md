<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 23. Solve Loop Supervisor Bridge

이번 단계에서 중요한 변화는 Claude가 만든 `solve_loop`를 제가 만든 outer-loop scaffold가 직접 실행할 수 있게 된 것이다. 이전까지 `agentic_supervisor.py`는 기본적으로 `harness.py`를 호출해서 bootstrap episode를 만들고, 그 결과를 바탕으로 belief, decision, follow-up queue를 구성하는 역할에 머물러 있었다. 이 구조는 unattended exploration을 시작하기에는 충분했지만, 실제 solver 본체와는 아직 약하게 연결되어 있었다. 즉 “밤새 돌아가는 몸체”와 “실제로 문제를 푸는 두뇌”가 같은 queue/manifest 생태계 안에서 만나지 못하고 있었다.

이번 브리지는 그 경계를 줄인다. `QueueItem`은 이제 `runner`와 `max_steps`를 함께 들고 다닐 수 있고, `agentic_supervisor.py`는 `runner == "solve_loop"`인 항목을 만나면 `harness.py` 대신 `run_agentic_solver_job.py`를 호출한다. 이 wrapper는 Claude의 `solve_episode(...)`를 감싼 아주 얇은 어댑터로, solver가 돌고 난 뒤 episode root, trace path, episode json path, levels completed, final state, phase transitions, world model summary 같은 핵심 산출물을 하나의 compact JSON으로 정리해 supervisor에게 돌려준다.

이 구조의 장점은 단순히 “다른 파이썬 스크립트를 하나 더 실행한다”가 아니다. 더 중요한 것은 solver episode가 이제 bootstrap episode와 같은 manifest 흐름 안으로 들어온다는 점이다. night loop, queue policy, trace enricher, episode metrics가 이후에는 bootstrap artifact만이 아니라 solve-loop artifact도 같은 방식으로 바라볼 수 있게 된다. 즉 solver가 만들어낸 긴 reasoning/phase trace가 더 이상 고립된 로그가 아니라, outer-loop scheduling과 offline distillation의 입력 자산으로 흡수될 수 있는 형태가 된다.

브리지를 만들면서 같이 고친 seam도 있다. `EpisodeMemoryStore.create(...)`는 원래 내부적으로 episode id를 새로 만들었는데, `solve_loop`도 별도의 episode id를 생성하고 있었다. 그 결과 wrapper 바깥에서 보는 `EpisodeResult.episode_id`와 실제 디스크에 생긴 episode 디렉토리 이름이 어긋날 가능성이 있었다. 이 문제를 막기 위해 `EpisodeMemoryStore.create(...)`가 명시적인 `episode_id`를 받을 수 있게 만들었고, `solve_loop`는 자기 episode id를 그대로 store에 넘기도록 바꿨다. 덕분에 supervisor manifest, wrapper result JSON, 실제 `episode.json` 디렉토리가 한 episode id를 공유하게 되었다.

실제 smoke run도 수행했다. `sk48`에 대해 `runner=solve_loop`, `max_steps=5`인 queue item 하나를 supervisor로 실행했고, `manifest.jsonl`에는 `started -> completed` 두 줄이 정상적으로 쌓였다. completion row에는 `episode_id`, `episode_root`, `trace_path`, `levels_completed`, `final_state`, `phase_transitions`, `world_model_summary`, `trajectory_length`가 기록되었고, 실제 artifact도 `episodes/<episode_id>/episode.json`과 `episode_trace.jsonl` 형태로 생성되었다. 이 smoke는 solve-loop bridge가 말뿐인 설계가 아니라 실제로 queue item에서 episode artifact까지 관통한다는 것을 보여준다.

스모크에서 보인 운영상 이슈도 하나 바로 정리했다. solve-loop subprocess가 `matplotlib` 캐시 디렉토리 경고를 뿜었는데, unattended night loop 관점에서는 이런 노이즈가 장기적으로 로그를 지저분하게 만들고 import startup도 느리게 만든다. 그래서 `agentic_supervisor.py`는 subprocess 실행 시 공통 runtime env를 구성하면서 `MPLCONFIGDIR`를 repo 내부 `artifacts/mplconfig`로 고정하도록 했고, `run_agentic_solver_job.py`도 standalone 실행 시 같은 기본값을 쓰도록 맞췄다. 이는 기능 변경이라기보다, “밤새 도는 루프”에 필요한 운영 안정성을 조금 더 끌어올린 작업이다.

이 브리지가 의미하는 바는 명확하다. 지금부터는 solver와 scaffold가 별개의 줄기가 아니다. solver가 더 정교해질수록 outer loop는 더 풍부한 artifact를 얻게 되고, outer loop가 더 정교해질수록 solver episode는 더 좋은 queue/attention policy 안에서 재사용될 수 있다. 즉 이 단계는 control-plane과 cognitive-plane이 문서 수준을 넘어 실제 실행 경로에서 처음으로 맞물린 시점이라고 볼 수 있다.
