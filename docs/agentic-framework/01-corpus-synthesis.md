<!-- [Mar 29] Created by SD with GPT-5.4. -->
# 01. Corpus Synthesis

## 왜 코퍼스 종합이 필요한가

개별 harness narrative는 각 게임을 매우 구체적으로 다루지만, framework를 설계하려면 개별 게임의 디테일보다 **여러 문서에서 반복적으로 등장하는 인지 구조**를 먼저 봐야 한다. 이번 종합에서 가장 먼저 눈에 띈 것은, 거의 모든 narrative가 이미 world-model-oriented harness의 씨앗을 갖고 있다는 점이다. Claude는 각 문서에서 scene을 해석하고, motif 후보를 세우고, probe를 설계하고, 복수의 가설을 유지하고, dynamics 의사코드를 쓰고, prediction-verification 루프를 가정하고, surprise와 distillation까지 염두에 두고 있다. 즉 철학은 맞다.

그러나 동시에 대부분의 문서는 아직 “좋은 서술적 실행 계획”에 머물러 있다. 실제 시스템으로 옮길 때 필요한 역할 경계, 상태 표현, 실패 복구 규칙, phase switching, memory hierarchy는 문서마다 암묵적으로만 존재한다. 바로 그 차이를 메우는 것이 framework 설계의 목적이다.

## narrative들에서 반복적으로 보인 공통 골격

첫째, 거의 모든 게임이 `장면 읽기`에서 시작한다. 여기서 배경과 전경, object의 수, 큰 구조물, 이동 경로, 참조 패턴, 에너지 바, 조작 대상 후보를 뽑아낸다. `ls20`은 통로와 플레이어, `sk48`은 다이아몬드와 꼬리, `g50t`는 미로와 트랙, `re86`은 십자형 조준선, `tr87`은 정렬 대상 블록과 컨테이너 프레임을 읽는다. 이 차이에도 불구하고 실제로 필요한 것은 동일하다. raw grid를 object-centric scene description으로 바꾸는 일이다.

둘째, 모든 문서가 `motif 추정`을 한다. 장면을 그냥 픽셀로 보지 않고, navigation, maze, threading, push, toggle, sorting, click-semantics, symmetry 같은 장르 후보에 매핑한다. 이는 인간이 다른 게임이나 퍼즐 경험을 떠올려 현재 문제를 해석하는 방식과 매우 닮아 있다. 다시 말해 Claude narrative들은 이미 analogy-driven initialization을 하고 있다.

셋째, 모든 문서가 `epistemic planning`을 채택한다. 문제를 곧바로 푸는 것이 아니라, 먼저 action semantics를 파악하고, 어떤 실험이 가장 정보량이 높은지 설계한다. 이것은 매우 중요한 강점이다. 특히 `sk48`, `re86`, `g50t`에서 이 경향이 뚜렷하다. 다만 그 정보량 계산은 아직 대부분 서술적 직관에 의존한다.

넷째, 거의 모든 문서가 `복수 가설`을 유지한다. 이것은 매우 건강한 설계다. 단일 설명에 너무 빨리 고정되지 않으려는 태도가 narrative 수준에서 이미 드러난다. 그러나 실제 구현으로 옮기려면 “가설이 몇 개 살아 있어야 하는가”, “어떤 evidence가 어떤 belief node를 약화시키는가”, “언제 kill해야 하는가” 같은 규칙이 더 필요하다.

다섯째, 많은 문서가 `dynamics 코드화`를 상정한다. 즉 단순히 관찰을 서술하는 것이 아니라, 현재까지의 관측을 설명하는 실행 가능한 의사코드를 쓴다. 이것은 ARC-AGI-3 맥락에서 아주 큰 장점이다. Claude가 코드를 잘 쓴다는 사실을 world model 작성 능력으로 활용하려는 방향이기 때문이다.

