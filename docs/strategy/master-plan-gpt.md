<!-- [Mar 29] Created by SD with GPT-5.4. -->
# ARC-AGI-3 Master Plan GPT

## 왜 이 문서를 다시 쓰는가

이 문서는 ARC-AGI-3를 단순한 강화학습 문제나 next-action prediction 문제로 다루지 않기 위해 쓰였다. 내가 이 프로젝트를 바라보는 관점은 비교적 분명하다. ARC-AGI-3에서 진짜 어려운 것은 “지금 당장 무슨 action을 누를까”를 맞히는 것이 아니다. 더 근본적인 어려움은, 지금 내가 보고 있는 64x64 grid가 어떤 종류의 세계를 나타내고 있는지, 그 안에 어떤 object들이 존재하는지, 어떤 object가 조작 가능한지, 어떤 object가 결과물인지, action이 개입되었을 때 그 object들 사이의 관계가 어떤 규칙으로 변하는지를 매우 적은 관측만 가지고 빠르게 파악해야 한다는 점에 있다. 다시 말해, 이 과제의 본질은 policy 이전에 world model이고, planning 이전에 world understanding이다.

나는 이 점이 굉장히 중요하다고 생각한다. 왜냐하면 ARC-AGI-3를 grid를 입력받아 action을 출력하는 블랙박스 함수로 생각하는 순간, 문제의 핵심을 놓치기 쉽기 때문이다. 그런 접근은 표면적으로는 그럴듯해 보이지만, 실제로는 세계의 규칙을 추론하는 대신 픽셀 수준의 상관관계에 의존하게 만든다. 그리고 그런 방식은 데이터가 아주 많고 규칙이 반복되는 환경에서는 어느 정도 작동할 수 있어도, ARC-AGI-3처럼 매 문제마다 다른 규칙이 생겨나는 환경에서는 쉽게 무너진다. 여기서는 무엇보다도 “이 문제의 물리학, 논리학, 조작 체계가 무엇인가”를 빠르게 알아내는 능력이 중요하다. 그러므로 이 문서의 목적은 정답률을 조금 높이는 요령을 나열하는 데 있지 않고, 문제를 풀기 위해 우리가 어떤 종류의 인지 구조를 시스템 안에 세워야 하는지 서술적으로 정리하는 데 있다.

이 문서가 특히 필요한 이유는 하나 더 있다. 우리는 결국 이런 능력을 Qwen 4B와 같은 작은 모델에게도 이식하고 싶어 한다. 그러려면 지금의 생각을 “막연히 감으로 푼다” 수준에 두면 안 되고, 나중에 코드와 데이터, prompt schema, evaluation protocol로 쪼갤 수 있는 형태로 남겨야 한다. 그러므로 아래 내용은 철학적 주장처럼 보일 수 있지만, 실제로는 앞으로의 harness 설계, scorecard 검증, distillation dataset 작성, 그리고 최종 Kaggle notebook packaging까지 이어질 실무 계획의 뼈대이기도 하다.

## 가장 먼저 고정해야 할 원칙

이 프로젝트에서 가장 먼저 고정해야 할 것은 정보 경계다. `environment_files`를 읽지 않는다는 원칙은 단순히 규칙을 지키자는 선언이 아니라, 우리가 만들고 싶은 능력의 정의와 직접 연결된다. 환경 구현을 읽는 것은 빠른 지름길일 수 있다. 그러나 그 순간부터 시스템은 “주어진 관측만으로 세계를 이해하는 능력”을 배우는 것이 아니라, “숨겨진 정답 설명서를 참조해 행동하는 능력”을 배우게 된다. 그것은 ARC-AGI-3에서 궁극적으로 우리가 검증하고 싶은 종류의 일반화가 아니다. 더 나아가, 그렇게 얻어진 해결 절차는 scorecard나 Kaggle 환경에서 재현 가능한 사고 절차로 이어지기 어렵고, 작은 모델에 이식 가능한 형태의 지식으로도 남기 힘들다.

따라서 허용되는 정보는 엄격하게 제한되어야 한다. 현재 frame, 이전 frame과의 diff, available actions, action 이후의 변화, state, levels completed, 그리고 scorecard나 recording을 통해 관찰 가능한 로그만을 사용해야 한다. 이 제한은 우리를 불편하게 만들지만, 동시에 더 강한 설계를 요구한다. 우리가 정말로 만들고 싶은 것은 “관측 가능한 것만으로도 문제를 구조화하는 기계”이기 때문이다.

두 번째 원칙은 grid를 픽셀 자체로 보지 않는 것이다. 64x64 grid는 겉으로는 4096개의 셀로 이루어져 있지만, 사람이 문제를 푸는 방식은 그 4096개의 셀을 같은 위상으로 다루지 않는다. 사람은 반복되는 색 영역을 묶고, 연결된 덩어리를 object로 보고, 배경과 전경을 분리하고, 경계와 중심을 직관적으로 느끼며, “저것은 플레이어 같고, 저것은 문 같고, 저것은 장애물 같고, 저것은 목표 지점 같다”는 식의 장면 해석을 수행한다. 다시 말해 사람에게 중요한 것은 픽셀값 자체가 아니라, 픽셀들이 어떤 object와 관계를 구성하고 있느냐이다. 그러므로 우리 시스템 역시 state representation의 기본 단위를 픽셀이 아니라 object와 object 관계로 잡아야 한다.

세 번째 원칙은 planning의 시점을 조심해야 한다는 것이다. dynamics를 모르는 상태에서 planning을 한다는 것은 사실상 blind search에 가깝다. 어떤 action이 어떤 결과를 낳는지 모르는 상태에서 “정답까지의 경로”를 찾는다는 것은 개념적으로 모순이다. 그래서 초기 몇 step의 목적은 해결이 아니라 이해여야 한다. 초반에는 solve-oriented planning보다 information-seeking experimentation이 우선한다. 이 구분을 명확히 하지 않으면, 시스템은 문제를 푼다기보다 허공에 행동을 던지는 상태에 머물게 된다.

## ARC-AGI-3를 world model 문제로 본다는 것의 의미

ARC-AGI-3를 world model 문제로 본다는 말은 단순히 “다음 frame을 예측하자”는 뜻이 아니다. 오히려 그보다 더 구조적인 것을 요구한다. 내가 보기에 여기서 필요한 world model은 full 64x64 reconstruction 모델이 아니다. 우리는 굳이 다음 프레임의 모든 픽셀을 처음부터 끝까지 정확히 그려내는 모델을 만들 필요가 없다. 더 중요한 것은 어떤 object가 action의 영향을 받는지, 그 영향이 이동인지 회전인지 토글인지 소멸인지 생성인지, 관계 변화인지 내부 상태 변화인지, 그 결과 목표에 가까워졌는지를 예측할 수 있는 모델이다. 다시 말해 world model은 raw pixel simulator가 아니라 object transition predictor여야 한다.

