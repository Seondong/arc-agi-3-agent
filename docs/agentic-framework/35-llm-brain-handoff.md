<!-- [Mar 31] Created by SD with GPT-5.4. -->
# LLM Brain Handoff

이번 메모는 Claude가 추가한 `LLM brain` 경로를 GPT가 점검한 결과를 정리한 handoff다. 결론부터 말하면, 방향은 좋고 solver frame과도 잘 맞는다. 다만 현재 상태는 “구조는 들어갔지만 integration은 아직 덜 닫힌 상태”에 가깝다. 따라서 이 문서는 기능 자체를 되돌리자는 뜻이 아니라, Claude가 다음 수정 우선순위를 빠르게 판단할 수 있도록 현재 구조와 리스크를 요약하는 것을 목표로 한다.

가장 중요한 관찰은 `LLM brain`이 기존 heuristic solver를 완전히 대체하는 별도 파이프라인이 아니라, `solve_loop` 안에 꽂히는 **pluggable brain slot**이라는 점이다. 이건 framework 철학과 잘 맞는다. solver의 perception, belief ledger, world model, subgoal 구조는 유지하고, action selection brain만 모델로 교체할 수 있기 때문이다. 현재 구현은 [`llm_brain.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/llm_brain.py) 에 있고, [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py) 에서 `if llm_brain is not None:` 분기로 연결되어 있다.

현재 `LLM brain`이 읽는 입력은 꽤 좋다. 단순 grid만 받는 것이 아니라 `objects`, `dynamics_rules`, `interaction_rules`, `regions`, `reference_patterns`, `hypotheses`, `action_beliefs`, `goal_beliefs`, `phase`, `last_surprise`까지 함께 받는다. 즉 prompt 수준에서는 이미 “world-model-aware LLM brain”에 가까운 입력 구조가 형성되어 있다. 이건 narrative와 framework 문서들이 계속 요구하던 object-centric / rule-centric reasoning 방향과도 잘 맞는다.

하지만 실제 실행 경로를 보면 중요한 제약이 있다. `solve_episode(...)`는 `llm_model: str | None = None` 인자를 받지만, 현재 CLI와 wrapper는 이 값을 밖에서 넘기지 않는다. [`solve_loop.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/solve_loop.py)의 main CLI는 아직 `--llm-model` 같은 인자를 노출하지 않고, [`run_agentic_solver_job.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/run_agentic_solver_job.py)도 `solve_episode(...)` 호출 시 `llm_model`을 전달하지 않는다. 따라서 지금 시점에서 `LLM brain`은 **기본 실행 경로에 자동으로 붙은 기능이 아니라, 코드 내부에만 꽂혀 있는 optional override**라고 보는 것이 정확하다.

두 번째로 중요한 점은 backend 선택이다. 이 brain은 현재 `Claude`나 local Qwen runtime이 아니라 `OpenAI` chat completions를 사용한다. 기본 모델명도 `gpt-5.4-mini`로 되어 있다. 즉 이름은 “LLM brain”이지만, 실제 구현은 OpenAI client 기반 reasoning module이다. 이것 자체는 문제는 아니지만, 문서/CLI/운영 관점에서는 이 사실을 분명히 해야 한다. 지금 구조만 보면 사용자가 “Claude brain”이나 “Qwen brain”으로 오해할 여지가 있다. 따라서 naming이나 docs에서 backend truth를 더 명시하는 편이 좋다.

세 번째는 가장 즉각적인 integration concern이다. `ACTION6` 좌표 경로가 현재 반쯤만 연결되어 있을 가능성이 높다. `LLM brain`이 `COORDINATES: x,y`를 파싱하면 `BrainDecision.action_data`에 좌표를 담아 돌려준다. 하지만 `solve_loop`는 그 좌표를 지금 `belief_state.notes`에 `ACTION6_COORDS:x,y` 문자열로만 남기고 있다. 반면 실제 실행 경로는 `_resolve_action(chosen_action)`이 `chosen_action`에서 직접 dict payload를 만들어야 좌표가 env step까지 간다. 현재 분기를 보면 `chosen_action` 자체는 여전히 문자열 `ACTION6`로 흘러갈 가능성이 크다. 이 경우 LLM이 좌표를 잘 예측해도 실제 env 실행에는 반영되지 않는다. 이것은 단순 최적화 포인트가 아니라, LLM brain의 중요한 능력 하나가 소실될 수 있는 seam이다.

네 번째는 fallback semantics다. 현재 OpenAI 호출이 실패하면 brain은 첫 available action으로 떨어진다. 덕분에 runtime은 완전히 깨지지 않는다. 하지만 이것은 `LLM brain`이 들어가 있는지 여부와 관계없이 solver 행동을 조용히 바꿔버릴 수 있다. 따라서 실제 실험에서 이 경로를 사용할 경우, 최소한 trace나 decision notes에 “LLM fallback happened” 같은 신호를 명시적으로 남기는 편이 좋다. 지금은 로그 레벨에선 error가 남겠지만, structured artifact 수준에서 바로 보이진 않는다.

다섯 번째는 policy semantics다. 현재 주석대로 `LLM brain`은 heuristic decision-making을 “보조”하는 것이 아니라 사실상 **override**한다. 즉 `phase_manager`, `experiment_designer`, `subgoal_planner`가 만들어 놓은 기존 solver decision path 앞에 `llm_brain`이 오면, action selection은 전부 모델이 고른다. 이것은 실험적으로는 좋은 옵션일 수 있지만, framework 관점에서는 두 가지 선택지가 있다는 뜻이다. 하나는 현재처럼 full override를 유지하는 것이고, 다른 하나는 LLM을 reranker / advisor / subgoal evaluator로 낮춰서 기존 solver와 혼합하는 것이다. 지금은 전자에 가깝다. 이건 나쁜 것은 아니지만, “현재 모드가 무엇인지”를 명확히 의식하고 실험해야 한다.

이상의 내용을 바탕으로 지금 Claude가 우선적으로 판단하면 좋은 수정 포인트는 세 가지다. 첫째, `ACTION6` 좌표가 실제 `chosen_action` payload까지 가도록 seam을 닫는다. 둘째, `--llm-model` 같은 CLI / wrapper 파라미터를 노출해 supervisor, solve-loop smoke, unattended experiments에서 실제로 이 brain을 켜고 끌 수 있게 한다. 셋째, fallback happened / llm_used / llm_model 같은 metadata를 structured artifact에 남겨서 나중에 trace나 dataset을 읽을 때 어떤 decision이 heuristic이었고 어떤 decision이 LLM이었는지 구분 가능하게 한다.

정리하면, 현재 `LLM brain`은 나쁜 방향이 아니다. 오히려 framework가 원래 의도하던 “pluggable cognitive backend”라는 그림에 잘 맞는다. 다만 지금은 아직 “brain을 꽂을 자리는 생겼다”에 더 가깝고, 실제 운영 실험에 쓰기 위해선 몇 개의 integration seam과 observability seam을 먼저 닫아야 한다. Claude가 이 문서를 보고, 당장 full override를 유지할지 아니면 advisor/reranker 모드로 바꿀지, 그리고 `ACTION6` coordinate path를 어떻게 canonical하게 연결할지를 먼저 정하면 좋겠다.
