<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 24. Scaffold Exit Checklist

이 문서는 “scaffolding을 언제까지 계속할 것인가”를 감으로 결정하지 않기 위해 만든 전환 체크리스트다. 지금까지 우리는 episode memory, supervisor, night loop, queue policy, trace enrichment, phase-aware scheduling, solve-loop bridge까지 상당한 양의 바깥 구조를 쌓아왔다. 이 작업은 분명 필요했고, 실제로 solver가 더 좋은 artifact를 남기고 밤새 반복 실행될 수 있는 기반을 만들었다. 하지만 ARC-AGI-3의 최종 목표는 어디까지나 문제를 푸는 것이지, orchestration 계층을 끝없이 고도화하는 것이 아니다. 따라서 이제는 “무엇이 아직 scaffolding으로서 꼭 필요한 일인지”와 “언제부터는 solver 개선이 더 높은 가치인지”를 분리해서 봐야 한다.

핵심 원칙은 간단하다. scaffolding은 solver를 더 많이, 더 안정적으로, 더 해석 가능하게 만들어야 한다. 만약 새로운 scaffold가 실제 solve behavior, trajectory quality, distillation quality, unattended stability 가운데 하나라도 개선하지 못한다면, 그 시점부터는 scaffolding이 아니라 구조적 미세 장식에 가까워진다. 이 문서는 바로 그 경계선을 가시화한다.

## A. “Scaffolding을 계속해도 되는” 정당한 이유

아래 항목 중 하나라도 아직 충족되지 않았다면, scaffolding 작업을 더 해도 된다. 다만 이때도 새 컴포넌트를 무조건 늘리기보다, 이미 있는 solver와 outer loop가 더 잘 맞물리도록 seam을 정리하는 방향이어야 한다.

1. solver episode와 bootstrap episode가 같은 manifest/queue/trace 생태계 안에 완전히 수렴하지 않았다.
2. unattended run이 밤새 안정적으로 돌지 않고, 자주 경고·예외·중단 상태로 끝난다.
3. episode artifact는 남지만, 그 artifact가 SFT/distillation용 데이터로 바로 변환되기 어렵다.
4. phase, probe, surprise, hypothesis revision 같은 핵심 신호가 artifact 안에 누락되어 있다.
5. queue policy가 실제 solver progress나 epistemic gain을 거의 반영하지 못한다.
6. seam 테스트가 빈약해서, solver 또는 scaffold 중 한쪽이 바뀌면 자주 깨진다.

즉 scaffolding은 “더 예쁜 구조”를 위해 계속하는 게 아니라, solver가 실제로 일할 수 있도록 하는 최소 운영 조건을 아직 다 못 갖췄을 때만 계속해야 한다.

## B. “이제 scaffold는 충분하다”라고 판단할 최소 기준

아래 기준의 대부분이 맞으면, scaffolding은 이미 최소 작동 골격을 넘긴 것이다. 이때부터는 scaffold를 주력 개발 트랙으로 두지 않는 것이 좋다.

1. queue item 하나가 bootstrap run이든 solve-loop run이든 supervisor를 통해 동일한 manifest 흐름으로 들어온다.
2. episode마다 observation, belief, decision, trace, episode summary가 구조화된 파일로 남는다.
3. phase 정보가 남는다.
   `epistemic`, `instrumental`, `recovery` 또는 그에 준하는 mode가 step/episode 레벨에서 기록된다.
4. 다음 probe에 대한 근거가 남는다.
   단순 action 추천이 아니라 `왜 이 probe가 선택되었는가`가 artifact로 남는다.
5. expected gain과 actual gain을 둘 다 회수할 수 있다.
6. recovery, stagnation, progress momentum을 scheduler가 다르게 취급한다.
7. small smoke와 targeted unit tests가 있어, seam 회귀를 빠르게 잡을 수 있다.
8. one-off local experiment가 아니라 bounded night loop로 여러 게임을 순환시킬 수 있다.

우리의 현재 상태를 여기에 대입하면, 이미 상당수를 충족하고 있다. 따라서 지금부터는 scaffolding을 “본업”으로 계속 끌고 가는 것은 점점 비용 대비 가치가 떨어질 가능성이 높다.

## C. Solver 쪽으로 무게중심을 옮겨야 한다는 신호

아래 신호가 보이면, 그때는 새 scheduler나 manager를 추가하기보다 solver를 직접 개선하는 쪽이 훨씬 중요하다.

1. episode는 많이 쌓이는데 실제 level completion이나 progress가 거의 늘지 않는다.
2. trace는 풍부한데 hypothesis quality가 낮다.
   즉 많이 기록하지만, 믿음이 더 정교해지지 않는다.