이 차이는 매우 크다. 픽셀 예측기를 만들면 시스템은 변화의 원인보다 결과의 외형에 집착하기 쉽다. 하지만 object transition predictor를 만들면 시스템은 자연스럽게 causal structure를 추적하게 된다. 예를 들어 어떤 action을 했을 때 특정 색 object만 오른쪽으로 한 칸 이동하고 나머지는 그대로라면, 중요한 것은 “오른쪽으로 한 칸 이동한 픽셀 셋”이 아니라 “이 object는 controllable하며 이 action은 horizontal displacement를 유발한다”는 설명이다. ARC-AGI-3에서 planning이 가능해지려면 바로 이 수준의 설명이 먼저 필요하다.

이런 world model은 거대한 사전학습 모델처럼 대량의 dynamics 데이터를 미리 먹고 만들어지는 것과는 성격이 다르다. 오히려 하나의 문제를 푸는 과정에서 급속히 형성되는 작은 이론에 가깝다. 관측은 적고, 규칙은 처음엔 모르며, 실험은 비용이 있다. 그러므로 이 world model은 완성된 모델이 아니라 계속 수정되는 working theory여야 한다. 중요한 것은 그것이 틀릴 수 있다는 사실을 전제로 설계하는 것이다. 우리는 한 번 세운 설명을 끝까지 붙드는 것이 아니라, action 이후 예상 밖 현상이 나왔을 때 기존 가설을 수정하고 confidence를 업데이트할 수 있어야 한다. 이 유연함은 월드 모델의 부차적 성질이 아니라 핵심 성질이다.

## Core Knowledge를 실제 설계 원리로 바꾸기

이 프로젝트에서 말하는 prior knowledge는 막연한 상식이 아니다. 적어도 기본 수준에서는 Spelke와 Kinzler의 core knowledge 프레임이 꽤 직접적인 힌트를 준다. 세계는 object의 집합으로 이루어져 있고, object는 공간적 성질을 가지며, object들은 충돌하거나 지지되거나 정렬되거나 분리되며, 어떤 object는 행위 주체처럼 보일 수 있다. 이 수준의 prior만으로도 우리는 초기 해석 공간을 상당히 줄일 수 있다.

예를 들어 장면 속 반복되는 connected component들을 object로 본다는 것은 objectness prior의 적용이다. 떠 있는 물체가 아래 빈 공간과 함께 나타날 때 “중력이나 지지 관계가 있을 수 있다”고 의심하는 것은 basic physics prior의 적용이다. 하나의 salient object가 있고 나머지가 구조물처럼 보일 때 그 object를 controllable avatar 후보로 두는 것은 agentness prior의 적용이다. 이 priors는 정답을 직접 알려주지 않지만, 아무것도 모르는 상태에서 시작하는 것보다 훨씬 생산적인 가설 공간을 준다.

중요한 점은 이 priors를 교조적으로 믿지 않는 것이다. core knowledge는 초기 bias이지 최종 설명이 아니다. 어떤 문제는 보기엔 navigation처럼 생겼지만 사실은 toggle puzzle일 수 있고, 보기엔 gravity-like해 보여도 실제로는 action-triggered teleport일 수도 있다. 그러므로 prior는 hypothesis initialization을 돕는 역할을 할 뿐, 반증되면 빠르게 철회할 수 있어야 한다.

## 인간이 초반에 헛발질을 줄이는 진짜 방법: analogy와 motif

여기서 아주 중요한 것이 나온다. 인간은 새 게임을 볼 때 빈 머리로 시작하지 않는다. 이미 알고 있는 다른 게임, 퍼즐, 동영상, 애니메이션, GIF, 장난감, 물리 장면들을 머릿속에서 끌어와 현재 장면과 비교한다. “이건 소코반 같다”, “이건 스위치를 눌러 문이 열리는 구조 같다”, “이건 레이저가 반사되는 장면 같다”, “이건 중력 퍼즐처럼 보인다”, “이건 적을 피해 목표까지 가는 구조 같다” 같은 감각이 바로 그 예다. 그리고 사람은 이 analogy를 바탕으로 초반에 가장 정보량 높은 행동을 고른다. 다시 말해 인간이 초반 헛발질을 줄이는 이유는, 장면을 곧바로 하나의 motif나 genre 후보에 매핑하고 그에 맞는 probing action을 선택하기 때문이다.

나는 이것이 ARC-AGI-3에서 매우 중요하다고 본다. 왜냐하면 online world-modeling만으로도 문제를 풀 수는 있겠지만, 초기 탐색의 비용이 너무 클 수 있기 때문이다. 초반 몇 step은 정보량이 낮은 행동을 반복하면 곧바로 낭비가 된다. 그런데 motif prior를 쓰면 처음부터 비교적 좋은 가설 공간에서 출발할 수 있다. 예를 들어 장면이 하나의 player-like object, 하나의 target-like object, 정적 장애물 구조로 보인다면 navigation motif를 상위 후보로 둘 수 있다. 반대로 object는 거의 고정돼 있고 일부 색상만 on/off처럼 바뀐다면 toggle motif를 의심할 수 있다. 여러 object가 특정 위치에서 합쳐지거나 쪼개지는 양상이라면 assembly motif가 유력할 수 있다.

이때 motif는 정답 규칙이 아니라 초기 설명 프레임이다. 즉 motif는 “이 게임은 본질적으로 무엇이다”를 선언하는 것이 아니라 “현재 내가 세계를 어떤 장르로 가정하고 출발할 것인가”를 정하는 장치다. 이 distinction이 중요하다. motif를 정답처럼 취급하면 오히려 오판을 고착화할 수 있기 때문이다. motif는 언제나 반증 가능한 형태로 유지되어야 한다.

## motif prior가 왜 강력한가

motif가 강력한 이유는 픽셀보다 더 추상적인 구조를 포착하기 때문이다. 한 장면이 정확히 같은 픽셀을 가져야만 같은 종류의 문제인 것은 아니다. 소코반류 문제는 플레이어의 색이 무엇인지, 벽의 모양이 어떤지, grid가 얼마나 큰지와 상관없이 “조작 가능한 object가 있고, passive movable block이 있으며, 충돌과 위치 제약이 중요하다”는 구조를 공유한다. toggle puzzle 역시 배경색과 object 모양이 달라도 “동일 action 반복 시 reversible change가 일어난다”는 구조를 공유한다. navigation, gravity, switch-door, reflect, merge-split, fill, symmetry completion 같은 motif들은 각각 장면의 본질적인 causal grammar를 요약한다.

