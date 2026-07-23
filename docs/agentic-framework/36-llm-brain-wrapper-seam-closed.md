<!-- [Mar 31] Created by SD with GPT-5.4. -->
# LLM Brain Wrapper Seam Closed

`35-llm-brain-handoff.md`에서 짚었던 wrapper seam을 이번 단계에서 닫았다. 핵심은 `solve_loop` 내부에 이미 들어가 있던 `llm_model`, `llm_used`, `ACTION6` coordinate path를 outer loop와 trace provenance까지 이어주는 일이었다.

먼저 `QueueItem`이 이제 `llm_model`을 들고 다닐 수 있게 되었다. 이에 따라 [`agentic_supervisor.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_supervisor.py)의 `build_solver_command(...)`는 solve-loop wrapper를 호출할 때 `--llm-model`을 실제로 전달한다. 동시에 manifest planned/completed payload에도 `llm_model`, `llm_used`, `resolved_llm_model`이 남는다. 즉 unattended queue 입장에서도 “이 solve-loop job이 어떤 LLM brain을 쓸 예정이었는가 / 실제로 썼는가”를 추적할 수 있게 되었다.

둘째, [`run_agentic_solver_job.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/run_agentic_solver_job.py)는 `--llm-model` 인자를 받아 `solve_episode(...)`까지 전달한다. result JSON에도 `llm_used`, `llm_model`이 포함되므로, supervisor가 wrapper 결과만 읽어도 provenance를 잃지 않는다.

셋째, queue dedupe도 solver brain 구성을 구분하도록 바뀌었다. [`agentic_queue_policy.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_queue_policy.py)의 `queue_signature(...)`는 이제 `runner="solve_loop"`인 경우 `llm_model`까지 signature에 포함한다. 따라서 같은 `game_id + actions + max_steps`라도 모델이 다르면 서로 다른 solve job으로 취급된다. 이건 `gpt-5.4-mini`와 다른 LLM brain 실험이 unattended loop 안에서 서로 덮어쓰지 않게 하는 최소한의 안전장치다.

넷째, trace provenance도 닫혔다. `TrajectoryRecord`에 `llm_used`, `llm_model` 필드를 추가했고, `TrajectoryCurator`와 `solve_step(...)`가 그 값을 `episode_trace.jsonl`까지 내려보낸다. 이제 per-step trace를 열어보면, 어떤 step이 heuristic branch였고 어떤 step이 LLM brain branch였는지 직접 볼 수 있다.

다섯째, `EpisodeResult`에도 `llm_used`, `llm_model`이 정식 필드로 추가되었다. 이건 wrapper가 result payload를 만들 때 필드를 안전하게 읽을 수 있게 하기 위한 변경이다. 이전에는 step log에는 `llm_used/llm_model`이 있었지만, top-level result dataclass에는 canonical slot이 없어서 wrapper seam이 불안정했다.

이 단계 이후 상태를 한 문장으로 정리하면 이렇다. `solve_loop` 단독 실행, wrapper 실행, supervisor manifest, night-loop dedupe, per-step trace까지 모두 `llm_model` provenance를 이해하는 상태가 되었다. 즉 이제 LLM brain은 solver 내부에만 꽂힌 옵션이 아니라, unattended orchestration 계층에서도 **실제로 선택 가능하고 추적 가능한 runtime mode**가 되었다.
