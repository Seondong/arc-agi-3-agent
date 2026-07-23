<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 15. Experiment Designer Integration

Claude 쪽에서 `Experiment Designer`를 추가하면서, epistemic probe selection 계층이 한 단계 더 정교해졌다. 기존의 [`bootstrap_reasoner.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/bootstrap_reasoner.py)는 “아직 안 해본 ACTION을 먼저 눌러본다”는 수준의 가벼운 bootstrap 정책이었다. 이것만으로도 초기 unattended loop를 열 수는 있었지만, 경쟁 가설들을 가장 빨리 갈라놓는 probe를 설계하는 수준까지는 가지 못했다. 그래서 이번 단계에서는 Claude가 작성한 [`experiment_designer.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/agents/agentic/experiment_designer.py)를 supervisor에 실제로 연결했다.

통합 원칙은 보수적이다. Claude의 모듈 자체는 건드리지 않는다. 대신 [`agentic_supervisor.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/agentic_supervisor.py) 안에 얇은 adapter를 둔다. 이 adapter는 현재까지 실행된 action prefix와 observation의 action history를 읽어 `ProbeHistory`를 재구성하고, `design_next_probe(...)`를 호출한다. 그러면 supervisor는 더 이상 무조건 `ACTION1 has not been tested yet` 식으로 제안하지 않고, hypothesis discrimination, reversibility, boundary probing, family saturation 같은 richer heuristic을 거친 probe를 받을 수 있다.

중요한 지점은 여기서 끝이 아니라는 것이다. Claude의 `Experiment Designer`는 때때로 richer action을 제안한다. 예를 들어 `{"sequence": ["ACTION1", "ACTION2"]}` 같은 paired reversibility probe나, `{"action": "ACTION6", "coordinate": [...]}` 같은 click probe를 줄 수 있다. 하지만 현재 harness와 queue는 여전히 비교적 단순한 action prefix를 기준으로 움직인다. 그래서 supervisor에는 adapter가 하나 더 들어간다. `expand_probe_action_for_queue(...)`는 이 richer probe를 **현재 outer loop가 실행 가능한 prefix 형태**로 낮춰준다. sequence probe는 action list로 확장하고, click probe는 우선 `ACTION6`이라는 coarse action으로 축약한다. 즉 이 단계의 목표는 rich proposal을 완벽하게 실행하는 것이 아니라, richer planner를 existing infrastructure와 안전하게 접합하는 것이다.

실제 변화는 decision과 manifest에도 반영된다. supervisor는 이제 next probe를 고를 때, 그것이 `experiment_designer`에서 왔는지 `bootstrap_reasoner_fallback`에서 왔는지를 기록한다. decision notes와 manifest의 `next_probe_selector`를 보면, 어떤 episode가 더 정교한 probe selection을 거쳤는지 추적할 수 있다. 이건 이후 structured corpus를 분석할 때 중요하다. 같은 game을 돌렸더라도, “그 probe가 왜 선택되었는가”와 “어느 selector가 골랐는가”를 분리할 수 있기 때문이다.

이 통합이 의미하는 바는 크다. 지금까지의 night loop는 episode를 쌓는 쪽에 가까웠다. 이제부터는 적어도 다음 probe 하나만큼은, 경쟁 가설과 family diversity를 고려한 설계를 바탕으로 고를 수 있게 되었다. 물론 아직 full world model planning은 아니다. affordance-aware click targeting도 실제 queue execution까지 완전히 내려오진 않았다. 하지만 epistemic planning의 control-plane이 한 단계 더 깊어졌다는 점에서, 이것은 중요한 전환점이다.

다음 단계는 자연스럽게 두 갈래다. 하나는 `Experiment Designer`가 제안하는 rich probe를 harness가 더 직접 실행할 수 있도록 action schema를 확장하는 것이다. 다른 하나는 night loop와 queue policy가 `next_probe_selector`, `probe_family`, `information_gain`을 더 적극적으로 반영하여, 어떤 follow-up를 계속 살릴지 결정하는 것이다. 지금 단계의 통합은 바로 그 두 방향을 열어주는 bridge 역할을 한다.