따라서 motif는 세계를 category 수준에서 빠르게 설명해주는 추상 장치다. 이 추상성 덕분에 적은 데이터로도 유용한 bias를 줄 수 있다. 그리고 그 bias는 곧바로 probe 설계로 이어질 수 있다. navigation motif가 높으면 방향 action을 먼저 시험하는 것이 자연스럽고, toggle motif가 높으면 동일 action 반복 실험이 먼저 떠오르며, click semantics가 의심되면 중심, 경계, 빈 공간에 대한 좌표 click 비교가 우선 과제가 된다. 이렇게 보면 motif retrieval의 출력은 단순 label이 아니라 “무슨 실험을 먼저 해볼 것인가”에 대한 힌트다.

## motif catalog를 어떻게 구성할 것인가

motif catalog는 처음부터 완벽할 필요는 없지만, 적어도 주요 장르적 구조를 덮는 기본 집합은 필요하다. 예를 들어 하나의 salient object가 target-like object와 장애물 사이를 이동해야 하는 구조는 navigation 혹은 reachability motif로 묶을 수 있다. 플레이어와 movable block, 통로와 벽, 위치 제약이 핵심이면 sokoban 혹은 push-pull motif가 된다. floating object와 빈 공간, 수직적 변화, support 관계가 두드러지면 gravity나 falling motif가 유력하다. 장면의 구조는 유지되는데 일부 상태만 on/off처럼 바뀌고 동일 action 반복이 의미 있어 보이면 toggle motif를 고려할 수 있다. 어떤 object가 선행 조건 역할을 하고 다른 object의 통과 가능 여부나 상태를 바꾸는 구조라면 key-door 혹은 dependency unlock motif가 적합하다. 직선적 전파, 방향성, 반사, 차단이 중심이면 reflect나 laser propagation motif가 가능하다. object count가 줄거나 늘고, 가까워질 때 합쳐지거나 특정 action에서 분할된다면 assembly, merge, split motif를 생각할 수 있다. 특정 영역 전체의 색이나 상태가 바뀌면 paint, fill, region editing motif가 보이고, 대칭성과 패턴 결손이 중심이면 symmetry completion motif가 유력하다.

중요한 것은 이 catalog가 단지 이름 모음이 아니라, 각 motif별로 어떤 observable feature가 중요한지, 어떤 initial hypothesis template를 만들어야 하는지, 그리고 어떤 probing action이 가장 정보량이 큰지를 같이 담아야 한다는 점이다. motif는 결국 hypothesis bank를 생성하는 템플릿이자 probe generator이기 때문이다.

## motif retrieval은 어떻게 이루어져야 하는가

motif retrieval의 입력은 raw grid 전체여서는 안 된다. motif retrieval은 object-centric scene summary를 입력으로 삼는 편이 훨씬 낫다. 예를 들어 배경 후보 색, 색별 object count, bounding box 크기 분포, 연결성 패턴, symmetry score, adjacency graph, 빈 공간의 topology, available actions profile 같은 것이 더 좋은 특징이 된다. 이렇게 하면 retrieval은 “픽셀 패턴이 비슷한가”가 아니라 “구조가 비슷한가”를 보게 된다.

또한 motif retrieval의 출력은 top-1 하나만 선택하는 방식보다는 top-k 후보를 유지하는 방식이 적절하다. 하나의 motif만 고르면 초기 오판 비용이 너무 크다. 예를 들어 어떤 장면에 대해 navigation 0.41, toggle 0.28, assembly 0.17처럼 유지할 수 있다면, 그 뒤의 probing policy도 훨씬 안정적이 된다. navigation을 검증하는 행동을 하되, 결과가 별로면 즉시 toggle 가설로 넘어갈 수 있기 때문이다. 결국 motif retrieval은 분류라기보다 prior distribution을 만드는 과정이라고 보는 편이 정확하다.

## motif와 hypothesis bank의 관계

motif는 planning으로 바로 들어가는 것이 아니라 hypothesis bank의 초기 조건을 만들어야 한다. 예를 들어 navigation motif가 강하면, 초기 hypothesis bank 안에는 “controllable avatar가 존재한다”, “방향성 action이 semantics를 가질 가능성이 높다”, “장애물과의 충돌이나 목표와의 접촉이 중요하다” 같은 가설이 들어갈 수 있다. toggle motif가 높다면 “동일 action 반복 시 reversible change가 나타날 가능성”, “장면 전체 재배치보다 object-local state change가 중요할 가능성”, “active/inactive mode가 존재할 가능성” 같은 가설이 초기값이 된다. assembly motif가 강하면 “object proximity가 중요하다”, “merge 또는 split의 전제 조건이 존재한다”, “개수 변화가 관측의 핵심이다” 같은 가설이 자연스럽게 올라온다.

즉 motif는 장르 추정이고, hypothesis는 구체 규칙 추정이다. motif가 “이건 어떤 세계 같다”를 말한다면, hypothesis는 “그러면 ACTION3는 이런 의미일 수 있다”를 말한다. 이 둘은 위계가 다르다. 좋은 시스템은 motif에서 hypothesis로 자연스럽게 내려가고, 관측 결과가 쌓이면 다시 hypothesis가 motif confidence를 수정하도록 만들어야 한다.

## 가설은 하나가 아니라 경쟁 집합이어야 한다

ARC-AGI-3에서 가장 위험한 것은 하나의 설명을 너무 빨리 정답처럼 믿는 것이다. 실제로는 대부분의 초기 설명은 부분적으로만 맞고, 몇 step 지나면 깨진다. 그래서 hypothesis bank는 최소한 경쟁 가설들의 집합이어야 한다. ACTION1이 left move일 수도 있고, mode toggle일 수도 있고, 특정 object activate일 수도 있다. 특정 object가 플레이어처럼 보일 수도 있지만 사실은 키일 수도 있다. 특정 색이 배경처럼 보여도 실제로는 latent state의 표시일 수 있다. 그러므로 시스템은 한 번에 하나의 설명을 채택하는 대신, 여러 설명을 병렬로 유지하면서 각 설명의 confidence를 step마다 갱신해야 한다.

이 구조는 단지 안정성을 높이는 용도가 아니다. planning 자체가 이 위에서 더 잘 작동한다. 여러 가설이 공존하면, 우리는 “이 세 가설을 가장 빨리 갈라놓는 행동이 무엇인가”를 물을 수 있다. 이 질문이 바로 epistemic planning이다. 반면 가설이 하나뿐이면, 시스템은 자기 자신의 설명을 검증하기보다 정당화하려 들 가능성이 높아진다.

## world model의 진짜 업데이트 규칙

