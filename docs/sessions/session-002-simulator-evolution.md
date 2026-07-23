# Session 002: Simulator Evolution — tu93 Hands-On (2026-04-01~02)

## Summary

Claude Code가 tu93 게임을 **직접 플레이**하면서 시뮬레이터를 점진적으로 빌드하고, 실패에서 배우며 업그레이드하는 과정을 기록. 1개 scorecard 안에서 시뮬레이터 v1→v2→v3까지 진화시켜 Level 0+1을 클리어하고, Level 2에서 새로운 적 행동(sight cone)을 발견했으나 해결하지 못한 채 세션 종료.

**핵심 성과**: "관찰→시뮬레이터 코드 작성→BFS 계획→실행→실패→시뮬레이터 수정" 루프가 실제로 작동함을 검증.

---

## Timeline

### Phase 1: 아침 세션 — Claude Code가 직접 게임 풀기 (harness 없이)

tu93를 CLI에서 직접 탐색. 시뮬레이터 없이 즉석 Python 스크립트로 게임 메카닉 발견:

```
발견한 메카닉:
  1. 64x64 그리드는 3x3 블록 타일로 구성
  2. 0-블록 = 정류장(노드), 2-블록 = 연결(엣지), 5 = 벽
  3. 에이전트(9+4 블록)가 연결을 따라 다음 노드로 점프
  4. e(14) 블록 = 목표. 도달하면 레벨 클리어
  5. Level 1부터 적(8+f 블록) 등장
  6. 적과 충돌하면 GAME_OVER
  7. 하단 bar(6 값)는 액션 카운터
```

**방법**: 매번 게임을 새로 시작해서 BFS 스크립트를 돌림. 5개 scorecard 소비.
**결과**: Level 0-2 클리어, Level 3 BFS depth 초과로 실패.

### Phase 2: 시뮬레이터 인프라 구축

simulator.py, schemas.py, solve_loop.py, memory.py에 시뮬레이터 프레임워크 추가:

```
simulator.py (NEW, ~500줄):
  - GameState: 엔티티 위치, 벽, 경로, 승패 상태
  - MechanicRule: DynamicsRule에서 변환된 실행 가능 규칙
  - Simulator: predict(state, action), search_bfs(), search_safe_bfs()
  - SimulatorBuilder: belief→simulator 변환, surprise 기반 업데이트

schemas.py:
  - SimulatorSnapshot: 시뮬레이터 버전 스냅샷
  - SimulatorEvolutionEntry: 시뮬레이터 변경 로그
  - TrajectoryRecord에 simulator_version/prediction/correct 필드 추가

solve_loop.py:
  - INSTRUMENTAL phase에서 simulator BFS를 우선 사용
  - 매 스텝 후 predict→verify→update 루프
  - surprise 시 simulator 자동 업데이트

memory.py:
  - simulator/ 디렉토리에 evolution.jsonl, simulator_vNNN.json 저장
```

### Phase 3: solve_loop 통합 테스트 — 실패

solve_loop.py의 DynamicsRule → MechanicRule 변환(pattern matching)이 부정확:

```
문제:
  1. DynamicsRule의 NL 텍스트에서 방향을 잘못 추출
     → "ACTION2→move_left" (실제: down)
  2. update_from_surprise()가 매번 전체 DynamicsRule 재추가
     → 232개 중복 mechanic 폭발
  3. 1셀 그리드 이동 가정 vs 실제 그래프 점프 메카닉 불일치

수정:
  Fix 1: action_name에서 방향 우선 추출 (NL보다 신뢰도 높음)
  Fix 2: existing_source_ids 체크로 중복 방지
  결과: 232 → 15 mechanics, avg_conf 0.557 → 0.865
```

**교훈**: pattern matching 기반 시뮬레이터 빌더는 "세계를 이해"하지 못함. LLM이 직접 시뮬레이터 코드를 짜야 함.

### Phase 4: Claude Code가 직접 시뮬레이터를 짜며 게임 풀기

