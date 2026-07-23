<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 03. Perception And Affordance

## 이 층이 왜 중요한가

사람은 새로운 게임을 볼 때 모든 픽셀을 같은 무게로 읽지 않는다. 배경을 걷어내고, salient object를 고르고, 무엇이 움직일 것 같은지 추정하고, 어디를 먼저 봐야 할지 정한다. 현재의 harness narrative들도 이미 이 과정을 하고 있지만, 대부분은 서술 수준에 머무른다. framework로 구현하려면 이 과정을 명시적인 역할들로 분해해야 한다.

## Scene Canonicalizer

Scene Canonicalizer의 역할은 현재 frame을 일관된 표준 표현으로 바꾸는 것이다. 배경색 후보, active playfield, display region, likely HUD, repeated motifs, sparse salient regions를 정리해야 한다. 같은 게임이라도 step마다 작은 흔들림이 생길 수 있으므로, canonicalizer는 단순 시각 변화에 흔들리지 않는 representation을 제공해야 한다.

이 컴포넌트의 산출물은 raw grid가 아니라 `scene summary`다. 예를 들어 `sk48`에서는 “다이아몬드, 꼬리, 세 블록, 참조 영역, 에너지 바”로 정리되고, `re86`에서는 “십자형 레일, 교차점 커서, 분산된 마커들, 하단 에너지 바”로 정리되어야 한다. 이 요약은 뒤의 motif retrieval과 world model의 공통 입력이 된다.

## Object Tracker

Object Tracker는 장면 속 물체에 persistent identity를 부여한다. 중요한 이유는, ARC-AGI-3에서는 같은 물체가 이동하거나, 모양을 조금 바꾸거나, 다른 물체와 합쳐지거나, 일시적으로 가려질 수 있기 때문이다. 단순 diff만 보면 “무엇이 변했는가”는 알 수 있어도 “무엇이 같은 존재로 남았는가”는 놓치기 쉽다.

Tracker는 최소한 다음 사건을 다뤄야 한다. 이동, 회전, 크기 변화, merge, split, appearance, disappearance, occlusion. 또한 tracker는 confidence를 가져야 한다. 즉 어떤 object identity는 확실하고, 어떤 것은 ambiguity를 가진 채 유지될 수 있어야 한다.

## Relation Graph Builder

Perception의 출력은 object list만으로 충분하지 않다. object 간 관계가 중요하기 때문이다. 상대 위치, 접촉 여부, 포함 관계, 정렬, 대칭, 동일 행/열, 레일 위 여부, 벽과의 거리, reference object와의 대응 같은 관계를 graph 형태로 빼는 것이 좋다.

이 graph는 motif retrieval과 affordance inference에 큰 도움이 된다. `tr87`처럼 정렬/재배치 문제는 object 자체보다 slot 관계가 중요하고, `ls20`처럼 navigation 문제는 에이전트와 벽, 목표 상자, 에너지 오브젝트 사이의 공간 관계가 더 중요하다.

## Attention Controller

Attention Controller는 “지금 무엇을 자세히 봐야 하는가”를 정한다. 사람은 scene 전체를 한 번에 균등하게 reasoning하지 않는다. 움직임이 있었던 곳, 반복 구조가 모여 있는 곳, 목표처럼 보이는 곳, interaction이 예상되는 접촉 부위를 먼저 본다.

이 컴포넌트는 다음 질문에 답해야 한다. 지금 가장 중요한 subgrid는 어디인가. 어떤 object pair의 관계가 가장 diagnostic한가. 다음 action 이후 어느 영역의 diff를 확대해서 비교해야 하는가. 현재 belief state 아래에서 HUD와 playfield 중 어디를 더 살펴봐야 하는가.

이 역할은 나중에 비용 절감에도 도움이 된다. 모델이 매번 전체 64x64를 reasoning하는 대신, attention-selected patch와 canonical summary만 보면 되기 때문이다.

## Affordance Mapper

Affordance Mapper는 scene을 보고 “무엇을 할 수 있어 보이는가”를 추정한다. 어떤 object는 player처럼 보이고, 어떤 것은 pushable, 어떤 것은 collectible, 어떤 것은 click target, 어떤 것은 gate, 어떤 것은 trigger plate처럼 보인다. 이 조작 가능성 추정은 인간이 새 게임에 적응할 때 매우 빠르게 수행하는 일이다.

Affordance는 object label과 다르다. 어떤 object가 문처럼 보여도 실제론 switch일 수 있고, 빈 공간처럼 보여도 click target일 수 있다. 따라서 mapper는 각 object나 region에 대해 복수의 affordance 후보와 confidence를 유지해야 한다.

이 컴포넌트는 probe selection을 직접 돕는다. 예를 들어 어떤 빈 칸이 clickable region으로 보이면 ACTION6/7의 좌표 실험을 유도하고, 어떤 object가 retract/extend interaction의 후보면 `sk48`류의 probing을 우선하게 만든다.

## Goal Surface Detector

모든 goal inference를 나중으로 미루면 늦다. 사람은 장면을 읽을 때 이미 “여기가 목표처럼 보인다”는 표면적 힌트를 잡는다. reference panel, score display, boxed target, repeated template, exit-like region, matched pattern zone 같은 것이 여기에 해당한다.

Goal Surface Detector는 깊은 goal reasoning 이전에, 어떤 영역이 목표의 흔적을 담고 있는지 먼저 태깅한다. 이것은 later-stage Goal Inferencer가 사용할 좋은 힌트가 된다.

## 이 층의 실패 모드

이 층이 실패하면 뒤의 모든 reasoning이 흐려진다. background를 object로 오인하거나, 동일 object를 매 프레임마다 새로 인식하거나, display region을 무시하거나, 움직일 수 없는 decorative pattern을 controllable하게 잘못 태깅하면 motif retrieval도 왜곡된다. 따라서 초기 구현에서는 이 층을 “완벽한 지능”으로 만들기보다, 신뢰도 높은 기하/연결성 기반 추출기와 conservative confidence management를 넣는 것이 좋다.

## 첫 구현 우선순위

가장 먼저 필요한 것은 Scene Canonicalizer와 Object Tracker다. 그 다음 Relation Graph Builder와 Goal Surface Detector를 붙이고, Affordance Mapper와 Attention Controller는 heuristic + small-model hybrid로 시작하는 것이 현실적이다. 이 순서로 가면 narrative에 이미 적혀 있는 scene analysis 부분을 system화하는 첫 발판이 된다.