world model은 static object가 아니라 belief state다. 각 step마다 우리는 관측 전 예측을 가지고 있어야 하고, action 이후의 실제 변화와 비교하여 belief를 수정해야 한다. 이 비교에서 중요한 것은 “틀렸다”는 사실 자체가 아니라 “어디가 틀렸는가”를 분해하는 것이다. object identity가 잘못되었는지, controllable object 추정이 잘못되었는지, action semantics가 틀렸는지, hidden state의 존재를 놓쳤는지, 혹은 목표 해석 자체가 틀렸는지 구분해야 한다. 이 분해가 있어야 다음 가설 업데이트도 생산적이 된다.

예를 들어 어떤 action을 했을 때 예상한 object는 그대로 있고 전혀 다른 object가 바뀌었다면, action semantics보다는 object salience 해석이 틀렸을 가능성이 크다. 반대로 같은 object가 바뀌기는 했지만 예상과 다른 방향으로 움직였다면 semantics의 방향성 추정이 틀렸을 수 있다. 아무것도 안 바뀌었다면 action이 invalid였거나 전제조건이 필요했을 수 있다. 전혀 예상치 못한 scene-global 변화가 일어났다면 local physics보다는 global mode change나 trigger rule을 의심해야 한다. 좋은 world model update는 이렇게 오류를 부분 구조로 분해하고, 그에 맞춰 가설을 수정한다.

## planning을 두 단계로 나눠야 하는 이유

planning은 처음부터 정답 경로 탐색으로 시작하면 안 된다. 더 생산적인 방식은 planning을 epistemic planning과 instrumental planning으로 나누는 것이다. epistemic planning의 목적은 세계를 더 잘 이해하는 것이다. 다시 말해, 어떤 action을 해야 현재 경쟁 중인 가설들이 빠르게 갈라지는가, 어떤 개입이 action semantics를 가장 잘 드러내는가, 어떤 위치 클릭이 click semantics를 가장 잘 설명해주는가를 묻는다. 반면 instrumental planning의 목적은 현재 세계 모델을 이용해 목표 상태로 가는 것이다. 이 두 planning은 보상 함수가 다르다. 전자는 정보 획득량이 중요하고, 후자는 progress와 success가 중요하다.

ARC-AGI-3 같은 환경에서는 초반 몇 step 동안 epistemic planning이 우세해야 한다. world model이 아직 형성되지 않은 상태에서 instrumental planning만 하면 시스템은 자주 의미 없는 반복에 빠진다. 반대로 충분한 가설 안정화 없이 exploration만 계속해도 action budget을 낭비한다. 그래서 중요한 것은 둘 사이의 전환 조건이다. controllable object가 어느 정도 식별되었고, action semantics 후보가 일정 수준 이하로 줄었고, 예측 정확도가 몇 step 연속 만족스러울 때 비로소 solve-oriented planning의 비중을 높이는 것이 좋다.

## sk48에 이 구조를 적용한다면

sk48을 실제로 다룬다고 상상해보자. 처음 해야 할 일은 정답 action sequence를 찾는 것이 아니라 scene을 language로 바꾸는 것이다. 배경색은 무엇인지, foreground object는 몇 개인지, 반복 구조는 있는지, 어떤 object가 독립적으로 움직일 수 있을 법한지, 어떤 관계가 장면에서 두드러지는지부터 요약해야 한다. 그다음 이 장면이 어떤 motif들과 닮았는지 상위 몇 개 후보를 세운다. navigation인지, toggle인지, assembly인지, 혹은 완전히 다른 구조인지 추정한다. 그리고 그 motif 후보들을 가장 빠르게 반증하거나 강화할 수 있는 action을 고른다.

중요한 것은 이 action이 “정답에 가까운 행동”일 필요가 없다는 점이다. 오히려 “가장 정보량 높은 행동”인 편이 낫다. 같은 action을 두 번 반복해 reversible한지 보는 것, object 중심과 빈 공간을 각각 클릭해 click semantics를 확인하는 것, 방향 action들을 모두 짧게 시도해 controllable object가 있는지 보는 것, 이 모든 것은 solve action이라기보다 probe action이다. 하지만 이런 probe가 있어야 이후 world model과 planner가 정교해진다.

행동을 하고 나면 반드시 그 변화를 설명하는 가설을 다시 써야 한다. 어떤 object가 바뀌었는지, 그 변화는 이동인지 토글인지 생성인지, 이 결과는 현재 motif 후보들 중 누구를 지지하는지, 그리고 confidence는 어떻게 달라졌는지를 기록해야 한다. 이 기록은 단지 디버깅용이 아니라, 나중에 작은 모델에 이식할 training signal의 핵심이 된다. raw action log만으로는 작은 모델이 “왜 그런 행동을 했는지”를 배우기 어렵지만, motif, hypothesis, prediction, surprise, revision이 함께 기록되면 훨씬 정보 밀도가 높다.

## Harness는 어떤 구조여야 하는가

앞으로 구현할 harness는 단순히 game loop를 감싸는 수준이면 부족하다. 적어도 scene analysis, motif retrieval, hypothesis management, prediction, planning이 모듈처럼 분리돼 있어야 한다. scene analyst는 현재 frame을 object와 관계로 요약하는 일을 맡고, motif retriever는 그 요약을 바탕으로 상위 장르 가설과 probe suggestion을 낸다. mechanism builder는 최근 action과 diff를 보고 local rule을 만든다. skeptic은 그 local rule을 깨뜨릴 수 있는 action을 제안한다. planner는 현재 belief state 아래에서 다음 행동을 정한다. 이 역할 분리는 반드시 여러 모델을 병렬로 돌리겠다는 뜻은 아니다. 오히려 나중에 단일 모델이나 작은 모델로 압축하더라도, 내부 논리 구조를 명확히 하기 위해서라도 필요하다.

여기서 기존의 Claude harness 문서를 다시 떠올려 보면, 그 문서가 강한 부분과 아직 더 강화될 수 있는 부분이 분명하게 구분된다. 강한 부분은 “두뇌와 손을 분리한다”는 점이다. 즉 `harness.py`가 환경과의 상호작용을 담당하고, 상위 에이전트가 이를 해석하며, 필요할 때 다시 실행하는 구조는 매우 실용적이다. 또한 액션을 하나씩 분리해 테스트하고 diff를 관찰하는 프로토콜도 훌륭하다. 이것만으로도 무작정 end-to-end policy를 학습시키는 접근보다 훨씬 더 인간적인 문제 풀이 절차에 가깝다. 그러나 사람의 실제 적응 과정을 더 세밀하게 생각해보면, explorer, modeler, executor 정도의 분해만으로는 아직 부족하다. 사람은 새로운 게임을 접했을 때 단지 관찰하고, 설명을 만들고, 실행하는 세 단계만 거치지 않는다. 그보다 앞에서 “무엇이 중요해 보이는지”를 고르고, 지금 보고 있는 장면이 어떤 익숙한 세계와 닮았는지 떠올리고, 어느 가설이 가장 취약한지 감지하고, 어떤 실험이 정보량이 높은지 계산하며, 예상 밖 현상이 나타났을 때 무엇을 버리고 무엇을 유지할지 빠르게 정리한다. 즉 인간의 적응은 단순한 loop가 아니라 attention, analogy, uncertainty, surprise, memory, replanning이 얽힌 복합 loop다.

