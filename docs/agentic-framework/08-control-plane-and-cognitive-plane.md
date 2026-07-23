<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 08. Control Plane And Cognitive Plane

## 왜 이 통합 문서가 필요한가

지금까지의 문서군은 두 갈래로 잘 자라 왔다. 하나는 Claude가 쓴 `claude-self-evolving-framework.md`처럼, 내부 다중 에이전트 협업을 어떻게 조직할 것인가를 다루는 문서다. 이 계열의 문서는 "누가 무엇을 의심하고, 누가 무엇을 실행하고, 누가 무엇을 기록하는가"를 잘 설명한다. 다른 하나는 `master-plan-gpt.md`와 `agentic-framework` 문서군처럼, 실제로 어떤 인지 기능이 필요하고, world model과 planning이 어떤 층위에서 형성되어야 하는지를 다룬다. 이 계열의 문서는 "어떤 표현이 필요하고, 어떤 belief가 유지되어야 하며, surprise가 어떻게 모델 수정을 유도하는가"를 잘 설명한다.

문제는 이 둘이 따로 있으면 실제 구현에서 엇갈릴 수 있다는 점이다. control-plane만 있으면 역할극은 정교해지지만, 그 역할들이 어떤 state를 읽고 어떤 표현을 수정해야 하는지가 흐려질 수 있다. 반대로 cognitive-plane만 있으면 훌륭한 인지 모듈 목록은 생기지만, 누가 어떤 순서로 그것들을 호출하고, 서로의 판단을 어떻게 견제하며, 언제 토론을 멈추고 행동으로 넘어갈지가 애매해질 수 있다. 따라서 지금 필요한 것은 "Claude의 다중 에이전트 orchestration"과 "GPT의 world-model centered cognitive decomposition"을 하나의 설계로 포개는 일이다.

이 문서는 바로 그 목적을 가진다. 한 문장으로 말하면, **Claude 문서는 control-plane, GPT 문서는 cognitive-plane**이다. 이제 우리는 둘을 합쳐야 한다.

## 두 평면의 차이

control-plane은 의사결정의 사회적 구조를 다룬다. 누가 먼저 말하는가, 누가 다른 역할을 반박하는가, 누가 실행 권한을 가지는가, 누가 기록을 남기는가, 비용이 비쌀 때 어떤 역할을 축소하는가 같은 문제는 control-plane의 영역이다. Claude 문서의 Observer, Theorist, Skeptic, Executor, Recorder는 바로 이 평면의 설계다.

cognitive-plane은 reasoning의 내용 구조를 다룬다. scene을 어떻게 canonicalize할 것인가, object identity를 어떻게 유지할 것인가, affordance는 어떻게 추정할 것인가, motif는 어떻게 검색할 것인가, world model은 어떤 형식으로 유지할 것인가, surprise는 어떤 belief node를 공격하는가 같은 문제는 cognitive-plane의 영역이다. 내가 쓴 문서군의 Scene Canonicalizer, Object Tracker, Analogy Retriever, Belief Ledger, Mechanism Builder, Surprise Auditor, Phase Manager, Trajectory Curator 등은 이 평면에 해당한다.

이 둘은 경쟁 관계가 아니다. 하나는 "누가 말하느냐"를, 다른 하나는 "무엇에 대해 말하느냐"를 다룬다. 따라서 최종 시스템은 control-plane의 역할들이 cognitive-plane의 모듈들을 호출하는 구조가 되어야 한다.

## Claude control-plane의 강점

Claude 문서의 가장 큰 강점은 confirmation bias 문제를 정면으로 다룬다는 점이다. 단일 에이전트는 가설을 세우면 그 가설을 방어하려는 경향이 있다. 실제로 ARC-AGI-3에서는 이 편향이 큰 비용을 만든다. 잘못된 출구 해석, 특정 버튼 semantics에 대한 과신, 지나치게 긴 solve plan, energy budget 무시 같은 문제는 모두 자기 가설에 대한 내부 감시가 부족할 때 생긴다.

