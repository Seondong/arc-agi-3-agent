# ARC-AGI-3: 시뮬레이터 기반 접근법 — 실험 기록

## 0. 여기까지 오기까지의 여정

### Phase A: Master Plan 수립 → 1개 게임 수동 분석

master-plan-gpt.md를 작성하면서 ARC-AGI-3의 본질을 정리함:
- **"다음 action을 맞히는 문제"가 아니라 "세계를 재구성하는 문제"**
- world model → hypothesis bank → motif retrieval → epistemic/instrumental planning
- 작은 모델(Qwen)에 이식 가능한 형태로 설계해야 함

이 마스터플랜을 바탕으로 sk48 게임 1개를 Claude Code(harness.py)로 수동 분석. **harness-narrative** 형태로 게임별 분석 문서를 작성.

→ `docs/harness-narratives/` 에 저장

### Phase B: Scaffolding — solve_loop + agentic 모듈

마스터플랜의 인지 구조를 코드로 구현:

```
agents/agentic/
  schemas.py              ← 40+ Pydantic 모델 (ObservationSnapshot, BeliefLedger, DynamicsRule...)
  perception.py           ← 오브젝트 추적, 역할 점수 (controllable/goal/blocker)
  experiment_designer.py  ← epistemic probe 선택 (정보량 최대화)
  phase_manager.py        ← EPISTEMIC / INSTRUMENTAL / RECOVERY 모드 전환
  surprise_auditor.py     ← 예측 vs 실제 비교 → 가설 수정
  memory.py               ← 에피소드별 파일시스템 저장
  solve_loop.py           ← 전체 오케스트레이션
```

이 단계에서는 **LLM 없이 휴리스틱으로 placeholder**를 채움. 데이터 포맷은 원하는 형태로 설계 완료. 매 스텝마다 observation/belief/decision 3종 JSON을 저장하는 구조.

→ `data/episodes/{game}-{id}/steps/` 에 저장

### Phase C: LLM Brain 연동 시도 → 실패

solve_loop에 **llm_brain.py** (OpenAI API)를 붙여서 매 스텝 LLM에게 액션 결정을 맡기려 함.

**문제**: 
- 매 step마다 API 호출 → **컨텍스트가 끊김** (이전 관찰/추론 히스토리가 전달 안 됨)
- LLM이 게임의 전체 맥락을 모른 채 1스텝씩 판단 → 일관된 전략 불가
- 비용/속도 문제

→ 이 방식으로는 게임을 풀 수 없었음

### Phase D: Claude Code (harness)로 직접 풀기 → 데이터 수집에는 유효

Claude Code CLI에서 직접 게임을 분석:
- Claude Code = 100만 토큰 컨텍스트 → 전체 히스토리 유지 가능
- 프레임을 보고, 추론하고, 코드를 짜서 실행 → **인간처럼 게임을 풀 수 있음**
- sk48, tu93 등에서 메카닉을 발견하고 전략을 수립

**하지만 치명적 문제**:
- **매 가설 확인마다 게임을 처음부터 다시 실행** → action이 기하급수로 소비
- 5번 시도 = 5개 scorecard = Level 0을 5번 반복
- **Kaggle에서는 Claude Code를 쓸 수 없음** (인터넷 필요)

→ `docs/harness-narratives/`, `docs/sessions/` 에 분석 기록 저장

### Phase E: 시뮬레이터 기반 접근법 도출 ← **지금 여기**

Phase D의 문제를 해결하기 위해:

```
Phase D의 문제:     매 가설 확인 = 실제 게임 action 소비
                    ↓
해결:              가설을 시뮬레이터 안에서 확인 (action 0)
                    ↓
필요한 것:          관찰 → 시뮬레이터 코드 작성 → BFS → 실행 → 수정
                    ↓
Kaggle에서는:       이 과정을 SLM(Qwen)이 수행
```

**1개 scorecard 안에서 시뮬레이터를 점진적으로 빌드하면서 게임을 풀 수 있는가?** 를 검증하는 것이 현재 목표.

### 데이터가 어디에 있는가