그래서 앞으로의 harness는 단순한 실행기보다 “새로운 게임에 적응하는 정신 구조”를 더 많이 내장해야 한다. 내가 보기에 첫 번째로 추가되어야 할 것은 perceptual canonicalizer다. 사람은 화면을 볼 때 매번 raw pixel을 같은 무게로 보지 않는다. 시야를 정리하고, 배경을 무시하고, 반복되는 장식과 기능적 오브젝트를 분리하며, scene을 자기 나름의 표준 형식으로 바꾼다. 이를 코드로 옮기면, 현재 프레임을 object list, relation graph, background mask, active region, display region, probable controllable object 후보 등으로 정규화하는 전처리 계층이 필요하다. 이 계층이 있어야 이후의 motif retrieval도 안정되고, step마다 약간씩 흔들리는 관측을 같은 의미 단위로 비교할 수 있다.

두 번째로 필요한 것은 object persistence tracker다. 사람은 한 번 본 오브젝트를 다음 프레임에서도 같은 존재로 추적하려고 한다. 위치가 바뀌거나 모양이 약간 변해도 “아까 그 물체가 움직였구나”라고 이해하지, 매 프레임마다 전혀 새로운 물체 집합으로 세계를 다시 파악하지 않는다. 그런데 현재의 많은 하네스는 사실상 frame-to-frame diff 중심으로만 사고한다. 이것만으로는 어떤 변화가 동일 object의 이동인지, 파괴 후 재생성인지, 혹은 단순 시각 효과인지 분간하기 어렵다. 따라서 object identity를 시간축으로 유지하고, 합쳐짐과 쪼개짐, 가려짐과 재등장 같은 사건도 설명할 수 있는 persistent tracker가 필요하다. 이 컴포넌트는 나중에 world model이 “무엇이 변했는가”뿐 아니라 “무엇이 계속 같은 존재였는가”를 설명하도록 만들어 준다.

세 번째로 강화해야 할 것은 attentional controller다. 사람은 새로운 게임을 접하면 장면 전체를 균등하게 읽지 않는다. 제일 눈에 띄는 움직일 것 같은 물체, 반복적으로 등장하는 표식, 하단의 디스플레이 영역, 목표처럼 보이는 박스, 혹은 방금 변화가 집중된 국소 영역에 주의를 더 준다. 이 선택적 주의는 굉장히 중요하다. 이유는 정보 처리량이 제한되어 있기 때문이다. AI 하네스도 마찬가지다. 모든 셀을 항상 같은 중요도로 다루면 reasoning이 금방 희석된다. 따라서 현재 belief state 아래에서 “지금 가장 봐야 할 영역은 어디인가”, “어떤 object pair의 관계가 핵심인가”, “action 이후 어느 subgrid를 중점 비교해야 하나”를 정하는 attention scheduler가 있어야 한다. 이것은 단지 속도 최적화용이 아니라, 본질적으로 인간형 문제 해결의 중요한 일부다.

네 번째로는 analogy retriever와 motif librarian을 더 명시적으로 분리할 필요가 있다. 지금 문서에도 motif prior가 중요하다고 적어 두었지만, 앞으로 agentic-framework로 구현을 분담하려면 “motif catalog를 저장하는 계층”과 “현재 scene을 그 catalog와 비교해 어떤 motif를 소환할지 결정하는 계층”을 따로 보는 편이 좋다. 사람은 새로운 문제를 만났을 때 즉시 기존 경험 전체를 검색한다. 하지만 그 검색은 무질서한 자유연상이 아니라, 현재 scene의 salient pattern에 의해 유도된다. 따라서 motif librarian은 정적인 지식 저장소에 가깝고, analogy retriever는 현재 관측을 받아 가장 그럴듯한 motif 몇 개와 그 이유를 제안하는 동적인 검색기여야 한다. 이 분리가 있으면 나중에 작은 모델에게도 “catalog는 코드/데이터로 두고, retriever만 모델이 담당”하게 설계할 수 있다.

다섯 번째로는 affordance mapper가 필요하다. 인간은 어떤 게임을 볼 때 단지 “이게 무엇인지”만 보지 않고, “이걸 건드릴 수 있나”, “이건 밀릴 수 있나”, “이건 통과 가능할까”, “이 표시는 클릭 대상으로 보이나”, “이 행동은 어디에 적용될까” 같은 조작 가능성을 함께 추정한다. 이것이 affordance다. ARC-AGI-3에서 action semantics를 빠르게 이해하려면 오브젝트의 정체만큼이나 조작 가능성 지도도 중요하다. 예를 들어 특정 object는 player일 가능성은 낮아도 trigger plate일 가능성은 높을 수 있다. 특정 빈 공간은 단순 배경이 아니라 click target일 수 있다. 어떤 벽은 collision wall이지만 어떤 테두리는 출입 가능한 gate일 수 있다. 이러한 affordance를 추정하고 갱신하는 모듈이 있으면, action 후보를 훨씬 더 인간답게 좁힐 수 있다.

여섯 번째로는 goal inferencer를 더 전면에 내세워야 한다. 기존 harness 문서는 액션 효과 매핑과 탐색 프로토콜을 잘 설명하지만, “무엇이 목표 상태인가”를 독립된 추론 문제로 다루지는 않는다. 그런데 사람은 새로운 게임을 볼 때 조작 규칙만 배우는 것이 아니라, 동시에 무엇이 성공의 신호인지 계속 추측한다. 점수 표시, 박스 구조, 상단 타겟, 색상 일치, object count 감소, 특정 영역 진입, 레벨 전환 등은 모두 목표 추론의 단서다. goal inferencer는 단순한 win detector가 아니라, 아직 클리어하지 못한 상태에서도 “지금 어떤 latent objective가 유력한가”를 계속 갱신하는 계층이어야 한다. 이 계층이 약하면 planner는 아무리 정교해도 엉뚱한 방향으로 최적화될 수 있다.

일곱 번째로는 experiment designer가 매우 중요하다. 사람은 낯선 게임을 배울 때 모든 행동을 랜덤으로 시도하지 않는다. 대개는 “가장 적은 비용으로 가설을 많이 가를 수 있는 실험”을 먼저 한다. 같은 버튼을 두 번 눌러 reversible한지 보는 것, player처럼 보이는 object 근처와 완전 빈 공간을 비교 클릭하는 것, obstacle 앞에서 이동 action을 써보는 것, 동일 action을 다른 위치에서 반복해 context sensitivity를 보는 것 등이 전형적인 예다. 이 능력을 명시적으로 agent화하면 explorer가 단순 수집자에 그치지 않고, information gain maximizer가 된다. 내가 보기에는 ARC-AGI-3 같은 과제에서는 solve planner 못지않게 experiment designer가 중요하다. 초반 10 step의 품질이 이후 전체 trajectory의 품질을 좌우하기 때문이다.

