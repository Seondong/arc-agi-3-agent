<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 25. Solver Priority Handoff

이 문서는 현재 시점에서 solver 개발의 우선순위를 정리하고, 어떤 종류의 작업을 Claude가 맡는 것이 더 자연스러운지, 어떤 종류의 작업을 GPT scaffold 쪽이 보조하는 것이 좋은지를 명확히 남기기 위한 handoff 문서다. 핵심 배경은 분명하다. episode memory, supervisor, night loop, queue policy, trace enrichment, phase-aware scheduling, solve-loop bridge까지 올라오면서 scaffolding은 이미 “최소 작동 골격”을 넘어섰다. 따라서 이제부터의 주력 개발은 새 control-plane을 계속 늘리는 것보다, 실제 solve quality를 밀어 올리는 쪽으로 옮겨가야 한다.

현재 기준의 solver 우선순위는 세 가지다. 첫째는 perception과 object persistence를 강화하는 일이다. 둘째는 surprise 이후 belief update가 실제 다음 행동에 영향을 주도록 wiring하는 일이다. 셋째는 epistemic probing 이후 solve-oriented subgoal planning을 더 구체화하는 일이다. 이 셋은 서로 연결되어 있다. 잘 보지 못하면 hypothesis가 흔들릴 이유를 설명할 수 없고, belief를 제대로 고치지 못하면 probe는 많아져도 세계를 더 잘 이해하지 못하며, subgoal이 없으면 instrumental 단계가 여전히 얕은 local action 선택에 머무르게 된다.

## 우선순위 1. Perception / Object Persistence

가장 먼저 강화해야 할 것은 scene을 object 중심으로 읽는 계층이다. 여기서 필요한 것은 “더 많은 feature를 뽑는다”가 아니라, step 간 동일 object의 지속성, controllable object 후보, goal-like object 후보, blocker, clickable region, relation graph를 더 안정적으로 세우는 것이다. 즉 solver가 매 step을 새로운 픽셀 배열로 보는 것이 아니라, 같은 세계의 변형된 상태로 보게 만들어야 한다.

이 작업은 기본적으로 Claude가 맡는 것이 더 적합하다. 이유는 perception 개선이 곧바로 world-model과 planning 가정에 영향을 미치기 때문이다. object summary의 어떤 필드가 실제 hypothesis discrimination에 중요한지, relation graph를 어떻게 solver 내부 belief와 연결할지, 어떤 object를 controllable candidate로 볼지 같은 문제는 solve-loop 내부 reasoning과 가까운 의사결정이다. 현재 Claude가 `perception.py`, `solve_loop.py`, `experiment_designer.py`를 더 직접적으로 다루고 있으므로, 이 영역은 solver 본체를 보는 쪽이 일관되게 가져가는 것이 좋다.

GPT 쪽의 역할은 여기서 보조적이다. 예를 들어 perception 변경이 episode artifact 품질을 실제로 올렸는지 검증하는 테스트를 쓰거나, perception 결과가 trace/dataset에 어떻게 남아야 하는지를 schema 수준에서 정리하는 일은 GPT scaffold 쪽이 지원할 수 있다. 그러나 perception의 핵심 로직 자체는 Claude가 주도하는 편이 자연스럽다.

## 우선순위 2. Belief Revision Wiring

두 번째 우선순위는 surprise가 단순 기록으로 끝나지 않고, 실제 hypothesis pruning, action semantics 수정, motif confidence 갱신으로 이어지게 만드는 일이다. 현재 trace에는 surprise와 actual information gain 같은 신호가 점점 풍부하게 남고 있지만, solver가 그 신호를 얼마나 강하게 다음 step 의사결정에 반영하느냐는 아직 개선 여지가 크다. 다시 말해 “놀랐다”에서 끝나지 않고, “어떤 hypothesis를 버렸고, 다음 probe는 왜 달라졌는가”로 이어져야 한다.

이 영역은 Claude와 GPT의 공동 seam으로 보는 것이 가장 좋다. belief update의 core logic, 즉 어떤 hypothesis를 죽이고 어떤 confidence를 올릴지는 Claude가 solver 내부에서 설계하는 편이 맞다. 반면 그 변화가 episode trace, decision record, queue policy, actual/expected gain calibration에 어떻게 반영되어야 하는지는 GPT 쪽이 더 잘 받쳐줄 수 있다. 따라서 이 우선순위는 “Claude 주도, GPT 보조”가 가장 적절하다.

실제로 작업을 나누자면, Claude는 `surprise_auditor.py`, `solve_loop.py`, `phase_manager.py`와 맞닿는 belief revision 규칙을 개선하고, GPT는 그 결과를 structured diff로 남기거나 scheduler가 읽을 수 있는 signal로 정리하는 역할을 맡는 것이 좋다. 이 분야는 양쪽이 만나는 seam이므로, 문서화와 artifact schema 합의가 특히 중요하다.