| 데이터 | 위치 | 내용 |
|--------|------|------|
| 마스터플랜 | `docs/strategy/master-plan-gpt.md` | 인지 구조 설계, 시뮬레이터 섹션 추가 |
| 전략 비교 | `docs/strategy/search-strategies-comparison.md` | MCTS vs CLI vs Harness |
| 시뮬레이터 접근법 | `docs/strategy/simulator-building-approach.md` | 4단계 루프, 확률적 모델, SLM |
| 게임별 분석 | `docs/harness-narratives/` | sk48, ls20 등 |
| 세션 기록 | `docs/sessions/session-002-*.md` | 이 세션의 전체 기록 |
| 에피소드 데이터 | `data/episodes/{game}-{id}/` | observation/belief/decision/simulator |
| 시뮬레이터 코드 | `agents/agentic/simulator.py` | BaseSimulator (abstract) |
| 게임별 시뮬레이터 | `agents/agentic/simulators/tu93_simulator.py` | tu93 전용 |
| 스키마 정의 | `agents/agentic/schemas.py` | 40+ 데이터 모델 |
| 솔버 루프 | `agents/agentic/solve_loop.py` | 전체 오케스트레이션 |

---

## 1. Phase B: Scaffolding — 어떤 데이터를 어떻게 수집하는가

게임을 풀기 전에, **agentic 인프라** — solver가 보고, 생각하고, 결정하는 모든 것을 캡처하는 데이터 파이프라인을 먼저 구축.

### 매 스텝 데이터 (액션 1회당 3개 파일)

에이전트가 1 action을 수행할 때마다 JSON 3개가 저장됨:

| 파일 | 무엇을 캡처하는가 | 주요 필드 |
|------|------------------|----------|
| `observation.json` | 에이전트가 **본 것** | 그리드 상태, diff, 오브젝트 (persistent ID, role 점수), 사용 가능 액션 |
| `belief.json` | 에이전트가 **믿고 있는 것** | 가설 (confidence 포함), dynamics 규칙, motif, 액션 의미, 서브골 |
| `decision.json` | 에이전트가 **결정한 것** | 선택한 액션, 근거, 기대 결과, 시뮬레이터 예측 |

### Agentic 파이프라인 모듈

```
perception.py         → 오브젝트 추출, 프레임 간 동일성 추적, 역할 점수 부여
experiment_designer.py → 가장 정보량 높은 probe action 선택 (epistemic 모드)
phase_manager.py      → 결정: 더 탐색? 계획 실행? 실패 복구?
surprise_auditor.py   → 예측 vs 실제 비교 → 신념 수정
memory.py             → 모든 것을 파일시스템에 저장
solve_loop.py         → 전체 루프 오케스트레이션
```

각 모듈은 **구조화된 데이터**를 채움 (schemas.py의 Pydantic 모델 — 40+ 클래스). solver가 휴리스틱만 쓰더라도 데이터 포맷은 프로덕션 수준.

→ `data/episodes/{game}-{id}/steps/step_NNNN.{observation,belief,decision}.json` 에 저장

---

## 2. Phase C: LLM Brain — 왜 매 스텝 API 호출이 실패했는가

solve_loop에 `llm_brain.py`를 붙임 — OpenAI API가 매 액션을 결정.

```
Step 1: 그리드 + diff를 LLM에 전송 → LLM "ACTION4 해봐" → 실행
Step 2: 새 그리드 + diff를 LLM에 전송 → LLM "ACTION1 해봐" → 실행
  (LLM은 Step 1의 추론을 전혀 기억 못함!)
```

**왜 실패했는가**:
- 각 API 호출 = 독립적. 스텝 간 **persistent context 없음**
- LLM이 매 호출 사이에 모든 것을 잊어서 world model을 구축 불가
- Rolling memory window (최근 4스텝)은 복잡한 게임에 너무 짧음
- 비용: 스텝당 ~$0.10 × 수백 스텝 = 비쌈

**핵심 교훈**: ARC-AGI-3를 풀려면 **에피소드 전체에 걸친 지속적 추론**이 필요. 매 스텝 독립 판단으로는 불가. Claude Code (100만 토큰 컨텍스트)가 API 호출보다 작동한 이유가 이것.

---

## 3. Phase D: Claude Code가 직접 게임을 풀다

LLM Brain 방식이 실패하자, **Claude Code 자체가** 게임을 인터랙티브하게 플레이.

**tu93 게임** (미로 + 적 회피)에서 시작:
- 64×64 그리드, ACTION1-4 (방향키)
- Claude Code가 프레임을 보고, 추론하고, Python 스크립트를 짜서 실행

### 발견한 메카닉
1. 3×3 블록 타일로 구성된 **그래프 구조** (0-블록=노드, 2-블록=엣지, 5=벽)
2. 에이전트(9+4 블록)가 엣지를 따라 다음 노드로 **점프**
3. e(14) 블록 = **목표**. 도달하면 레벨 클리어
4. Level 1부터 **적(8+f 블록)** 등장: 같은 행에서 수평 진입 → DEAD, 수직 진입 → SWAP(적 제거)
5. 적의 f/b 픽셀 = **눈**. 시야 방향 1노드에 진입하면 잡아먹힘