여덟 번째로는 surprise monitor와 belief auditor가 필요하다. 사람은 어떤 현상이 예상과 다르게 나오면 단순히 “틀렸다”에서 멈추지 않는다. 어느 층위의 설명이 어긋났는지 가늠한다. 내가 object를 잘못 봤는지, action semantics를 오해했는지, hidden mode를 놓쳤는지, 혹은 목표 해석이 틀렸는지 분해하려고 한다. 이 역할을 코드와 agent 구조에 넣으려면, 예측과 실제 결과의 차이를 받아 그 차이가 어떤 belief node를 공격하는지 해석하는 surprise monitor가 있어야 한다. 그리고 belief auditor는 현재 유지 중인 motif, hypothesis, affordance, goal assumption 각각의 confidence를 재조정해야 한다. 이런 구조가 있으면 시스템은 예상 밖 현상을 단순 noise가 아니라 학습 신호로 사용할 수 있다.

아홉 번째로는 phase manager가 필요하다. 사람의 적응은 exploration, modeling, exploitation이 뒤섞여 있긴 하지만, 그렇다고 항상 같은 비율로 유지되지는 않는다. 어떤 시점에는 더 관찰이 필요하고, 어떤 시점에는 이미 충분히 안다고 보고 계획 실행에 집중하며, 어떤 시점에는 실패 후 다시 탐색 모드로 후퇴한다. 지금까지의 문서에서는 이 전환이 주로 직관적으로 표현돼 있지만, 실제 framework로 나눌 때는 “지금은 epistemic mode인가, instrumental mode인가, recovery mode인가”를 관리하는 메타 컨트롤러가 필요하다. 이 컴포넌트는 전체 action budget, 남은 에너지, hypothesis entropy, 최근 예측 정확도, level progression 같은 신호를 보고 상위 전략 모드를 바꾼다. 이것이 있어야 한쪽 모드에 과도하게 갇히는 문제가 줄어든다.

열 번째로는 subgoal compiler와 execution monitor의 결합이 필요하다. 사람이 계획을 세울 때는 단순히 전체 정답 시퀀스를 머릿속에 한 번에 적는 것이 아니라, 중간 목표를 만든다. “먼저 저 물체까지 가자”, “그 다음 스위치를 한 번만 작동시키자”, “이 상태를 만든 뒤 타겟 박스로 이동하자” 같은 식이다. ARC-AGI-3에서도 dynamics가 어느 정도 파악된 후에는 긴 행동열을 곧장 실행하기보다, 하위 목표를 생성하고 각 하위 목표 달성 여부를 중간중간 검증하는 구조가 더 안정적이다. subgoal compiler는 현재 world model과 goal belief를 받아 실행 가능한 단기 목표를 만든다. execution monitor는 그 목표가 계획대로 진행되는지, drift가 생겼는지, 즉시 재계획이 필요한지를 본다. 이 둘이 없으면 planner의 산출은 쉽게 brittle해진다.

열한 번째로는 episode memory와 cross-game memory를 구분해야 한다. 사람은 현재 게임 안에서 방금 본 것을 기억할 뿐 아니라, 예전에 했던 다른 게임에서 얻은 구조적 통찰도 소환한다. 따라서 memory는 적어도 두 층이 필요하다. episode memory는 현재 문제 내부에서의 누적 관측, 액션 결과, 가설 변경 이력을 보존한다. cross-game memory는 motif, 자주 등장하는 affordance, 목표 패턴, 실패 모드, 유용했던 probe 전략 같은 메타 지식을 축적한다. 전자는 sk48을 푸는 데 직접 쓰이고, 후자는 다음 게임에서 더 좋은 초기 bias를 제공한다. 나중에 Qwen 4B 같은 모델로 distill할 때도, 실제로 전이하고 싶은 것은 주로 이 cross-game memory의 구조다.

열두 번째로는 trajectory curator와 teacher module이 필요하다. 지금까지의 문서들은 주로 “어떻게 풀 것인가”에 초점을 맞추고 있지만, 우리는 동시에 “이 과정을 나중에 작은 모델이 배울 수 있도록 어떻게 남길 것인가”도 설계해야 한다. 사람은 어떤 문제를 풀고 나면 단순히 행동열만 기억하지 않고, 중요한 전환점과 핵심 깨달음을 압축된 이야기 형태로 정리할 수 있다. 마찬가지로 시스템도 raw logs만 저장해서는 안 되고, 어떤 motif가 초기 후보였는지, 언제 버려졌는지, 어떤 실험이 가장 많은 정보를 주었는지, 어떤 예측 실패가 가설 전환을 촉발했는지, 최종적으로 어떤 세계 설명이 살아남았는지를 고밀도 trajectory로 남겨야 한다. trajectory curator는 이런 요약 데이터를 만들고, teacher module은 이를 이후 SFT나 preference tuning에 맞는 supervision 형태로 바꾸는 역할을 맡는다.

이렇게 보면 앞으로의 agentic framework는 단순한 세 agent 구조보다 더 세분화된 인지 생태계에 가깝다. scene analyst, object tracker, attention controller, motif retriever, affordance mapper, goal inferencer, experiment designer, mechanism builder, surprise monitor, belief auditor, phase manager, subgoal compiler, execution monitor, memory curator, teacher module이 서로 대화하는 구조를 상상할 수 있다. 물론 실제 구현에서는 이 중 일부가 하나의 프로세스로 합쳐질 수도 있고, 어떤 것은 코드 라이브러리로, 어떤 것은 LLM agent로, 어떤 것은 deterministic heuristic으로 남을 수 있다. 중요한 것은 이름을 많이 만드는 데 있는 것이 아니라, 인간의 적응 과정을 자세히 분해했을 때 무엇이 빠져 있는지 인식하고, 그 빠진 기능을 명시적으로 시스템 설계 안으로 끌어오는 데 있다. 그래야 이후에 “어떤 agent에게 무엇을 구현시킬 것인가”라는 분업 설계도 자연스럽게 생긴다.

## 작은 모델에 이식할 때 무엇을 남기고 무엇을 가르칠 것인가