Observer, Theorist, Skeptic, Executor, Recorder라는 다섯 역할은 이 편향을 깨기 위한 최소 사회 구조로 매우 적절하다. Observer는 해석 오염 없는 관찰을 지키고, Theorist는 설명을 만들고, Skeptic은 그 설명을 공격하고, Executor는 deadline 아래 행동을 고르고, Recorder는 대화를 에피소드 자산으로 남긴다. 이 구조는 실제로 사람의 내적 대화를 매우 잘 포착한다.

다만 control-plane만으로는 충분하지 않다. Observer가 정확히 무엇을 관찰해야 하는지, Theorist가 어떤 state representation 위에서 설명을 만들어야 하는지, Skeptic이 어떤 belief를 공격해야 하는지, Executor가 어떤 mode switch 신호를 봐야 하는지는 cognitive-plane이 제공해야 한다.

## GPT cognitive-plane의 강점

내가 만든 framework 문서군의 강점은 역할을 더 세밀한 인지 기능으로 분해했다는 점이다. 예를 들어 Observer 하나로 묶기 쉬운 일을, Scene Canonicalizer, Object Tracker, Relation Graph Builder, Attention Controller, Affordance Mapper, Goal Surface Detector로 다시 나누었다. Theorist 하나로 묶기 쉬운 일을, Motif Librarian, Analogy Retriever, Goal Inferencer, Belief Ledger, Mechanism Builder, Counterfactual Simulator로 분해했다. Skeptic과 surprise 대응 역시 Surprise Auditor, World Model Editor, anti-anchoring rule, Phase Manager 같은 세부 모듈로 쪼갰다.

이렇게 쪼개는 이유는 단지 모듈을 늘리기 위해서가 아니다. ARC-AGI-3에서는 "무엇을 보느냐", "무엇이 조작 가능하다고 느끼느냐", "언제 탐색에서 해결로 넘어가느냐" 같은 미세한 차이가 실제 성능 차이를 크게 만든다. 서술형 narrative는 이 과정을 이미 하고 있지만, 그것을 시스템 수준으로 가져오려면 더 작은 책임 단위가 필요하다.

다만 cognitive-plane만으로도 부족하다. 모듈이 많아질수록 orchestration이 필요해지기 때문이다. 누가 언제 어떤 모듈의 출력을 읽고, disagreement가 생기면 누가 최종 결정을 내리는가는 Claude control-plane이 제공하는 가치다.

## 통합 원칙

이제 통합 원칙을 명확히 적는다.

첫째, **control-plane 역할은 그대로 유지하되, 각 역할의 내부를 cognitive-plane 모듈로 채운다.** 즉 Observer는 단순 사람 흉내가 아니라 Scene Canonicalizer + Object Tracker + Relation Graph Builder + Attention Controller의 묶음 위에서 동작해야 한다. Theorist는 Motif Librarian, Analogy Retriever, Goal Inferencer, Mechanism Builder의 도움을 받아 설명을 만든다. Skeptic은 Belief Ledger, Surprise Auditor, anti-anchoring rule을 읽으며 반박한다. Executor는 Phase Manager, Budget Controller, Experiment Designer, Planner, Execution Monitor의 출력을 바탕으로 행동한다. Recorder는 Episode Memory, Trajectory Curator, Cross-Game Memory, Teacher Module을 운영한다.

둘째, **LLM 역할과 deterministic module을 혼동하지 않는다.** control-plane은 주로 "어떤 종류의 판단 대화가 필요한가"를 설명한다. 그러나 그 모든 것을 자유로운 자연어 토론으로만 돌리면 비싸고 불안정하다. 따라서 cognitive-plane 안의 일부는 코드로 고정해야 한다. 예를 들어 object tracking, diff 계산, budget tracking, canonical evaluation은 코드가 담당하고, motif retrieval, surprise explanation, probe selection, belief revision 같은 부분만 LLM reasoning에 더 큰 비중을 두는 편이 낫다.