## 우선순위 3. Subgoal Planning

세 번째 우선순위는 solve-oriented planning을 더 실제적인 subgoal 기반으로 바꾸는 일이다. 지금까지의 프레임워크는 epistemic probing, motif retrieval, experiment design 쪽이 많이 강화되었다. 하지만 ARC-AGI-3에서 실제 점수를 내려면, 어느 시점에서는 “무엇을 더 알아낼까”가 아니라 “무엇을 달성해야 하는가”로 넘어가야 한다. 이때 필요한 것이 subgoal이다. 예를 들면 path를 여는 것, 특정 object를 특정 위치로 보내는 것, switch를 활성화하는 것, aligned state를 만드는 것, goal region에 진입하는 것 같은 중간 목표가 plan에 명시적으로 등장해야 한다.

이 작업도 Claude가 주도하는 편이 맞다. subgoal planner는 experiment designer보다 더 solve-loop 중심의 기능이고, perception 결과와 belief state를 동시에 이용해야 하며, phase transition과도 강하게 연결된다. 즉 외부 scheduler보다 solver 내부 brain 쪽에 더 가까운 기능이다. 따라서 GPT가 먼저 planner를 크게 설계해버리기보다, Claude가 solve-loop 안에서 어떤 상태 표현을 쓰는지에 맞춰 자연스럽게 키우는 편이 좋다.

GPT는 이 단계에서 두 가지를 도울 수 있다. 첫째, subgoal이 trace에 어떻게 저장될지 구조를 정리할 수 있다. 둘째, subgoal planner가 생긴 뒤 그 결과를 night loop attention policy나 distillation export와 연결하는 보조 작업을 할 수 있다. 그러나 subgoal의 실질적 정의와 생성 로직은 Claude가 잡아야 solver 내부와 덜 어긋난다.

## 권장 담당 구조

정리하면 권장 담당 구조는 아래와 같다.

1. Perception / object persistence: Claude 주도, GPT는 테스트·trace schema 보조
2. Belief revision wiring: Claude 주도, GPT는 artifact/queue/seam 반영 보조
3. Subgoal planning: Claude 주도, GPT는 기록·integration 보조

즉 현재 우선순위 세 개는 모두 solver 본체 쪽에 더 가깝고, 그래서 1차 구현자는 Claude가 되는 것이 자연스럽다. GPT는 이 셋을 대신 구현하기보다, solver 개선이 실제로 unattended loop, manifest, episode dataset, distillation path에 잘 흘러들어오도록 다리를 놓는 역할을 맡는 편이 가장 효율적이다.

## GPT가 당장 피해야 할 일

이 시점에서 GPT가 먼저 들어가서 해버리면 오히려 충돌 가능성이 큰 작업도 있다. 예를 들어 `perception.py`의 핵심 object grouping 규칙을 크게 바꾸거나, solve-loop 안의 plan state 구조를 먼저 재설계하거나, subgoal semantics를 미리 추상화해서 박아두는 일은 권장하지 않는다. 이런 작업은 solver 내부 표현과 긴밀하게 맞물려 있기 때문에, Claude가 이미 들고 있는 reasoning 흐름과 충돌할 수 있다.

따라서 GPT는 이제 solver를 “대신 구현하는 사람”이 아니라, solver가 더 잘 작동하도록 주변 seam을 닦고, 좋아진 solver를 dataset과 loop 안으로 흡수하는 사람으로 움직이는 것이 맞다.

## 바로 다음 액션

이 문서를 기준으로 바로 다음 액션은 다음과 같이 잡는 것이 좋다.

1. Claude는 `perception -> belief revision -> subgoal planning` 순서로 solver 핵심 트랙을 민다.
2. GPT는 그동안 새 scaffold를 크게 늘리지 않는다.
3. 다만 Claude 쪽 변경이 들어오면, 그 결과를 trace/schema/night loop/dataset export에 연결하는 얇은 integration만 수행한다.
4. 만약 Claude의 solver 변경이 실제 artifact에 충분히 반영되지 않거나 outer loop에서 읽히지 않는다면, 그때만 GPT가 seam 작업을 추가한다.

## 운영 메모

이 문서는 “누가 더 잘하느냐”의 문제가 아니라, 현재 코드베이스에서 어떤 변경이 어디와 더 강하게 결합되어 있느냐를 기준으로 정리한 것이다. 지금 solver 우선순위 세 개는 모두 solve-loop 내부 의미론과 가깝다. 따라서 Claude가 주도하고, GPT는 그 개선이 구조화된 episode corpus와 unattended framework로 잘 스며들게 보조하는 방식이 가장 안정적이다.
