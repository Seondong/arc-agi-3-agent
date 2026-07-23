<!-- [Mar 29] Created by SD with GPT-5.4. -->
# ARC-AGI-3 Agentic Framework Draft

이 디렉토리는 `master-plan-gpt.md`의 철학과, Claude가 여러 게임에 대해 작성한 harness narrative들을 함께 읽고 정리한 **역할 분해 초안**이다. 목적은 단순하다. 지금까지의 narrative들은 각 게임을 인간처럼 이해하려는 좋은 시도였지만, 구현 단계로 내려가면 “누가 무엇을 맡아야 하는가”가 더 명확해져야 한다. 이 디렉토리는 바로 그 분해를 위해 존재한다.

여기서 핵심 전제는 ARC-AGI-3가 단순한 action prediction 문제가 아니라는 점이다. 에이전트는 먼저 scene을 읽고, object를 추출하고, 조작 가능성을 추정하고, 현재 장면이 어떤 motif와 닮았는지 불러오고, 복수의 경쟁 가설을 유지하고, 정보량 높은 probe를 설계하고, 관측과 예측의 차이를 바탕으로 world model을 수정하며, 충분히 확신이 생겼을 때에야 solve plan으로 전환해야 한다. 즉 이 시스템은 policy 이전에 perception, perception 이전에 representation, representation 위에 hypothesis, hypothesis 위에 planning이 올라간다.

이번 분해는 다음 narrative들을 종합적으로 염두에 두고 작성되었다. `ls20`, `sk48`, `g50t`, `re86`, `tr87`, 그 외 다수의 `*-harness-narrative.md`들이 보여준 공통 구조와 반복되는 약점을 함께 반영한다. 각 게임은 motif가 다르지만, 놀랍게도 거의 모든 narrative가 같은 골격을 공유했다. `scene analysis → motif retrieval → epistemic planning → competing hypotheses → dynamics code → prediction/verification → goal inference → surprise handling → energy budget → distillation record`라는 흐름이다. 따라서 framework도 이 공통 뼈대를 살리되, 게임별로 달라지는 부분을 별도 역할로 나누는 방향이 자연스럽다.

이 디렉토리의 문서들은 다음 순서로 읽는 것이 좋다.

1. `01-corpus-synthesis.md`
2. `02-role-topology.md`
3. `03-perception-and-affordance.md`
4. `04-hypothesis-and-world-model.md`
5. `05-planning-and-execution.md`
6. `06-memory-distillation-evaluation.md`
7. `07-build-roadmap.md`
8. `08-control-plane-and-cognitive-plane.md`
9. `09-episode-memory-and-ledger.md`
10. `10-unattended-supervisor-loop.md`
11. `11-bounded-night-orchestrator.md`
12. `12-belief-auditor-and-queue-policy.md`
13. `13-three-game-night-loop-integration.md`
14. `14-narrative-seed-queue-compiler.md`
15. `15-experiment-designer-integration.md`
16. `16-selector-aware-scheduling.md`
17. `17-information-gain-aware-scheduling.md`
18. `18-actual-information-gain-calibration.md`
19. `19-trace-level-epistemic-enrichment.md`
20. `20-phase-manager-bootstrap-wiring.md`
21. `21-phase-aware-queue-scheduling.md`
22. `22-recovery-cooloff-and-adaptive-attention.md`
23. `23-solve-loop-supervisor-bridge.md`
24. `24-scaffold-exit-checklist.md`
25. `25-solver-priority-handoff.md`
26. `26-solver-work-tickets.md`
27. `27-solve-loop-night-loop-integration.md`
28. `28-perception-export-integration.md`
29. `29-belief-revision-artifact-integration.md`
30. `30-belief-revision-aware-scheduling.md`
31. `31-belief-diff-export-bridge.md`
32. `32-world-model-structure-handoff.md`
33. `33-world-model-export-and-distillation-design.md`
34. `34-world-model-trace-sft-metrics-wiring.md`
35. `35-llm-brain-handoff.md`
36. `36-llm-brain-wrapper-seam-closed.md`
37. `37-ft09-llm-memory-window-comparison.md`

실제 구현을 맡길 때의 원칙도 여기서 분명히 한다. 모든 역할이 반드시 LLM agent일 필요는 없다. 오히려 ARC-AGI-3에서는 deterministic code, heuristic module, symbolic state tracker, small model prior, large model reasoner가 섞여야 한다. 예를 들어 connected-component 기반 object detection, diff 계산, relation graph 구축, budget tracking, canonical scorecard evaluation은 코드로 두는 편이 낫다. 반면 motif retrieval, belief revision, surprise explanation, epistemic probe selection, subgoal narration은 LLM 또는 소형 reasoning model이 더 적합할 수 있다.

이 문서군은 아직 최종 설계가 아니다. 그러나 충분히 구체적이어서, 이후 여러 agent에게 각 부분을 병렬로 맡길 수 있는 첫 번째 분업 설계서로는 기능할 수 있다. 목표는 agent를 많이 만드는 것이 아니라, 인간이 새 게임에 적응할 때 내부에서 어떤 기능들이 돌아가는지를 명시적으로 시스템 안으로 끌어오는 것이다.