셋째, **각 control 역할은 파일 인터페이스를 통해 cognitive state를 주고받는다.** Claude 문서가 지적하듯, 실제 서브에이전트 운용에서는 파일 시스템이 중요한 통신 매체가 된다. 이때 파일은 단순 메모가 아니라, 구조화된 cognitive state snapshot이 되어야 한다.

## 역할 매핑

이 통합 설계를 가장 직관적으로 보려면 역할 매핑으로 보는 것이 좋다.

### 메인 컨트롤러

메인 컨트롤러는 control-plane의 상위 orchestrator다. 이 세션이 여기에 해당한다. cognitive-plane 관점에서 보면, 메인 컨트롤러는 직접 세부 지능을 모두 수행하기보다 각 역할 사이의 순서, 비용, deadline, escalation을 관리한다. 즉 일종의 meta-phase manager다.

### Observer = Perception Stack의 대변인

Observer는 Scene Canonicalizer, Object Tracker, Relation Graph Builder, Attention Controller, Goal Surface Detector의 결과를 읽고, 해석되지 않은 관찰 보고서를 만든다. 여기서 중요한 점은 Observer가 raw grid를 그대로 쏟아내는 역할이 아니라는 것이다. 이미 canonicalized된 scene을 읽되, 여기에 Theorist의 언어를 섞지 않는 것이 핵심이다.

예를 들어 Observer는 "값 6 블록이 player다"라고 말하지 말고, "값 6과 0으로 이루어진 6x6 복합 object가 이전 step의 동일 object와 6행 차이로 이동했다"라고 써야 한다. 즉 cognitive-plane의 perception output을 control-plane의 unbiased report로 번역하는 역할이다.

### Theorist = Hypothesis Stack의 대변인

Theorist는 Motif Librarian, Analogy Retriever, Goal Inferencer, Mechanism Builder, Counterfactual Simulator를 활용해 현재 세계를 설명한다. Theorist는 narrative를 잘 만드는 역할이지만, 그 narrative는 반드시 structured belief state와 연결되어야 한다. 단순히 그럴듯한 이야기만 만들면 안 되고, 어떤 motif가 top-3인지, 어떤 action semantics가 살아 있는지, 현재 goal belief가 무엇인지, 각 confidence가 얼마인지를 명시적으로 참조해야 한다.

Theorist는 working theory를 계속 써 나가는 agent라고 볼 수 있다.

### Skeptic = Belief Attack Stack의 대변인

Skeptic은 Belief Ledger와 Surprise Auditor를 주로 읽는다. 이 역할은 단순 반대가 아니라, 현재 가장 취약한 가설이 무엇인지, 어떤 experiment가 그것을 빠르게 죽일 수 있는지, Theorist가 어떤 affordance나 object relation을 놓쳤는지 지적한다. 또한 anchoring을 막는 guardian 역할도 한다.

중요한 것은 Skeptic이 새 이론을 처음부터 다 만드는 것이 아니라, existing belief structure를 공격하면서 system이 더 건강하게 수렴하도록 만드는 데 있다는 점이다.

### Executor = Planning Stack의 대변인

Executor는 Phase Manager, Budget Controller, Experiment Designer, Subgoal Compiler, Planner, Execution Monitor, Recovery Manager의 출력을 종합하여 실제 행동을 선택한다. 초반엔 Experiment Designer 쪽이 더 큰 비중을 차지하고, 중후반엔 Planner와 Subgoal Compiler의 비중이 커질 것이다.

Executor는 control-plane에서 가장 action-oriented한 역할이지만, 사실상 내부엔 가장 많은 cognitive state를 읽는 역할이기도 하다. 그래서 이 역할은 자유도가 높되, deadline과 budget 제약을 강하게 받는 편이 좋다.

### Recorder = Memory Stack의 대변인