3. experiment designer가 고른 probe가 반복적으로 low-value observation만 낳는다.
4. perception/object tracking 오류가 solve failure의 근본 원인으로 보인다.
5. motif retrieval은 되지만 subgoal planning이 빈약하다.
6. recovery는 자주 일어나지만, recovery 이후 더 나은 plan으로 전환되지 않는다.
7. distillation용 데이터는 생기는데, 그 데이터가 “좋은 문제풀이 사고”보다 “운영 로그”에 더 가깝다.

이런 상태에서 scaffolding을 더 만들면, 우리는 실제 solver weakness를 고치지 못한 채 운영 계층만 더 복잡하게 만들 가능성이 높다.

## D. 앞으로 scaffolding을 허용하는 범위

이제부터 scaffolding은 아래 세 종류만 허용하는 것이 좋다.

1. solver와 outer loop를 직접 연결하는 seam 작업
   예: solve-loop runner를 night loop에 넣기, artifact schema 맞추기, dataset export 경로 연결하기

2. 장기 unattended run의 안정성을 높이는 운영 작업
   예: cache/env 정리, manifest 누락 방지, failure recovery, flaky path 보정

3. solver quality 또는 data quality를 바로 끌어올리는 instrumentation
   예: hypothesis diff를 더 직접적으로 저장, bad probe를 pruning하는 실제 metric 연결

반대로 이제는 아래 종류의 scaffolding은 가급적 피하는 편이 좋다.

1. scheduler를 또 하나 더 추가하는 일
2. manager를 더 세분화하는 일
3. artifact schema를 계속 크게 바꾸는 일
4. solve quality와 무관한 control-plane 추상화 늘리기

즉 앞으로 scaffold는 “얇고, 직접적이고, solver를 미는” 성격이어야 한다.

## E. 권장 전환 기준

실제로는 아래 세 조건이 동시에 맞으면 scaffolding의 우선순위를 낮추는 것이 좋다.

1. solver episode가 night loop나 supervisor에서 안정적으로 실행된다.
2. 그 결과가 trace/manifest/SFT export 경로로 바로 이어진다.
3. 현재 실패의 주 원인이 orchestration 누락이 아니라 solver reasoning weakness로 보인다.

이 세 가지가 맞는 순간부터는, 새 scaffold 1개보다 perception, hypothesis update, world-model prediction, subgoal planning, surprise-driven repair를 직접 개선하는 쪽이 더 큰 수익을 낸다.

## F. 실무용 의사결정 규칙

앞으로는 새 작업을 시작하기 전에 아래 질문을 먼저 던진다.

1. 이 작업이 solver의 성공률을 올리나?
2. 이 작업이 episode/trajectory의 학습 가치를 올리나?
3. 이 작업이 unattended stability를 실제로 높이나?
4. 이 작업이 Claude solver와 GPT scaffold 사이의 seam을 줄이나?

네 가지 중 하나에도 명확히 “예”라고 답하지 못하면, 그 작업은 미루는 편이 낫다.

그리고 보다 강한 stop rule도 두는 것이 좋다. 연속해서 두 번 이상의 scaffold 작업이 solve quality, data quality, stability 어느 쪽에도 눈에 띄는 개선을 주지 못했다면, 그다음 스프린트는 무조건 solver 개선에 쓴다. 즉 scaffold는 기본적으로 `opt-in`이 아니라 `justify-or-stop` 대상이 되어야 한다.

## G. 지금 시점의 판단

지금 상태를 이 체크리스트에 비춰보면, scaffolding은 이미 “충분히 의미 있는 기반” 단계까지 왔다. solve-loop bridge까지 연결되었고, queue/manifest/trace/night-loop/test 체인도 돌아간다. 따라서 이후 scaffolding은 전면 중단까지는 아니더라도, 우선순위를 낮추는 것이 맞다.

추천 전략은 이렇다.

1. 아주 짧은 기간만 더 scaffold seam을 정리한다.
   기준은 1~3개의 직접 연결 작업 정도다.

2. 그다음부터는 solver를 주력 트랙으로 본다.
   perception, hypothesis discrimination, motif retrieval, subgoal planning, recovery quality 개선이 본업이다.

3. scaffold는 solver를 방해할 때만 다시 손본다.
   즉 proactive expansion이 아니라 reactive support로 격하한다.

## H. 운영 결론

앞으로 우리는 이렇게 결정한다.

- 새 scaffolding 작업은 체크리스트의 A 또는 D에 해당할 때만 한다.
- 이 작업이 B를 이미 만족한 영역을 또 건드리는 것이라면, 보류한다.
- C 신호가 보이면 즉시 solver 트랙으로 전환한다.
- 두 번 연속으로 solver quality와 무관한 scaffold 작업을 했다면, 다음 작업은 반드시 solver를 고른다.

한 문장으로 요약하면, 이제 scaffolding은 “계속 만들 것”이 아니라 “필요할 때만 얇게 보수할 것”이다. 본격적인 개발의 중심은 점점 solver 쪽으로 옮겨가야 한다.
