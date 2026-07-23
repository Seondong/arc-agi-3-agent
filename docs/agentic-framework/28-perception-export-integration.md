<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 28. Perception Export Integration

이번 단계에서는 Claude가 solver 쪽에서 구현한 `P1-1 Persistent Object Identity`와 `P1-2 Role Candidate Scoring`을, GPT 쪽의 distillation/export 경로가 실제로 받아먹도록 연결했다. 이 작업의 핵심은 perception 자체를 더 똑똑하게 만드는 것이 아니라, 이미 더 똑똑해진 perception이 dataset 단계에서 다시 납작하게 눌려 사라지지 않게 만드는 것이다.

구체적으로는 `convert_episodes_to_sft.py`의 compact state builder를 보강했다. 이전에는 object summary가 사실상 `value`, `cell_count`, bounding box만 보여주는 수준이어서, Claude가 넣은 `persistent_id`, `controllable_score`, `goal_score`, `blocker_score`, `click_score` 같은 새 의미론적 신호가 user prompt에서 거의 드러나지 않았다. 즉 solver는 장면을 더 잘 보고 있는데, distillation용 text prompt는 여전히 예전처럼 “큰 object 몇 개”만 보여주고 있었다.

이 문제를 줄이기 위해 compact state는 이제 두 가지를 더 표현한다. 첫째, top objects 요약 안에 `persistent_id`의 짧은 형태와 높은 role score tag를 함께 넣는다. 둘째, 별도의 `Role candidates:` 라인을 만들어 controllable / goal / blocker / click 후보의 최상위 object를 직접 명시한다. 이렇게 하면 작은 모델이 상태를 읽을 때, 단순히 큰 blob 몇 개를 보는 것이 아니라 “지금 조작 가능성이 높은 object는 무엇이고, goal 후보는 무엇이며, click target처럼 보이는 것은 무엇인가”를 한 번에 읽을 수 있다.

또한 object ranking도 바꿨다. 이전에는 cell count가 큰 object가 거의 항상 요약 상단을 차지했다. 하지만 ARC-AGI-3에서는 solver에 중요한 object가 반드시 큰 object는 아니다. 작지만 클릭 가능한 스위치, 드문 색의 goal marker, controllable avatar 같은 물체가 더 중요할 수 있다. 그래서 exporter는 이제 role-salient object를 먼저 일부 선택하고, 그 다음에 큰 object로 채우는 혼합 ranking을 쓴다. 이는 Claude가 perception에서 만든 역할 점수가 실제 supervision prompt에 반영되도록 하기 위한 최소한의 다리다.

이 작업은 solver를 직접 바꾸는 것은 아니지만, 매우 중요하다. 지금의 agentic stack은 solve-loop가 episode artifact를 만들고, GPT 쪽 outer loop가 그것을 structured trace와 SFT example로 바꾸는 구조다. 이때 perception이 richer해졌는데 export가 그 richness를 잃어버리면, 나중에 작은 모델로 distill할 때 배울 수 있는 정보가 크게 줄어든다. 이번 integration은 바로 그 손실을 줄이기 위한 것이다.