여섯째, narrative들은 대부분 `surprise`와 `distillation`을 포함한다. 이는 단순히 퍼즐 하나를 푸는 것이 아니라, 그 과정을 나중에 작은 모델에 이식 가능한 학습 데이터로 만들겠다는 관점을 보여준다.

## 게임별로 달라지는 지점

게임에 따라 가장 크게 달라지는 부분은 세 가지였다.

첫째, **조작 가능성의 형태**가 다르다. `ls20`은 전형적인 이동형 avatar에 가깝고, `re86`은 click/coordinate semantics를 의심하게 하며, `tr87`은 container-like agent를 암시하고, `sk48`은 extend/retract 메커닉을 중심에 둔다. 즉 같은 “agent”라고 해도, 어떤 게임에서는 mover이고, 어떤 게임에서는 selector이며, 어떤 게임에서는 manipulator다.

둘째, **목표의 표면 형태**가 다르다. 어떤 게임은 참조 패턴을 제공하고, 어떤 게임은 목표가 공간적 도달이며, 어떤 게임은 정렬, 어떤 게임은 상태 토글, 어떤 게임은 수집이나 제거에 가깝다. 따라서 goal inference는 narrative마다 다루어지지만, 실제 framework에선 별도 계층으로 독립시켜야 한다.

셋째, **중간 목표의 필요성**이 다르다. 단순 이동 게임은 빠르게 solve plan으로 넘어갈 수 있지만, `tr87` 같은 sorting류나 `sk48` 같은 조작 연쇄형은 subgoal structure가 훨씬 중요하다.

## narrative 코퍼스가 보여준 반복적 약점

반복적으로 보인 약점도 있다.

첫째, 많은 문서가 scene을 잘 읽지만 `attention control`을 명시하지 않는다. 사람은 어디를 먼저 볼지, 어떤 오브젝트 쌍이 핵심인지 선택한다. narrative들은 이미 사실상 그 선택을 하고 있으나, 그것을 별도 역할로 드러내지 않는다.

둘째, `object persistence`가 약하다. frame-to-frame diff는 자주 이야기하지만, 동일 object identity를 시간축으로 어떻게 유지할지 명시하지 않는 경우가 많다.

셋째, `affordance inference`가 암묵적이다. 어떤 오브젝트가 밀릴 수 있는지, 클릭 대상인지, 수집 가능한지, gate인지, trigger인지에 대한 추정이 필요하지만, 대부분은 motif나 dynamics에 묻혀 있다.

넷째, `anti-anchoring mechanism`이 부족하다. motif를 잘 세우지만, 틀린 motif를 언제 버릴지에 대한 kill condition이 문서마다 충분히 강하지는 않다.

다섯째, `phase switching`이 명확하지 않다. 탐색에서 해결로, 해결에서 복구로 언제 넘어갈지 직관에 기대는 경우가 많다.

여섯째, `execution monitoring`과 `recovery`가 약하다. 계획이 틀어질 때 즉시 재계획하는 메타 구조가 narrative에는 있지만, 역할 단위로는 분리되어 있지 않다.

## framework 설계에 대한 함의

이 코퍼스는 우리에게 매우 분명한 설계 방향을 준다. 첫째, perception과 hypothesis를 분리해야 한다. 둘째, hypothesis와 planning 사이에 experiment design과 world-model editing 계층을 두어야 한다. 셋째, solve planner 못지않게 surprise auditor와 memory curator가 중요하다. 넷째, 각 narrative는 이미 좋은 문제 풀이 초안이지만, framework는 그 초안을 **재사용 가능한 인지 기능의 집합**으로 다시 써야 한다.

따라서 다음 문서들에서는 이 코퍼스를 바탕으로 역할을 분해한다. 목표는 “문서를 요약하는 것”이 아니라, 이후 구현을 agent 단위로 나눌 수 있도록 각 컴포넌트의 책임, 입력, 출력, 실패 모드, 우선 구현 순서를 분명히 하는 것이다.

