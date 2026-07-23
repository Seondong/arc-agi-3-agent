<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 31. Belief Diff Export Bridge

Claude 쪽 solver는 이미 `solve_loop.py` 내부에서 `BeliefDiff`를 계산하고 있었다. 이 diff는 step-level reasoning 관점에서는 충분히 유용했지만, 그동안은 `StepResult` 내부에만 머물고 `DecisionRecord`, `TrajectoryRecord`, SFT exporter로는 흘러가지 않았다. 따라서 outer loop와 dataset 쪽에서 읽을 수 있는 신호는 여전히 `belief_revision_summary`, `confidence_update`, `suggested_hypotheses` 같은 문자열 중심 필드에 치우쳐 있었다.

이번 브리지 작업의 목적은 solver 내부 구조를 바꾸는 것이 아니라, 이미 Claude가 계산한 `BeliefDiff`를 GPT 쪽 shared schema/export 층으로 안전하게 연결하는 것이었다. 그래서 canonical shape는 Claude가 이미 쓰고 있는 내부 필드에 맞췄다. 즉 `hypotheses_strengthened`, `hypotheses_weakened`, `hypotheses_discarded`, `hypotheses_suggested`, `motifs_updated`, `anchoring_alerts`, `max_confidence_delta`, `summary`를 공용 `BeliefDiffSummary`로 두고, `DecisionRecord`와 `TrajectoryRecord`가 이 구조를 optional field로 들고 다니도록 정리했다.

핵심 포인트는 solver 알고리즘을 건드리지 않았다는 점이다. `solve_loop.py`는 여전히 Claude가 만든 internal `BeliefDiff`를 그대로 계산한다. 다만 export 직전에 그것을 `BeliefDiffSummary`로 옮겨 `decision`과 `trajectory`에 함께 실어 준다. 이 덕분에 trace file과 step decision artifact를 읽는 쪽은 더 이상 string parsing만 하지 않아도 된다.

이 브리지의 실질적 효과는 두 군데에서 바로 나타난다. 첫째, structured episode trace가 “이번 step에서 belief가 얼마나 흔들렸는가”를 compact count 형태로 담을 수 있게 된다. 둘째, `convert_episodes_to_sft.py`의 compact prompt가 `Belief diff:` 라인을 추가로 넣을 수 있게 되어, 작은 모델에게도 `up/down/discarded/new hypothesis`, `motifs_updated`, `anchoring_alerts`, `max_confidence_delta` 같은 요약 신호를 텍스트로 직접 전달할 수 있다. 즉 distillation prompt가 이전보다 한 단계 더 solver-internal epistemic movement를 반영하게 된다.

이 작업은 안전한 분업의 좋은 예이기도 하다. Claude는 solver 안에서 실제 world-modeling과 belief revision을 만들고, GPT는 그 결과가 trace, dataset, night-loop attention policy로 잘 흘러가게 export seam을 정리한다. 이번 단계는 정확히 그 seam 정리에 해당한다.