### 결과
- Level 0: 18 actions으로 클리어 (BFS)
- Level 1: 10 actions으로 클리어 (적 회피 BFS)
- Level 2: 적 3마리 + sight cone → 미해결

### 이 방식의 문제점
- **매 가설 확인 = 게임을 처음부터 다시 실행** → 5개 scorecard 소비
- Level 0을 5번 반복 플레이 (90 actions 낭비)
- Claude Code는 인터넷 필요 → **Kaggle에서 사용 불가**

---

## 4. Phase D→E: 왜 시뮬레이터가 필요한가 (세 가지 접근법 비교)

직접 풀어보면서 **왜 이게 어려운지** 체감. 세 가지 접근법을 비교:

### MCTS (이상적)
- 시뮬레이터가 있으면 10,000번 "만약에..."를 **공짜로** 해봄
- 실제 게임에는 최적 1 액션만 보냄
- **전제: 정확한 시뮬레이터가 있어야 함**

### Harness LLM Agent (현재 방식)
- 매 턴 LLM에게 "뭘 해야 해?" 물어봄
- **탐색 = 실행**. 매 실수가 실제 액션으로 소비됨
- Look-ahead 불가. 1스텝 추론(greedy)

### CLI BFS with Oracle (내가 한 것)
- 게임 엔진을 오라클로 사용, 매번 처음부터 리플레이
- **정확하지만 느림** — O(N²) 리플레이 오버헤드
- Level 3에서 시간 초과

### 비교표

|  | MCTS | CLI BFS | Harness LLM |
|--|------|---------|-------------|
| 탐색 비용 | 0 (시뮬) | O(N²) 리플레이 | 매 테스트 = 실제 |
| 계획 품질 | 최적 | 최적 (깊이 내) | 추측 기반 |
| 선읽기 | 깊음 (20+) | 깊지만 느림 | 없음 (1스텝) |
| 적 대응 | 완벽한 모델 | 완벽 (오라클) | "아마 왼쪽으로 갈 듯" |

---

## 5. Phase E: 시뮬레이터를 만들어가며 풀기

**가장 강한 접근법**: 관찰에서 시뮬레이터 코드를 짜고, 그 위에서 BFS/MCTS.

### 4단계 루프

```
Phase 1: EXPLORE — 실제 액션 소비 (소량)
  → 몇 개 액션으로 메카닉 관찰

Phase 2: MODEL — 시뮬레이터 코드 작성 (비용 0)
  → 관찰에서 simulate(state, action) 함수 생성

Phase 3: PLAN — 시뮬레이터 위에서 BFS (비용 0)
  → 10,000 경로 탐색해도 실제 액션 0

Phase 4: EXECUTE — 최적 경로만 실제 실행
  → 예측과 다르면 Phase 2로 돌아가 시뮬레이터 수정
```

### 핵심 통찰: 확률적 시뮬레이터

- 매 메카닉에 **confidence** 점수
- 관찰이 쌓이면 confidence 증가
- 예측 실패하면 confidence 감소 + 규칙 수정
- BFS는 **confidence가 높은 경로만** 탐색 (safe planning)

---

## 6. Phase E: 실제 구현 + 검증

### 만든 것

| 파일 | 역할 |
|------|------|
| `simulator.py` | BaseSimulator (abstract) + Simulator (rule-based) |
| `simulators/tu93_simulator.py` | tu93 전용: 그래프 파싱 + sight cone + eat/swap |
| `schemas.py` | SimulatorSnapshot, SimulatorEvolutionEntry |
| `solve_loop.py` | simulator 연동 (build→predict→verify→update) |
| `memory.py` | evolution.jsonl 로깅 |

### 1 scorecard 안에서 시뮬레이터 점진 빌드

```
Step 1-4:   EPISTEMIC (4 actions) → "3x3 블록 그래프 점프" 발견
Step 5:     시뮬레이터 v1 빌드 (그래프 이동만)
Step 5-21:  v1 BFS로 Level 0 클리어 (17 actions)
Step 21:    Level 1 시작, 적 발견 → 시뮬레이터 v2 (적 충돌/SWAP)
Step 22-31: v2 BFS로 Level 1 클리어 (10 actions)

총: 31 actions, 2 levels, RHAE = 1.0 + 1.0 (둘 다 만점!)
```