**1개 scorecard** 안에서 시뮬레이터를 점진적으로 빌드. API 호출 없이 Claude Code가 LLM 역할.

#### Simulator v1 (step 1-4: EPISTEMIC)

```python
# 4 probe actions으로 관찰:
# ACTION1-3: diff 1-2 (벽에 막힘)
# ACTION4: diff 19, agent 이동 (3x3 블록 그래프 점프)

# Claude의 판단: "3x3 블록이 그래프 노드를 따라 점프하는 게임"
# → parse_graph() + bfs() 작성
```

**결과**: Level 0 클리어 (17 actions). 시뮬레이터 = 그래프 파싱 + BFS.

#### Simulator v2 (step 21: Level 1 시작)

```python
# 관찰: 적(8+f 블록) 발견 at (28, 37)
# 적의 adj: A2→(34,37), A3→(28,31), A4→(28,43)

# Claude의 판단 (Level 1 아침 세션 경험에서):
#   "같은 행에서 적 셀로 수평 진입 → 충돌(DEAD)"
#   "다른 행에서 적 셀로 수직 진입 → SWAP"

# BFS 상태 = (agent_pos, enemy_pos) 튜플로 확장
```

**결과**: Level 1 클리어 (10 actions). 시뮬레이터 = 그래프 + 적 충돌/SWAP 규칙.

#### Simulator v3 (step 31: Level 2 시작, 첫 사망 후)

```python
# Level 2: Agent=(43,43), Goal=(43,25), Enemies=3마리!
#   Enemy1: (25,25) eye=(0,1)→ sees (25,31)
#   Enemy2: (25,31) eye=(1,0)→ sees (31,31)
#   Enemy3: (37,13) eye=(0,1)→ sees (37,19)

# 첫 시도: v2 sim으로 9 steps 계획 → step 4 ACTION3에서 DEAD
# 관찰: enemy가 (25,26)에서 (37,14)로 이동! → charge 모델?

# (유저 힌트: "f/b 픽셀이 눈이다. 시야 반경 1 내에 들어오면 잡아먹힌다")

# Claude의 판단:
#   "f(15)/b(11) 마커 = 적의 눈. eye offset → sight direction"
#   "eye가 보는 방향의 1 노드에 들어가면 DEAD"
#   → find_enemy_eye_direction() + get_sight_node() 구현
#   → sim_sight_cone: 적의 시야 노드 진입 = DEAD
```

**결과**: BFS가 경로를 찾지 못함! Sight cone이 경로를 완전히 차단. Naive fallback으로 반복 사망.

---

## Level 2 미해결 분석

### 적 구성 (3마리)

```
Enemy 1: (25, 25), eye=(0,1) RIGHT → sees node (25, 31)
Enemy 2: (25, 31), eye=(1,0) DOWN  → sees node (31, 31)
Enemy 3: (37, 13), eye=(0,1) RIGHT → sees node (37, 19)
```

### 왜 BFS가 경로를 못 찾는가

```
Agent: (31, 43) → Goal: (43, 25)

필요한 경로: 왼쪽+아래로 이동
장애물:
  - (31, 31)은 Enemy 2의 시야 노드 → 진입 불가
  - (25, 31)은 Enemy 2 자체 → 직접 수평 진입 불가
  - (37, 19)는 Enemy 3의 시야 노드 → 진입 불가

→ 시야 노드를 피하면서 목표에 도달하는 경로가 없는 것처럼 보임
→ 실제로는 SWAP으로 적을 밀어내서 시야 방향을 바꿀 수 있을 것
→ BFS가 SWAP 후 적의 eye direction 변화를 모델링하지 않음
```

### 해결을 위해 필요한 것

```
1. SWAP 후 적의 eye direction이 바뀌는지 관찰 필요
2. 적이 이동했을 때 sight cone도 함께 이동하는지 확인
3. BFS 상태에 (agent, enemy1, enemy2, enemy3) 모두 포함 → 상태 공간 폭발 주의
4. 적 3마리의 sight cone이 만드는 "safe corridor"를 찾는 전략
```