Qwen 4B 같은 작은 모델에게 이 능력을 옮기려고 할 때 가장 먼저 버려야 할 환상은 “full grid in, perfect action out”이다. 작은 모델에게 모든 것을 맡기기보다, perception과 explicit state tracking, 일부 search는 코드가 강하게 맡고, 모델은 hypothesis manager와 reranker 역할을 맡는 편이 훨씬 현실적이다. 예를 들어 object extraction과 connected component 분석, geometry features, relation graph 구축, scorecard 로깅과 canonical evaluation loop는 코드로 두는 것이 좋다. 반면 모델은 scene summary를 읽고 motif 후보를 제안하거나, 최근 몇 step의 action/result를 보고 가설 confidence를 업데이트하거나, 현재 가설들 아래에서 가장 정보량 높은 probing action을 제안하거나, solve phase에서 후보 action들을 rerank하는 역할을 맡을 수 있다.

이 관점은 distillation에도 유리하다. 작은 모델에게 “세계를 완전히 시뮬레이션하라”고 요구하는 대신, “scene summary를 읽고 현재 motif를 추정하라”, “이 관측은 기존 가설 중 무엇을 약화시키는가”, “다음 한 step을 정보 획득 관점에서 고르라” 같은 형태로 학습시키면 훨씬 compact한 supervision이 가능해진다.

## 검증은 항상 canonical path로 돌아와야 한다

실험용 harness와 실제 scorecard 경로는 같아 보여도 미묘하게 다를 수 있다. 이번에 scorecard URL 문제를 겪으면서 더 분명해졌듯이, custom runner로 얻은 결과는 debugging에는 유용하지만, 반드시 canonical path에서 다시 검증해야 한다. 그렇지 않으면 로컬에서 본 행동과 서버가 기록한 행동, 실험용 score summary와 웹에서 보이는 scorecard, 나중의 Kaggle notebook 동작이 서로 어긋날 수 있다. 따라서 탐색과 debugging은 커스텀 harness에서 하더라도, 중요한 milestone마다 `main.py`나 실제 제출 경로처럼 공식 엔트리포인트로 다시 확인하는 절차가 필요하다.

이건 단순히 형식을 지키자는 뜻이 아니다. 우리가 결국 만들고 싶은 것은 hidden environment에서도 작동하는 시스템이기 때문이다. 그러려면 실험 환경과 평가 환경 사이의 분포 차이뿐 아니라 실행 경로 차이도 최대한 줄여야 한다.

## World Model의 구체적 실현: 코드로서의 시뮬레이터

<!-- [Apr 2] Added from tu93 hands-on session insights. -->

위에서 서술한 world model, hypothesis bank, confidence update의 추상적 원칙이 실제 코드와 실행에서 어떻게 구현되는지를 여기서 구체화한다. tu93 게임을 CLI에서 직접 풀어본 실험(2026-04-01)이 이 구체화의 계기가 되었다.

### World Model = Executable Simulator Code

이 문서의 핵심 주장 중 하나인 "world model은 belief state다"를 코드 수준에서 옮기면, **world model은 Python 함수 `simulate(state, action) → next_state`** 다. 이 함수는 처음에는 불완전하고, 경험이 쌓이면서 정교해진다.

```python
# 초기 시뮬레이터 (Level 0, 탐색 4 액션 후)
def simulate_v1(state, action):
    """Confidence: agent_movement=0.95, goal_detection=0.8"""
    agent_new = move_on_graph(state.agent, action, state.walls)  # 확신 높음
    return State(agent_new, state.enemy, state.goal)             # 적 행동 모름

# 개선된 시뮬레이터 (Level 1, 탐색 + 실패 3회 후)
def simulate_v3(state, action):
    """Confidence: agent_movement=0.99, enemy_mirror=0.7, trigger_distance=0.5"""
    agent_new = move_on_graph(state.agent, action, state.walls)
    enemy_new = state.enemy
    if same_row(agent_new, state.enemy) and adjacent(agent_new, state.enemy):
        enemy_new = move_opposite(state.enemy, action, state.walls)  # 가설!
    alive = agent_new != enemy_new
    return State(agent_new, enemy_new, state.goal), alive
```

핵심: **시뮬레이터의 각 줄이 하나의 mechanic hypothesis이고, 각 hypothesis에 confidence가 있다.** 이것이 위에서 말한 "경쟁 가설 집합"의 코드 레벨 구현이다.

### 매 액션마다 시뮬레이터가 어떻게 진화하는가

아래는 tu93 Level 1을 풀면서 시뮬레이터가 실제로 어떻게 변했는지의 로그다. **이런 로그가 모든 게임에서 남아야 한다.**

```
Action #1: ACTION1 (UP)
  Prediction: agent moves up (confidence: 0.95)
  Reality:    agent moved up ✓
  Simulator update: agent_movement confidence → 0.97
  Enemy:      didn't move (no hypothesis yet about enemy)

Action #2: ACTION4 (RIGHT)
  Prediction: agent moves right (confidence: 0.97)
  Reality:    agent moved right ✓, enemy stayed
  Simulator update: none
  New hypothesis: "enemy doesn't react to distant horizontal movement" (conf: 0.3)

Action #3: ACTION4 (RIGHT)
  Prediction: agent moves right, enemy stays (confidence: 0.6)
  Reality:    agent moved right ✓, enemy stayed ✓
  Simulator update: "enemy doesn't react when far" confidence → 0.5

Action #4: ACTION4 (RIGHT)
  Prediction: agent moves right, enemy stays (confidence: 0.5)
  Reality:    GAME_OVER! enemy moved LEFT and collided!
  Simulator update:
    ✗ REJECT "enemy doesn't react when far" (conf: 0.5 → 0.1)
    ✓ NEW "enemy mirrors when agent approaches within ~2 nodes" (conf: 0.6)
    ✓ NEW "collision = death" (conf: 1.0)

--- RESET ---

Action #5-7: UP, RIGHT, RIGHT (following old confident path)
  All predictions correct ✓
  No simulator updates needed

Action #8: DOWN (deviate to avoid enemy row)
  Prediction: agent moves down (confidence: 0.97)
  Reality:    agent moved down ✓
  New info:   enemy didn't move (different row)
  Simulator update: "enemy only reacts on same row" confidence → 0.7

Action #9-10: RIGHT, RIGHT (on safe row, below enemy)
  Both correct ✓

Action #11: UP (entering enemy's column from below)
  Prediction v3: agent enters enemy's position → enemy swaps down (conf: 0.4)
  Prediction v2: agent collides with enemy → death (conf: 0.3)
  Prediction v1: agent moves up normally (conf: 0.3)
  Reality:    agent swapped with enemy! Both alive!
  Simulator update:
    ✓ CONFIRM "column approach causes swap" (conf: 0.4 → 0.8)
    ✗ REJECT "collision on same cell = always death" (conf: 1.0 → 0.6)
    ✓ REFINE "collision from different axis = swap, same axis = death" (NEW, conf: 0.5)

Action #12-14: RIGHT, RIGHT, UP → WIN!
  Simulator correctly predicted all three ✓
```

### 이 로그가 왜 중요한가

이 로그는 세 가지 목적을 동시에 달성한다:

1. **디버깅**: 시뮬레이터가 어디서 틀렸고 왜 틀렸는지 추적
2. **SFT 데이터**: (observation, prediction, reality, update) 튜플이 SLM 훈련 데이터가 됨
3. **Cross-game transfer**: "enemy mirror" 패턴이 다른 게임에서도 나타나면 motif library에 등록

특히 **2번**이 핵심이다. 위 문서에서 "trajectory curator와 teacher module"이라고 부른 것의 구체적 산출물이 바로 이 로그다. raw action log만 남기면 "왜 그 행동을 했는지"를 알 수 없지만, 시뮬레이터 변화 로그가 있으면 **가설의 탄생, 검증, 폐기, 수정**이 모두 기록된다.

### 솔버(Search Algorithm)도 함께 진화한다

시뮬레이터만 바뀌는 것이 아니다. **시뮬레이터의 질에 따라 최적 솔버도 달라진다:**

```
시뮬레이터 v1 (confidence 낮음, 적 행동 모름):
  → 솔버: Greedy 1-step (시뮬레이터를 믿을 수 없으므로 1스텝만 계획)
  → 또는 "epistemic planning" 모드 (정보 수집 우선)

시뮬레이터 v2 (confidence 중간, 적 행동 대략 파악):
  → 솔버: Conservative BFS (높은 confidence 경로만 탐색, 위험한 경로 회피)
  → 불확실한 mechanic을 피하는 "safe path" 선호

시뮬레이터 v3 (confidence 높음, 대부분 mechanic 확인):
  → 솔버: Full MCTS/BFS (시뮬레이터를 신뢰하고 깊은 탐색)
  → 최적 경로를 자신있게 실행
```

이것이 위 문서에서 말한 "phase manager"의 구체적 실현이다. epistemic planning에서 instrumental planning으로의 전환은 **시뮬레이터의 평균 confidence가 임계치를 넘을 때** 일어난다.

### Motif Discovery가 시뮬레이터 초기화를 돕는다

위 문서에서 강조한 motif retrieval이 여기서 빛을 발한다:

```
새 게임 시작:
  Scene analysis → "3x3 블록들이 경로로 연결, 하나가 다른 색" 
  Motif retrieval → navigation (0.7), chase (0.2), toggle (0.1)

navigation motif 시뮬레이터 템플릿 자동 로드:
  def simulate_navigation(state, action):
      agent_new = move_on_graph(state.agent, action, state.walls)
      goal_reached = agent_new == state.goal
      return State(agent_new), goal_reached

chase motif가 확인되면 확장:
  def simulate_navigation_chase(state, action):
      agent_new = move_on_graph(state.agent, action, state.walls)
      enemy_new = chase_behavior(state.enemy, agent_new)  # motif에서 가져온 패턴
      ...
```

motif는 "시뮬레이터의 뼈대"를 제공한다. 경험이 쌓이면서 뼈대에 살이 붙는다.

### Kaggle에서 SLM이 이 모든 것을 해야 한다

인터넷이 없는 Kaggle 환경에서는 **Qwen 3.5 7B (또는 유사 모델)이 위의 전체 루프를 수행**해야 한다:

```
SLM의 역할:
  1. 프레임 관찰 → 엔티티/구조 파악 (scene analysis)
  2. Motif 매칭 → 시뮬레이터 템플릿 선택 (motif retrieval)
  3. 시뮬레이터 코드 생성 (mechanism builder)
  4. 예측 실패 시 시뮬레이터 수정 (surprise monitor + belief auditor)
  5. 시뮬레이터 위에서 계획 (planner)

코드/라이브러리의 역할 (SLM이 안 해도 되는 것):
  1. Object extraction, connected component analysis
  2. BFS/MCTS 탐색 엔진 (시뮬레이터 위에서 실행)
  3. Confidence tracking, observation logging
  4. Motif template library (사전 구축)
  5. Graph structure parsing
```

**핵심**: SLM이 "모든 것"을 하는 게 아니라, **시뮬레이터 코드 생성과 수정**이라는 좁지만 결정적인 역할에 집중한다. 나머지는 코드 라이브러리가 담당한다. 이것이 이 문서에서 말한 "perception과 explicit state tracking은 코드가 강하게 맡고, 모델은 hypothesis manager와 reranker 역할"의 구체적 실현이다.

### 이 능력을 SLM에 이식하기 위한 데이터

위에서 기술한 "매 액션마다의 시뮬레이터 진화 로그"가 바로 SFT 데이터가 된다:

```
Input:  "현재 그리드 요약: agent at (28,26), enemy at (28,36), same row.
         Action: RIGHT. 결과: GAME_OVER, enemy moved to (28,30).
         기존 시뮬레이터: enemy_new = state.enemy (적 안 움직임 가정)"

Output: "시뮬레이터 수정:
         if same_row(agent, enemy) and distance(agent, enemy) <= 3:
             enemy_new = move_opposite(enemy, action)
         Confidence: 0.6 (1회 관찰 기반)"
```

이런 (input, output) 쌍을 공개 25개 게임 × 여러 레벨 × 여러 시행착오로 수집하면, SLM이 "관찰 → 시뮬레이터 수정"을 학습할 수 있다. **이것이 distillation의 핵심 데이터 형태다.**

상세 기술 문서: [simulator-building-approach.md](simulator-building-approach.md)

---

## 최종적으로 무엇을 만들게 될 것인가

이 계획의 끝에는 단순 agent 하나가 아니라 여러 층을 가진 시스템이 있을 것이다. object-centric scene representation이 있고, motif prior library가 있으며, hypothesis bank와 confidence updater가 있고, local world-model predictor와 epistemic/instrumental planner가 있으며, 그 모든 과정을 trajectory로 남겨 작은 모델에게 이식 가능한 데이터로 바꾸는 pipeline이 있다. 그 뒤에야 canonical scorecard 검증이 이루어지고, 마지막으로 Kaggle notebook이라는 제출 가능한 포맷으로 포장된다.

이 모든 것을 한 문장으로 요약하면 다음과 같다. ARC-AGI-3는 “다음 action을 맞히는 문제”가 아니라, “관측 가능한 장면으로부터 세계를 재구성하고, 그 세계가 어떤 익숙한 motif와 닮았는지 불러오고, 그 유사성을 초기 가설로 삼아, action을 개입 실험으로 사용해 world model을 online하게 형성하고, 예상 밖 결과 앞에서 유연하게 설명을 바꾸며, 충분히 확신이 생겼을 때 planning으로 전환하는 문제”다. 내가 만들고 싶은 harness는 바로 그 전 과정을 기계가 수행할 수 있도록 돕는 구조이며, 나중에 작은 모델에 이식될 때도 이 구조를 최대한 잃지 않는 방향으로 정리되어야 한다.