### 시뮬레이터 진화 히스토리

| Version | Step | Trigger | 결과 |
|---------|------|---------|------|
| v1 | 4 | epistemic probes | L0 ✓ (17 steps) |
| v2 | 21 | 적 발견 | L1 ✓ (10 steps) |
| v3 | 55 | L2 사망 → sight cone | L2 ✗ (BFS 경로가 실제로는 unsafe) |

---

## 7. 핵심 교훈

### ✅ 작동한 것
- 시뮬레이터 점진 빌드가 실제로 게임을 풀 수 있다
- 1 scorecard 안에서 v1→v2 업그레이드 → 이전 방식 대비 5x 효율
- RHAE 만점 달성 (인간보다 효율적)

### ❌ 안 된 것
- Level 2: 적 3마리의 sight cone + 추격 메카닉 → 시뮬레이터가 현실과 불일치
- **같은 실패를 반복하는 버그** — 실패 감지 후 전략 변경 로직 부재
- **ls20**: goal inference 실패 — 승리 조건 자체를 모름

### 💡 깨달은 것
1. **시뮬레이터 빌드에 LLM이 필수** — pattern matching으로는 구조적 이해 불가
2. **적 행동은 레벨마다 다름** — 레벨별 학습 필요
3. **goal inference가 시뮬레이터보다 선행** — 목표를 모르면 BFS goal_test 정의 불가
4. **Kaggle에서는 SLM이 이 역할을 해야** — Claude가 하는 것을 Qwen이 대체

---

## 8. Kaggle 전략으로의 연결

### SLM이 해야 할 일

```
Claude Code (로컬 개발)          Qwen 3.5 (Kaggle)
─────────────────                ─────────────────
프레임 관찰 → 메카닉 추론         같은 일을 해야 함
시뮬레이터 코드 작성               같은 일을 해야 함
실패 시 시뮬레이터 수정            같은 일을 해야 함
시뮬레이터 위에서 BFS             같은 일을 해야 함
```

### SFT 데이터 = 시뮬레이터 진화 로그

```
Input:  "새 엔티티 8-block 발견, f marker at offset (0,-1)"
Output: "if agent enters enemy cell horizontally → DEAD
         if agent enters enemy cell vertically → SWAP
         Confidence: 0.7"
```

이런 (관찰, 시뮬레이터 수정) 쌍이 SLM 훈련 데이터.

### 게임별 시뮬레이터 파일

```
simulators/
  tu93_simulator.py  ← 이번 세션에서 생성
  ls20_simulator.py  ← 다음 목표
  common_patterns.py ← graph_movement, sight_cone 등 재사용
```

같은 게임 재시도 시 이전 시뮬레이터를 로드 → 탐색 비용 절감.

---

## 9. ls20 분석 (진행 중)

tu93와 전혀 다른 유형 — **메카닉은 단순하지만 목표가 불투명**.

### 발견한 것
- c(12)+9 블록이 5셀 단위로 이동 (도구)
- 0/1 패턴 = 변환 연산자 (고정 위치)
- c 블록이 0/1 위를 통과하면 **bottom-left ref 패턴이 변형**
- ref는 4-cycle로 순환 (4회 통과 = 원점)
- 방향에 따라 변형이 다름 (LEFT 통과만 변형 발생 확인)

### 미해결
- **WIN 조건을 모름** — ref를 top room 패턴에 맞춰도 WIN 안 됨
- 130 action budget (3 라운드) 내에 풀어야 함
- Goal inference가 핵심 도전

---

## 10. 다음 단계

1. **ls20 goal inference**: Claude Code가 직접 관찰하며 WIN 조건 파악
2. **tu93 Level 2**: 적 추격 메카닉 정밀 관찰 → 시뮬레이터 v4
3. **실패 반복 방지**: 같은 경로 2회 사망 시 자동 전략 변경
4. **SLM 연동**: Claude 세션 로그로 Qwen SFT 데이터 구축

---

## 11. Solver가 수집하는 데이터와 저장 구조

### 매 스텝마다 3종류의 데이터를 수집

```
step_0001.observation.json  ← 이 스텝에서 뭘 봤는가
step_0001.belief.json       ← 이 스텝에서 뭘 믿고 있는가
step_0001.decision.json     ← 이 스텝에서 뭘 결정했는가
```