---

## 시뮬레이터 버전 히스토리 (SFT 데이터 원형)

| Version | Step | Trigger | Rules | Confidence | Result |
|---------|------|---------|-------|------------|--------|
| v1 | 4 | epistemic probes | graph_movement only | 0.8 | L0 ✓ (17 steps) |
| v2 | 21 | enemy discovered | + horizontal_DEAD, vertical_SWAP | 0.7 | L1 ✓ (10 steps) |
| v3 | 55 | L2 death | + sight_cone (eye direction) | 0.6 | L2 ✗ (no path found) |
| v4 (needed) | - | - | + SWAP changes enemy position/sight | - | L2 해결 예상 |

### 각 버전 전환의 SFT 데이터 형태

```
v1→v2 transition:
  Input:  "Level 1 시작. 새 엔티티 발견: 8-block with f(15) marker at (28,37).
           이전 시뮬레이터: graph movement only."
  Output: "시뮬레이터 업데이트:
           - 새 규칙: if agent enters enemy cell horizontally → DEAD
           - 새 규칙: if agent enters enemy cell vertically → SWAP (enemy goes to agent's old pos)
           - BFS 상태 확장: (agent_pos, enemy_pos) tuple
           Confidence: 0.7 (Level 1 아침 세션 경험 기반)"

v2→v3 transition:
  Input:  "Level 2에서 ACTION3(LEFT)로 step 4에서 사망.
           Enemy (25,25)에 f marker at offset (0,1) → RIGHT.
           Agent가 enemy의 오른쪽 방향 1노드에 진입했을 때 사망."
  Output: "시뮬레이터 업데이트:
           - 새 함수: find_enemy_eye_direction(center, block_vals)
           - 새 함수: get_sight_node(enemy, eye_dir, adj)
           - 새 규칙: if agent enters enemy's sight node → DEAD
           - 적의 'eye'는 f/b marker의 block 내 offset으로 결정
           Confidence: 0.6 (1회 관찰, 미검증)"
```

---

## 발견된 버그 및 수정

### Bug 1: 규칙 중복 (Critical)
- **증상**: simulator mechanics 232개로 폭발
- **원인**: `update_from_surprise()`가 매번 `belief_state.dynamics_rules` 전체를 재추가
- **수정**: `existing_source_ids` 체크로 이미 있는 규칙은 confidence만 갱신

### Bug 2: NL 방향 파싱 오류
- **증상**: "ACTION2→move_left" (실제: down)
- **원인**: DynamicsRule 텍스트의 "left" 키워드를 우선 추출
- **수정**: `action_name`에서 방향 우선 추출 (DEFAULT_ACTION_DIRECTIONS)

### Bug 3: 같은 실패 반복 (Design flaw)
- **증상**: Level 2에서 같은 경로로 20+ 번 사망
- **원인**: BFS 실패 시 naive fallback → 같은 경로 → 같은 사망. 학습 없이 반복.
- **미수정**: 실패 후 다른 전략 시도 로직 필요 (epistemic probe, 다른 경로 등)

---

## 핵심 교훈

### 1. 시뮬레이터 진화는 실제로 작동한다
v1(그래프만)→v2(적 충돌)→v3(sight cone)로 점진적 업그레이드가 가능했고, 각 버전이 이전 버전이 풀지 못한 레벨을 풀었다.

### 2. "같은 실패를 반복하지 않는" 메커니즘이 필수
가장 큰 action 낭비는 시뮬레이터가 틀렸을 때 같은 경로를 반복 시도한 것. 실패 감지 → 전략 변경 → epistemic probe가 자동으로 일어나야 한다.

### 3. 시뮬레이터 빌드에는 LLM이 필수
Pattern matching(solve_loop 기반)으로는 "3x3 블록이 그래프 노드를 점프" 같은 구조적 이해가 불가능. Claude Code가 직접 시뮬레이터를 짰을 때만 작동했다.

