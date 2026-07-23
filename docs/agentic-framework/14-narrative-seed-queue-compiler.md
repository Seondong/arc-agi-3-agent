<!-- [Mar 30] Created by SD with GPT-5.4. -->
# 14. Narrative Seed Queue Compiler

지금까지의 night loop는 hand-written queue에 의존했다. `sk48`, `re86`, `g50t` 같은 몇 개 게임을 직접 JSONL로 써 넣는 방식은 구조를 검증하는 데는 좋지만, 문서 자산이 이미 20개 가까이 쌓인 현재 시점에서는 병목이 된다. Claude가 여러 게임에 대해 자세한 `harness narrative`를 써놓았는데, 그 안에 이미 초기 motif와 첫 probe 방향이 들어 있다면, 이를 다시 사람이 손으로 queue로 옮기는 것은 낭비다. 그래서 이번 단계에서는 narrative 문서를 seed queue로 자동 변환하는 compiler를 추가했다.

새 스크립트는 [`compile_seed_queue_from_narratives.py`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/scripts/compile_seed_queue_from_narratives.py) 이다. 이 스크립트는 `docs/harness-narratives` 디렉토리의 `*-harness-narrative.md` 파일들을 읽고, 각 문서에서 최소 세 가지를 뽑아낸다.

첫째, **motif_names**다. 현재 휴리스틱은 `Motif 후보 분포` 섹션 직후의 bullet/numbered list를 읽고, 각 항목의 영어 라벨을 slug로 정규화한다. 예를 들어 `Click-Semantics / Coordinate Selection (좌표 선택)`은 `click-semantics`로 정규화된다. 이 과정은 거칠지만, 최소한 bootstrap reasoner와 queue policy가 seed 수준의 motif prior를 받을 수 있게 해 준다.

둘째, **candidate_actions**다. narrative의 `실험 계획` 구역에서 `실험 1`, `실험 2` 식의 줄을 읽고, 그 줄에 등장하는 `ACTION1~ACTION7` 토큰을 순서대로 수집한다. 이것은 아직 queue item의 실행 action 자체로 들어가지는 않지만, notes와 goal hint에 반영되어 이후 scheduler나 Experiment Designer가 참고할 수 있게 된다.

셋째, **available_actions**다. 문서 초반부에서 ACTION 토큰을 훑어 narrative가 암시하는 가용 액션 집합을 정리한다. 이 값은 summary catalog에 들어가며, 나중에 compiler output을 검증하거나 prompt conditioning에 활용할 수 있다.

출력은 두 가지다. 하나는 night loop가 바로 읽을 수 있는 JSONL queue다. 기본 경로는 [`agentic_seed_queue_from_narratives.jsonl`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_seed_queue_from_narratives.jsonl) 이다. 다른 하나는 더 풍부한 summary catalog로, narrative별 추출 결과와 queue item을 함께 담는다. 기본 경로는 [`agentic_narrative_probe_catalog.json`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/agentic_narrative_probe_catalog.json) 이다.

queue item은 현재 deliberately simple하다. `actions`는 항상 `["RESET"]`로 시작하고, `motif_names`는 narrative에서 추출한 상위 motif들, `expected_mode`는 `epistemic`, `probe_family`는 `narrative-seed`로 고정한다. notes에는 source 문서 이름과 candidate probe 목록이 들어간다. 즉 이 compiler는 아직 "narrative를 완전한 실행 plan으로 번역"하지 않고, **night loop가 시작할 수 있는 seed artifact**로만 바꾸는 역할을 한다.

왜 이렇게 보수적으로 설계했는지도 중요하다. 지금 Claude 쪽에서는 `Experiment Designer`를 더 정교하게 만들고 있기 때문에, 여기서까지 액션 시퀀스를 너무 공격적으로 고정해버리면 역할이 겹친다. 오히려 지금 단계에서 필요한 것은, narrative 문서의 지식을 잃지 않으면서도 night loop가 읽을 수 있는 형태로 정리하는 것이다. 즉 compiler는 input preparation 역할이고, 실제 다음 probe 선택은 이후 더 정교한 모듈에게 넘긴다.

물론 한계는 분명하다. narrative 형식이 완전히 일관된 것은 아니어서, motif bullet이나 experiment line의 문법이 바뀌면 추출이 흔들릴 수 있다. 또 motif normalization이 영어 라벨의 첫 부분만 사용하는 식이라, nuance를 잃을 수 있다. 예를 들어 `Pattern Painting / Stamping`은 현재 `pattern-painting`만 남고 `stamping`은 떨어진다. 하지만 이 정도 단순화는 seed queue 단계에서는 오히려 장점일 수 있다. 너무 미세한 motif taxonomy는 bootstrap 단계에서 과적합된 prior가 될 수도 있기 때문이다.

중요한 건, 이제 20개 내외의 narrative 자산을 사람이 손으로 queue로 옮기지 않아도 된다는 점이다. 이 compiler가 생기면서, 다음 단계는 아주 자연스럽게 이어진다. narrative corpus 전체를 seed queue로 컴파일하고, 지금 만든 night loop에 넣어 여러 게임에 걸친 unattended structured episode를 더 넓게 생산할 수 있다. 그리고 그 위에 Claude의 더 강한 Experiment Designer가 올라오면, bootstrap_reasoner가 제안하던 단순한 `ACTION1 has not been tested yet` 수준을 넘어, narrative-conditioned probe scheduling으로 발전시킬 수 있다.