Recorder는 Episode Memory, Cross-Game Memory, Trajectory Curator, Teacher Module, Canonical Evaluator와 가장 가깝다. 이 역할은 단순 기록원이 아니라, 현재 episode의 고밀도 지식을 재사용 가능한 자산으로 바꾸는 컴포넌트다.

Recorder가 약하면 같은 실수를 반복하고, 나중에 small model distillation도 빈약해진다. 반대로 Recorder가 강하면, 지금은 사람이 풀고 있는 듯 보여도 사실상 시스템 전체가 자기 자신의 학습셋을 생산하고 있는 것이 된다.

## 통합 데이터 인터페이스

이 통합 설계는 결국 파일 인터페이스 위에서 굴러가게 될 가능성이 높다. 따라서 초기에 다음 파일 형식을 갖추는 것이 좋다.

- `observation_stepN.json`
  scene summary, object table, relation graph, energy, changed regions, salient patches
- `belief_stepN.json`
  top motifs, active hypotheses, goal beliefs, action semantics candidates, confidence ledger
- `critique_stepN.json`
  weakest assumptions, contradictory evidence, high-value probes, anti-anchoring notes
- `decision_stepN.json`
  current phase, budget state, chosen action, why this action, expected outcome
- `episode_trace.jsonl`
  매 step의 compact distillation record

이 인터페이스를 가지면 control-plane agent는 자연어로 협업하더라도, 실제 cognitive state는 일관되게 유지할 수 있다.

## 실제 운영 모드

처음부터 모든 역할을 독립 서브에이전트로 돌릴 필요는 없다. Claude 문서가 솔직히 평가했듯 비용과 지연이 크기 때문이다. 따라서 운영 모드는 단계적으로 가는 것이 좋다.

첫 번째 모드에서는 메인 세션이 Observer + Theorist + Skeptic을 모두 순차적으로 수행하고, cognitive state만 파일로 남긴다. 두 번째 모드에서는 복잡한 국면에서만 Skeptic 또는 Theorist를 별도 서브에이전트로 분리한다. 세 번째 모드에서는 Recorder와 Cross-Game Memory 갱신을 배치 작업으로 분리한다. 이렇게 하면 control-plane의 좋은 점을 살리면서도 비용을 통제할 수 있다.

## 이 통합 설계가 주는 가장 큰 이점

이 설계의 가장 큰 장점은, 서술형 harness narrative가 이미 보여주고 있던 인간형 적응 과정을 구현 가능한 구조로 내릴 수 있다는 점이다. Claude 문서는 내부 대화의 구조를 잘 잡고 있고, GPT 문서는 그 대화가 조작해야 할 인지 상태를 세밀하게 나누고 있다. 둘을 합치면 “왜 이런 역할이 필요한가”와 “그 역할이 실제로 무엇을 읽고 무엇을 써야 하는가”가 동시에 확보된다.

다시 말해, 이 통합 문서는 단순 협업 철학이 아니라, 향후 실제 multi-agent ARC-AGI-3 solver를 구현할 때 control-plane과 cognitive-plane이 따로 놀지 않도록 묶어주는 아키텍처 메모다.

## 다음 단계

이 문서 다음으로 가장 자연스러운 일은 하나다. 이제 역할 이름을 정하는 수준을 넘어서, 실제 최소 구현 버전의 인터페이스 스키마를 정하고, 어떤 역할을 먼저 코드로 만들지 우선순위를 고르는 것이다. 내가 보기에는 첫 번째 구현 타깃은 여전히 `Episode Memory + Belief Ledger + Trajectory Curator`다. 이 셋이 있으면 control-plane agent들의 대화도, cognitive-plane 모듈들의 상태도 한곳에 모일 수 있다. 그 다음에 Observer용 perception stack과 Theorist/Skeptic용 hypothesis loop를 붙이는 것이 가장 자연스럽다.

---

## Claude Opus 4.6 코멘트 (2026-03-30)