### 4. 적 행동은 레벨마다 복잡해진다
L0(적 없음) → L1(단순 충돌/SWAP) → L2(sight cone + 다수 적). 시뮬레이터도 레벨에 맞춰 점진적으로 복잡해져야 한다.

### 5. 1 scorecard 안에서 시뮬레이터를 진화시키는 게 핵심
5개 scorecard(게임 5번 시작)와 1개 scorecard(1번 시작, 내부에서 RESET) 차이:
- 5개: ~150 actions 낭비 (Level 0을 5번 반복)
- 1개: 31 actions으로 Level 0+1 클리어

### 6. 이 과정이 SFT 데이터의 원형
(관찰, 시뮬레이터_코드, 예측, 실패, 수정) 튜플이 SLM 훈련 데이터가 된다. 지금 남긴 로그가 나중에 Qwen에게 "시뮬레이터를 짜는 법"을 가르치는 데 사용된다.

---

## Level 2 추가 시도 (v3-sight-eat)

v3 시뮬레이터(sight cone + eat via SWAP)로 BFS가 15-step 경로를 찾았으나, **step 7 ACTION2에서 항상 사망.** 25회 반복 시도 모두 같은 지점에서 실패 (944 actions 소비).

```
경로: ACTION4, ACTION1, ACTION3×4, ACTION2(←여기서 사망), ...
문제: v3가 step 7을 "safe"로 판단하지만 실제로는 적에게 잡힘
원인 추정: 
  - 적의 시야가 1 노드가 아닌 더 넓을 수 있음
  - 적이 이동하면서 시야 방향이 바뀔 수 있음
  - SWAP 후 적의 재배치가 시뮬레이터와 다를 수 있음
  - 적이 3마리라 상호작용이 복합적
```

**핵심 미해결**: 시뮬레이터 예측과 실제의 불일치를 1 step씩 관찰해서 정확한 원인 파악 필요.

## 최종 RHAE 결과

```
L0: 17 actions (human baseline 125) → RHAE = 1.0000 (만점)
L1:  8 actions (human baseline  58) → RHAE = 1.0000 (만점)
L2:  미해결 (시뮬레이터 v3 부정확)
```

## 다음 단계

1. **Level 2 디버그**: step 7에서 실제로 무엇이 일어나는지 1 action 단위 관찰
2. **시뮬레이터 v4**: 관찰 기반으로 적 행동 모델 수정 (시야 범위? 이동 시 시야 변경?)
3. **같은 실패 반복 방지**: 같은 경로로 2번 이상 죽으면 자동으로 전략 변경
4. **LLM 연동**: Claude API 또는 로컬 Qwen을 시뮬레이터 코드 생성에 연결
5. **다른 게임 시도**: tu93 외 게임에서 시뮬레이터 진화 루프 검증

---

## Architecture Insight: Per-Game Simulator Files

### 현재 코드의 두 층

```
simulator.py (abstract framework — 파일로 저장됨)
  ├── GameState, EntityState       — 범용 상태 표현
  ├── MechanicRule                 — 실행 가능 규칙 (condition_fn + effect_fn)
  ├── Simulator                    — predict() + search_bfs() + search_safe_bfs()
  ├── SimulatorBuilder             — belief → simulator 변환, surprise 업데이트
  └── pattern matching 변환기       — DynamicsRule NL → callable (범용이지만 부정확)

tu93 전용 코드 (bash 스크립트 안에서 즉석 작성 — 파일로 안 남음!)
  ├── parse_graph()                — 64x64 그리드 → 3x3 블록 그래프 추출
  ├── sim_v1~v5()                  — (agent, enemies, action) → (new_agent, new_enemies, alive)
  ├── eye_dir() + sight_node()     — 적의 눈 방향 → 시야 노드 계산
  └── bfs_full()                   — (agent, enemy_tuple) 상태 공간 BFS
```

**문제**: 실제로 게임을 풀었던 건 tu93 전용 코드인데, 이게 파일로 남지 않음.

