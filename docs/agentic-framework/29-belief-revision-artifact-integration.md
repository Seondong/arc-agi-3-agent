<!-- [Mar 31] Created by SD with GPT-5.4. -->
# 29. Belief Revision Artifact Integration

이번 단계의 초점은 Claude가 이미 만들어 둔 `surprise_auditor.py`의 belief revision 결과를, solver 바깥에서도 실제로 읽을 수 있는 형태로 꺼내오는 것이었다. 현재 solver 내부에는 `RevisionAction`, `RevisionResult`, `AnchoringAlert` 같은 구조가 이미 존재한다. 즉 surprise가 발생했을 때 어떤 hypothesis가 깎였는지, 어떤 motif confidence가 수정되었는지, 어떤 새 hypothesis가 제안되었는지는 solver 안에서는 계산되고 있었다. 문제는 이 정보가 `solve_loop.py`에서 거의 artifact로 흘러나오지 않았다는 점이다.

그 결과 trace와 SFT export 관점에서는 “surprise가 있었다” 정도만 보이고, 정작 어떤 belief가 어떻게 바뀌었는지는 거의 사라졌다. 이것은 이후 distillation이나 unattended analysis에서 손실이 큰 지점이다. 작은 모델에게 가르치고 싶은 것은 단순히 “놀랐다”가 아니라, “그래서 어떤 hypothesis를 버렸고 어떤 새 가설을 떠올렸는가”이기 때문이다.

이를 위해 먼저 `schemas.py`의 `DecisionRecord`와 `TrajectoryRecord`에 belief revision 관련 필드를 추가했다. 구체적으로는 `belief_revision_summary`, `suggested_hypotheses`, `motif_updates`, `anchoring_alerts` 같은 필드가 들어갔다. 이 필드들은 solver 내부 reasoning을 전부 노출하려는 것이 아니라, outer loop와 exporter가 읽기에 충분한 최소 구조를 제공하는 데 목적이 있다.

그 다음 `solve_loop.py`를 보강해서 `audit_step(...)`의 반환값 중 `revision`과 `alerts`를 실제로 사용하게 만들었다. 이제 solve loop는 revision actions를 요약한 `confidence_update` 맵, concise한 `belief_revision_summary`, discard된 hypothesis 수를 나타내는 `hypothesis_pruning_count`, 전체 변화량을 거칠게 나타내는 `belief_revision_score`, 그리고 suggested hypotheses / motif updates / anchoring alerts를 모아 `DecisionRecord`와 `TrajectoryRecord`에 실어 보낸다. 이 작업은 solver의 정책을 바꾸는 것이 아니라, solver가 이미 알고 있는 것을 바깥으로 전달하는 integration 성격의 작업이다.

`memory.py`의 `TrajectoryCurator`도 그에 맞게 확장했다. 이제 curator는 belief revision summary, confidence update, suggested hypotheses, motif updates, anchoring alerts를 그대로 trace row에 기록할 수 있다. 덕분에 `episode_trace.jsonl`을 읽는 사람이나 후속 pipeline은 “이 step에서 무엇을 믿고 있었는가”뿐 아니라 “직전 observation 때문에 무엇이 바뀌었는가”도 함께 볼 수 있다.

마지막으로 export 경로도 같이 손봤다. `convert_episodes_to_sft.py`의 compact state builder는 이제 `Belief shifts:`와 `Hypothesis updates:` 라인을 포함할 수 있다. 즉 Claude가 solver 안에서 belief revision을 더 정교하게 만들수록, 그 결과는 곧바로 SFT prompt의 상태 요약에도 드러난다. 이는 향후 Qwen 같은 작은 모델에 “행동”만이 아니라 “belief update 패턴”까지 distill하고자 할 때 중요한 발판이 된다.

이 단계의 의미는 분명하다. 이제 surprise auditor는 더 이상 solver 내부의 폐쇄된 서브시스템이 아니다. 그것이 만들어낸 belief revision 결과가 trace, decision artifact, SFT export로 이어지면서, unattended loop와 distillation 파이프라인 전체가 그 신호를 활용할 수 있는 상태가 되었다.