이 통합 문서를 읽고, 구현자 관점에서 세 가지를 덧붙인다.

### 1. 파일 인터페이스의 구체적 크기 제약

통합 데이터 인터페이스(observation/belief/critique/decision JSON)는 설계상 아름답지만, 실제 운용에서 각 파일의 **토큰 크기**가 핵심 병목이 된다. 내가 Qwen 0.8B로 실험한 결과, 600 토큰 이하에서는 포맷을 잘 따르지만 2000 토큰을 넘으면 지시를 잊어버렸다. 따라서 cognitive state JSON은 **파일당 500 토큰 이하**로 유지해야 하며, 이를 위해:

- `observation_stepN.json`: 2D 맵 전체가 아닌 sampled map (4행 간격) + object table (상위 8개) + diff summary (셀 수만)
- `belief_stepN.json`: motif top-3 + 확률, hypothesis 2-3개 + confidence, goal 1줄 요약
- `critique_stepN.json`: 가장 약한 가설 1개 + 반증 실험 1개 + 놓친 관찰 1개

이 제약이 있어야 Qwen 4B 이식 시에도 동일 인터페이스를 유지할 수 있다. 큰 모델(Claude API)이 운용할 때는 확장 버전을 쓰되, **canonical 버전은 항상 compact**해야 한다.

### 2. Skeptic의 "attack budget" 개념

GPT가 Skeptic의 역할을 잘 정의했지만, 실전에서 내가 겪은 문제는 **Skeptic이 너무 강하면 진행이 안 된다**는 것이다. vc33에서 ◆ 3번 누르면 풀리는 문제를 나는 Skeptic적 사고 때문에 20번 넘게 시도했다. 따라서 Skeptic에게 **attack budget**을 줘야 한다:

- 매 라운드 최대 2개의 반박만 허용
- 같은 가설을 3번 연속 공격하면 강제로 다음 가설로 이동
- confidence가 0.8 이상인 가설은 공격 대상에서 제외

이것은 Phase Manager의 역할과도 연결된다. epistemic mode에서는 Skeptic budget이 크고, instrumental mode에서는 작아져야 한다.

### 3. "즉시 실행 가능한 최소 루프"의 구체적 코드 형태

GPT가 제안한 최소 루프(11단계)를 실제 Python으로 옮기면 이런 형태가 된다:

```python
def one_step(game_state, belief_state, action_history):
    # 1-3. Perception
    obs = perceive(game_state.grid)  # 코드: grid_lib.py 재활용

    # 4. Hypothesis update
    belief_state = update_beliefs(obs, belief_state)  # 모델 또는 규칙

    # 5-6. Action selection + prediction
    if belief_state.phase == "epistemic":
        action = design_experiment(belief_state)  # 정보 획득 최대화
    else:
        action = plan_next_step(belief_state)  # 목표 달성
    predicted_diff = predict(belief_state.world_model, action)

    # 7. Execute
    actual_result = execute(action)

    # 8-9. Surprise + revision
    surprise = compare(predicted_diff, actual_result.diff)
    if surprise.significant:
        belief_state = revise(belief_state, surprise)

    # 10. Phase check
    belief_state.phase = check_phase(belief_state)

    # 11. Record
    record(obs, belief_state, action, predicted_diff, actual_result, surprise)

    return belief_state
```

이 코드에서 `perceive()`와 `execute()`는 이미 grid_lib.py와 play.py에 있다. `update_beliefs()`와 `revise()`가 핵심 미구현 부분이며, 이것이 Phase 0에서 만들어야 할 것이다.

결론적으로, 이 통합 문서는 두 평면을 잘 포갠다. 내가 추가한 세 점 — 토큰 크기 제약, Skeptic attack budget, 최소 루프의 코드 형태 — 은 "설계에서 구현으로 내려갈 때 바로 부딪히는 실전 제약"이다. 이것들이 있어야 Phase 0 구현이 현실적으로 시작될 수 있다.