### 올바른 구조 (다음 단계)

```
agents/agentic/
  simulator.py                     — abstract base (이미 있음)
  simulators/                      — 게임별 시뮬레이터 (NEW)
    __init__.py
    tu93_simulator.py              — parse_graph + sight_cone + eat/swap
    ls20_simulator.py              — 블록 이동 + 패턴 영역
    sk48_simulator.py              — ...
    common_patterns.py             — 재사용 가능한 패턴 (graph_movement, sight_cone 등)
```

### 왜 파일로 남아야 하는가: Kaggle 시나리오

```
Kaggle 6시간, 110 games:

tu93 첫 번째 시도:
  → 탐색 4 actions → 시뮬레이터 v1 (그래프 이동만)
  → L0 클리어 → L1 사망 → v2 (적 SWAP)
  → L0+L1 클리어 → L2 사망 → v3 (sight cone)
  → 저장: simulators/tu93_simulator_v3.py
  → 결과: 2 levels

tu93 두 번째 시도 (시간 남으면):
  → tu93_simulator_v3.py 로드 ← 처음부터 안 배워도 됨!
  → v3에서 바로 시작, L0+L1은 이미 아는 경로로 리플레이
  → L2 적 행동 추가 관찰 → v4 업그레이드
  → 저장: simulators/tu93_simulator_v4.py
  → 결과: 3+ levels (개선!)

cross-game transfer:
  → tu93에서 배운 "sight cone" 패턴
  → 다른 게임에서 비슷한 구조 (적 + 눈 마커) 보이면
  → common_patterns.py의 sight_cone 로직을 템플릿으로 재사용
  → 탐색 비용 대폭 절감
```

### 시뮬레이터 파일 = Cross-Game Memory

master-plan-gpt에서 말한 **episode memory vs cross-game memory**의 구현:

```
episode memory   = data/episodes/{game}-{id}/  (한 에피소드 내 관찰/가설/결정)
cross-game memory = agents/agentic/simulators/  (게임별 시뮬레이터 코드)

episode memory는 "이번 게임에서 뭘 관찰했는가"
cross-game memory는 "이 게임의 물리법칙을 코드로 알고 있다"

전자는 데이터, 후자는 실행 가능한 지식.
```

### 시뮬레이터 파일의 SFT 데이터 가치

각 게임별 시뮬레이터 파일의 **git diff history**가 SFT 데이터가 됨:

```
v1 → v2 diff: "적 발견 → SWAP/DEAD 규칙 추가"
  Input:  "새 엔티티 8-block 발견, f 마커 포함"
  Output: "if new_ag == en: if vertical → SWAP; else → DEAD"

v2 → v3 diff: "L2 사망 → sight cone 규칙 추가"
  Input:  "step 9 ACTION2에서 사망. enemy의 f offset=(0,1)"
  Output: "eye_dir 함수 추가, sight_node에 진입하면 DEAD"

이런 (관찰, 코드 diff) 쌍이 SLM에게
"관찰을 시뮬레이터 코드 수정으로 변환하는 법"을 가르치는 데이터
```

---

## Files Changed

```
NEW: agents/agentic/simulator.py (~500 lines)
MOD: agents/agentic/schemas.py (SimulatorSnapshot, SimulatorEvolutionEntry, TrajectoryRecord fields)
MOD: agents/agentic/solve_loop.py (simulator integration, build/predict/verify/update loop)
MOD: agents/agentic/memory.py (simulator evolution logging)
NEW: docs/strategy/search-strategies-comparison.md
NEW: docs/strategy/simulator-building-approach.md
MOD: docs/strategy/master-plan-gpt.md (simulator as code section added)
```

## Data Generated

```
data/episodes/tu93-2b534c15-*/
  simulator/evolution.jsonl — 시뮬레이터 진화 로그
  simulator/simulator_v*.json — 버전별 스냅샷
  steps/step_NNNN.{observation,belief,decision}.json — 스텝별 상세
```