#### Observation (관찰)
```json
{
  "step_index": 1,
  "grid_rows": 64, "grid_cols": 64,
  "diff_summary": "19 cells changed",
  "available_actions": ["ACTION1", "ACTION2", "ACTION3", "ACTION4"],
  "objects": [
    {
      "persistent_id": "P_○0_3",
      "value": 9,
      "cell_count": 8,
      "bbox": {"row_min": 16, "row_max": 18, "col_min": 15, "col_max": 17},
      "controllable_score": 0.8,
      "goal_score": 0.0,
      "blocker_score": 0.0
    }
  ],
  "compressed_grid": "...(RLE)...",
  "map2d": "...(ASCII visualization)..."
}
```

#### Belief (신념 체계)
```json
{
  "step_index": 1,
  "mode": "epistemic",
  "top_motifs": [{"name": "navigation", "confidence": 0.7}],
  "hypotheses": [
    {
      "hypothesis_id": "H0",
      "summary": "Game follows a 'navigation' motif",
      "confidence": 0.7,
      "status": "provisional",
      "evidence": ["directional actions available"]
    }
  ],
  "dynamics_rules": [
    {
      "rule_id": "DR_1",
      "action_name": "ACTION4",
      "condition": "",
      "effect": "moves controllable P_○0_3 right ~6 cells",
      "confidence": 0.30,
      "times_verified": 1,
      "times_violated": 0
    }
  ],
  "action_semantics": {"ACTION4": ["moves agent right"]},
  "active_subgoals": []
}
```

#### Decision (결정)
```json
{
  "step_index": 1,
  "mode": "epistemic",
  "chosen_action": "ACTION4",
  "rationale": "Epistemic probe: test ACTION4 effect",
  "expected_outcome": "Agent moves right",
  "expected_information_gain": "Discover ACTION4 semantics",
  "simulator_version": 0,
  "simulator_prediction": "agent moves to (17, 23)",
  "simulator_correct": true
}
```

### 시뮬레이터 진화 로그

```
episode_{id}/simulator/
  evolution.jsonl        ← 시뮬레이터가 바뀔 때마다 1줄 추가
  simulator_v000.json    ← v0 스냅샷
  simulator_v001.json    ← v1 스냅샷 (surprise 후 수정)
```

#### evolution.jsonl 예시
```jsonl
{"step_index":5,"version_before":0,"version_after":0,"trigger":"initial_build","rules_added":["ACTION1→move_up","ACTION4→move_right","collision_death","goal_reached"]}
{"step_index":16,"version_before":0,"version_after":1,"trigger":"surprise_update","rules_added":["enemy_mirror"],"prediction_that_failed":"action=ACTION4","actual_observation":"diff=19, GAME_OVER"}
```

### 전체 디렉토리 구조

```
data/episodes/{game_id}-{episode_hash}/
│
├── episode.json                    ← 메타데이터 (game_id, tags, timestamp)
├── episode_trace.jsonl             ← 스텝별 압축 trajectory (1줄 = 1스텝)
│
├── simulator/                      ← ★ 시뮬레이터 진화 기록
│   ├── evolution.jsonl             ← 버전별 변경 이력
│   ├── simulator_v000.json         ← 초기 시뮬레이터 스냅샷
│   └── simulator_v001.json         ← 업데이트된 스냅샷
│
└── steps/                          ← 스텝별 상세 데이터
    ├── step_0001.observation.json  ← 뭘 봤는가
    ├── step_0001.belief.json       ← 뭘 믿는가
    ├── step_0001.decision.json     ← 뭘 결정했는가
    ├── step_0002.observation.json
    ├── step_0002.belief.json
    ├── step_0002.decision.json
    └── ...
```

### 이 데이터가 SFT에 어떻게 쓰이는가

```
Observation + Belief → "현재 상태에서 뭘 알고 있는가"     = SFT Input
Decision (action + rationale + simulator_update)         = SFT Output

특히 simulator evolution이 핵심:
  (관찰, 예측실패, 시뮬레이터 코드 수정) 튜플
  = SLM에게 "관찰 → 코드 수정"을 가르치는 supervision signal
```

---

## 관련 문서

- `docs/strategy/search-strategies-comparison.md` — MCTS vs CLI vs Harness 상세 비교
- `docs/strategy/simulator-building-approach.md` — 시뮬레이터 접근법 + 확률적 모델 + SLM 전략
- `docs/strategy/master-plan-gpt.md` — "코드로서의 시뮬레이터" 섹션 추가됨
- `docs/sessions/session-002-simulator-evolution.md` — 전체 세션 상세 기록
