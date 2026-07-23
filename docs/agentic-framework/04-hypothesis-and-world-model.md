<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 04. Hypothesis And World Model

## 왜 이 층이 중심인가

ARC-AGI-3의 핵심은 결국 “이 게임은 어떤 세계인가”를 빠르게 설명하는 데 있다. perception이 scene을 준비하면, hypothesis/world-model 층은 그것을 해석 가능한 세계로 바꿔야 한다. 이 층이 약하면 system은 그냥 반응형 탐색기에 머문다.

## Motif Librarian

Motif Librarian은 장르적 prior의 저장소다. navigation, maze, threading, push, sorting, assembly, toggle, click-semantics, symmetry, reflection, track-building, sequence puzzle 같은 motif를 담고 있어야 한다. 중요한 것은 단순한 라벨 목록이 아니라, 각 motif가 암시하는 causal grammar를 함께 저장하는 것이다.

예를 들어 navigation motif는 “controllable object가 있고, 이동 가능 영역과 장벽이 있다”를 뜻하고, threading motif는 “anchor object와 extendable/retractable structure, pass-through or attach interaction이 있다”를 뜻한다. sorting motif는 “slot, container, arrangement objective, order constraint”를 함의한다.

## Analogy Retriever

Retriever는 현재 scene summary를 받아 가장 그럴듯한 motif 몇 개를 소환하는 역할을 맡는다. 이 단계는 인간의 “아, 이건 소코반 같다”, “이건 조준선 퍼즐 같다”라는 감각과 대응한다.

중요한 것은 단일 motif로 바로 수렴하지 않는 것이다. top-k motif와 그 evidence를 함께 내야 한다. 또한 retriever는 왜 그런 motif를 불렀는지 설명 가능해야 한다. 그래야 나중에 surprise가 왔을 때 어떤 근거가 무너졌는지도 추적할 수 있다.

## Goal Inferencer

Goal Inferencer는 현재 세계에서 무엇이 success를 의미하는지 추정한다. 이 역할은 narrative들에서 자주 등장하지만, 별도 agent로 분리하지 않으면 planner가 잘못된 objective를 최적화할 위험이 크다.

Goal은 표면적으로는 reference matching, target zone entry, state toggle completion, object ordering, object removal, full coverage, path completion 등으로 다양하다. inferencer는 단순히 “정답을 맞힌다”가 아니라, 현재 어떤 latent objective가 가장 유력한지 belief로 유지해야 한다.

## Belief Ledger

Belief Ledger는 현재 살아 있는 motif, affordance, action semantics, goal assumption, object identity ambiguity를 한곳에서 관리한다. 이것은 단순한 메모장이 아니라, 각 belief node의 confidence와 supporting/attacking evidence를 보관하는 구조여야 한다.

Ledger가 있어야 system은 다음 질문에 답할 수 있다. 지금 가장 유력한 motif는 무엇인가. ACTION4에 대한 해석은 아직 몇 개가 살아 있는가. 어떤 관찰이 H1을 약화시켰는가. 어느 belief가 가장 취약해 반증 실험이 필요한가.

## Mechanism Builder

Mechanism Builder는 실제 world model을 구축한다. 여기서의 world model은 raw pixel predictor가 아니라, action이 object와 관계에 어떤 변화를 일으키는지 설명하는 transition model이다. 코드 템플릿 형태로 가도 되고, structured rule form으로 가도 된다.

예를 들어 “ACTION1은 controllable assembly를 6칸 위로 이동”, “ACTION4는 trail length를 6만큼 증가”, “click action은 crosshair intersection과 겹친 marker를 toggle”처럼 규칙이 표현되어야 한다. 이 규칙은 hypothesis가 아니라 점진적으로 강화되는 working theory다.

## Counterfactual Simulator

Simulator는 현재 world model로 action 결과를 예측한다. 이 예측 능력이 있어야 epistemic planning도, instrumental planning도 가능하다. 단순히 하나의 next state를 출력하는 것이 아니라, top action 후보 각각에 대해 무엇이 바뀔지를 설명해야 한다.

정확한 full-grid simulation이 어려울 때도 최소한 `affected object subset`, `change type`, `goal progress estimate` 정도는 예측해야 한다. 이 층이 있으면 “어떤 action이 가장 정보량이 높은가”와 “어떤 action이 목표에 가장 가까운가”를 모두 비교할 수 있다.

## Surprise Auditor

Surprise Auditor는 예측과 실제 관측의 차이를 받아, 그 차이가 무엇을 의미하는지 해석한다. 이 역할은 narrative들에서 자주 서술되지만, framework에서는 별도 컴포넌트로 승격돼야 한다.

Surprise는 단순 오류가 아니다. 그것은 belief를 재배열하는 강한 학습 신호다. 예측보다 더 많은 object가 움직였는지, 전혀 다른 region이 변했는지, change type은 맞았는데 magnitude가 틀렸는지, expected precondition이 없었는지, hidden mode가 의심되는지 등을 분해해야 한다.

## World Model Editor

Auditor의 해석을 받아 실제 규칙을 수정하는 주체가 World Model Editor다. 이 역할은 코드 수정자에 가깝다. 기존 규칙을 강화하거나, 예외 조건을 추가하거나, 전혀 다른 semantics로 바꾸거나, kill된 가설에 연결된 규칙을 제거해야 한다.

핵심은 보수성이다. 모든 surprise마다 world model 전체를 뒤엎으면 안 된다. 반대로 evidence가 충분한데도 수정하지 않으면 anchoring이 심해진다. 따라서 editor는 local patch와 global rewrite를 구분해야 한다.

## anti-anchoring 규칙

이 층에는 반드시 anti-anchoring 규칙이 있어야 한다. narrative들을 읽으며 가장 자주 느낀 리스크가 바로 너무 빠른 motif 고정이었다. 이를 막기 위해 다음 규칙을 권장한다.

첫째, 초기엔 top-3 motif를 유지한다. 둘째, 어떤 motif의 핵심 prediction이 두 번 연속 틀리면 confidence를 크게 깎는다. 셋째, 한 motif만 기준으로 probe를 설계하지 않고, 두 개 이상의 가설을 가르는 experiment를 선호한다. 넷째, solve phase 진입 직전에도 최소 하나의 대안 semantics를 보존한다.

## 첫 구현 우선순위

먼저 Motif Librarian, Analogy Retriever, Belief Ledger의 최소 버전을 만든 뒤, rule-based Mechanism Builder와 Counterfactual Simulator를 붙이는 것이 좋다. Surprise Auditor와 World Model Editor는 처음엔 단순 패턴 분류기로 시작해도 된다. 중요한 것은 이 계층을 narrative 수준의 설명에서 시스템 수준의 belief machine으로 옮기는 것이다.

