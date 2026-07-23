<!-- [Mar 30] Created by SD with Claude Opus 4.6. -->
# ARC-AGI-3 Master Plan

## 유저 프롬프트 아카이브

### 2026-03-30: World Model Agent 방향 설정

> 주어진 64x64 그리드를 단순히 4096짜리 픽셀로만 보는 것이 아니라, 주요 오브젝트를 기반으로 인지해야 할 것이며, 어떤 조작(action)이 가해졌을 때, 어떤 로직으로 인해서, 그리드 내의 오브젝트가 어떻게 변했는지, 그래서 64x64 그리드가 어떻게 변할 지 예측을 정확히 해 내야 한다. 이런 게 월드 모델이잖아. 그것이 확실하게 가능한 상황에서 planning을 수행해야 하는 task이지.
>
> 너는 프로그램을 짜는 것이 목적인 agent이니까 이 로직이 적용되는 environment를 문제를 풀어나가는 과정 중에 구체화해야 할 것이야. 기존의 학습 방법은 training phase를 따로 두고, model dynamics를 대량의 데이터로 학습해 나가곤 했지만, 이 ARC-AGI-3 task에서는 너가 가진 prior knowledge를 바탕으로, 이 행위를 문제를 푸는 과정 동안 즉각적으로 해 나가야 할 거야.
>
> Prior는 Elizabeth S. Spelke and Katherine D. Kinzler. Core knowledge. Developmental science, pages 89–96, 2007 논문에서 따다 썼다고 하니까, 참고하고.
>
> 문제를 풀어나가기 위한 action을 수행하였는데, 생각지 못한 현상을 발견한다면, 가지고 있는 가설을 유연하게 바꿀 수 있는 능력이 있어야돼. 이 말인즉슨, 한 스텝 한 스텝 수행하는 과정 중에도, 문제를 서술하는 코드베이스가 바뀔 수 있어야 하며, 그 과정동안 너가 알아낸 것들에 대한 컨피던스가 점차 높아지길 기대해야 할거야. 그리고 정답을 달성하기 위한 planning 역시 더 구체화되어야 할 것이고.

### Core Knowledge Priors (Spelke & Kinzler, 2007)
ARC-AGI-3 게임은 아래 4가지 핵심 지식만으로 풀 수 있도록 설계됨:
1. **Objectness**: 세계는 구별 가능한 개체(object)로 이루어져 있다
2. **Basic Geometry**: 물체는 공간적 위치, 크기, 모양을 가진다
3. **Basic Physics**: 물체는 연속적으로 이동하고, 충돌하고, 겹치지 않는다
4. **Agentness**: 일부 개체는 자발적으로 행동한다 (플레이어, 적 등)

---

## 작업 순서

### Phase A: World Model Agent로 sk48 해결 (Claude Code)
environment_files 절대 참조 불가. 관찰만으로 dynamics를 코드화.

**매 스텝 루프:**
```
1. OBSERVE: 그리드 → 오브젝트 식별 (Core Knowledge: objectness)
2. ACT: 액션 수행 → diff 관찰
3. HYPOTHESIZE: diff를 설명하는 Python 함수 작성
   def action1_effect(objects) -> predicted_changes
4. PREDICT: 다음 액션의 결과를 예측
5. VERIFY: 실제 결과와 비교 → confidence 업데이트
6. REVISE: 예측 틀리면 함수 수정
7. PLAN: dynamics가 확실하면 → 최적 액션 시퀀스 계산
```

**산출물:**
- `dynamics/sk48_model.py` — 발견한 게임 로직 코드
- `dynamics/sk48_solution.py` — 계획된 솔루션
- 매 스텝의 (관찰, 가설, 예측, 결과, 수정) 기록

### Phase B: World Model Agent 프레임워크 설계
sk48 경험을 일반화하여 모든 게임에 적용 가능한 프레임워크 구축.

**모듈 구성:**
```
world_model_agent/
  object_detector.py    — 그리드 → 오브젝트 목록 (이미 grid_lib.py에 있음)
  dynamics_builder.py   — diff 관찰 → Python 함수 생성
  predictor.py          — dynamics 함수로 다음 상태 예측
  confidence_tracker.py — 가설별 신뢰도 추적
  planner.py            — dynamics 확정 후 최적 경로 탐색
```

### Phase C: Qwen 4B에 이식
Claude Code가 하는 것을 Qwen 4B가 할 수 있게.

**전이 가능한 것 vs 코드로 남겨야 하는 것:**
| 능력 | Qwen 4B 가능? | 방법 |
|------|--------------|------|
| 오브젝트 식별 | ✅ | 코드 (grid_lib) |
| 액션 효과 분류 | ✅ | SFT (diff → "이동"/"회전"/"토글") |
| dynamics 코드 생성 | △ | 템플릿 기반 코드 생성 |
| 예측-검증 루프 | ✅ | 코드 (predictor) |
| 가설 수정 | △ | SFT (잘못된 예측 → 수정된 가설) |
| 최적 경로 계획 | ✅ | 코드 (BFS/DFS) |

**SFT 데이터**: Phase A에서 생성한 (관찰, 가설코드, 수정, 최종코드) 쌍

### Phase D: Scorecard 검증
- 온라인 모드로 25개 게임 평가
- Phase A의 sk48 + 다른 게임들

### Phase E: Kaggle 노트북
- Qwen 4B + World Model 프레임워크 패키징
- 오프라인 실행 (인터넷 없음)
- `kaggle_submission.ipynb` 업데이트

---

---

## 서술형 분석: 왜 World Model이고, 어떻게 해야 하는가

### 1. 문제의 본질

ARC-AGI-3는 근본적으로 **시간 압박 하의 과학적 발견** 문제다. 에이전트는 완전히 미지의 게임에 던져진다. 규칙서도 없고, 목표 설명도 없고, 튜토리얼도 없다. 오직 64×64 그리드와 몇 개의 버튼만 있을 뿐이다. 이 상태에서 에이전트는:

- 그리드 안의 개체(object)가 무엇인지 식별하고
- 각 버튼(action)이 무엇을 하는지 발견하고
- 게임의 목표가 무엇인지 추론하고
- 목표를 달성하는 최적의 행동 시퀀스를 계획하고 실행해야 한다

이것은 사실상 **한 사람이 처음 보는 퍼즐 게임을 앞에 두고 하는 것**과 정확히 같다. 사람은 이것을 100% 성공률로 해낸다. 현재 최고의 AI(Gemini 3.1 Pro)는 0.37%다. 이 격차의 원인이 무엇인가?

### 2. 기존 접근법이 실패하는 이유

**StochasticGoose (CNN, 12.58% 1위)**: "프레임이 변했으면 좋은 액션"이라는 휴리스틱을 사용한다. 이것은 탐색에는 효과적이지만, 목표를 이해하거나 계획을 세우는 능력이 전혀 없다. 아기가 버튼을 누르고 화면이 바뀌면 좋아하는 것과 같다. 튜토리얼 레벨은 우연히 풀 수 있지만, 복잡한 레벨은 절대 못 푼다.

**LLM 에이전트 (Claude/GPT, <1%)**: 원칙적으로 게임에 대해 추론할 수 있지만:
- 64×64 그리드를 텍스트로 표현하면 수천 토큰이 되어 공간 추론이 불가능
- 스텝 간에 지속되는 월드 모델이 없다 (매번 처음부터 분석)
- 실행 가능한 dynamics 코드를 즉석에서 작성하고 실행하는 체계가 없다
- 컨텍스트 윈도우가 그리드 데이터로 가득 차버린다

**빠진 조각**: 두 접근법 모두 **월드 모델(world model)** — 게임이 어떻게 작동하는지에 대한 실행 가능한 표현 — 을 구축하지 않는다.

### 3. 내가 ls20을 풀었을 때 실제로 한 것

Session 1에서 유저와 함께 ls20을 풀었을 때, 나는 무의식적으로 월드 모델을 구축하고 있었다. 그 과정을 분해해보면:

**지각 (Perception)**: 2D 맵을 보고 오브젝트를 식별했다.
- 값 12/9의 5×5 블록 → "이건 플레이어 같다" (Objectness prior)
- 넓은 값 3 영역 → "바닥" (배경 vs 전경 구분)
- 값 4 영역 → "벽, 갈 수 없는 곳" (Physics prior: 물체는 충돌한다)
- 값 0/1의 작은 클러스터 → "상호작용 가능한 오브젝트" (Agentness prior)

나는 4096개의 픽셀을 본 것이 아니다. **"플레이어가 R45에 있고, 벽이 C29-33에 있고, 회전기가 R31에 있다"**를 봤다.

**액션 매핑**: 각 액션을 한 번씩 테스트하고 diff를 분석했다.
- ACTION1 → 52셀 변화, 12/9 블록이 5칸 위로 이동 → `player.y -= 5`
- ACTION2 → 2셀만 변화 → "아래로 막혀있다, 벽 충돌"
- ACTION3 → 52셀 변화, 블록이 왼쪽으로 → `player.x -= 5`

이 시점에서 나는 이미 머릿속에 코드를 작성하고 있었다:
```python
def move_player(pos, action):
    if action == UP: new_pos = (pos[0]-5, pos[1])
    elif action == DOWN: new_pos = (pos[0]+5, pos[1])
    # ...
    if grid_at(new_pos) == 4: return pos  # 벽이면 안 움직임
    return new_pos
```
confidence: ~90% (한 번의 관찰로도 꽤 확실)

**상호작용 발견**: 플레이어가 0/1 오브젝트와 겹쳤을 때:
- 58셀 변화 (평소 52보다 6셀 더) → "무언가 추가로 변했다"
- R55-60의 키 디스플레이가 변화 → "키가 회전했다!"
- dynamics 업데이트: `if player.overlaps(rotator): key = rotate_90cw(key)`

**목표 추론**:
- 상단 박스에 고정된 패턴 (타겟 키)
- 하단에 변하는 패턴 (현재 키)
- 키가 일치한 상태에서 박스에 들어가면 → 레벨 클리어
- `win_condition = (current_key == target_key) and player_in_target_box`

**계획 수립**: dynamics가 확정된 후:
- 필요한 회전 횟수 계산 (현재→타겟: 1회)
- 최단 경로: 시작→회전기→타겟 박스
- 에너지 고려: 각 스텝은 에너지 1 소모
- 경로: UP×4, LEFT×3, DOWN(회전기), UP, RIGHT×3, UP×3(출구) = 16 액션

이 전체 과정을 **코드로 명시적으로** 수행했다면, 더 빠르고 정확하고 재현 가능했을 것이다.

### 4. 코드를 월드 모델로 사용하는 이유

월드 모델을 신경망 가중치가 아닌 **실행 가능한 Python 코드**로 표현하면:

1. **해석 가능**: 코드를 읽고 "이 규칙이 맞는가?" 판단 가능
2. **테스트 가능**: 예측을 실행하고 현실과 비교 가능
3. **수정 가능**: 예측이 틀리면 특정 줄을 고치면 됨 (신경망은 전체 재학습 필요)
4. **전이 가능**: 코드 구조(템플릿)는 새 게임에서도 재사용 가능
5. **효율적**: 학습 데이터 불필요, 몇 번의 관찰로 충분

Claude Code는 본질적으로 **코드를 작성하는 에이전트**이므로 이것이 자연스럽다.

### 5. 구체적 아키텍처: 매 스텝의 사고 과정

게임의 매 스텝에서 에이전트가 수행해야 할 것:

**Step 1 — 지각적 그라운딩 (Perceptual Grounding)**

원시 그리드를 심볼릭 표현으로 변환한다. Core Knowledge가 여기서 작동한다:

Objectness: 같은 값의 연결된 셀 집합이 오브젝트를 형성한다. 하지만 더 세밀하게:
- 값 12와 9가 섞인 5×5 블록은 두 개의 오브젝트가 아니라 **하나** (플레이어)
- 값 11이 42칸 연속으로 있으면 42개의 점이 아니라 **하나** (에너지 바)
- 전체의 30%를 차지하는 값 3은 오브젝트가 아니라 **배경**

이것을 자동화하는 코드:
```python
def perceive(grid):
    value_freq = Counter(grid.flatten())
    bg_values = {v for v, c in value_freq.items() if c > 64*64*0.15}
    objects = []
    for value in set(range(16)) - bg_values:
        components = find_connected_components(grid, value)
        for comp in components:
            objects.append(Object(value, cells=comp, bbox=bbox(comp)))
    return objects, bg_values
```

**Step 2 — 액션 효과 분류**

diff를 분석하여 "무슨 일이 일어났는가"를 구조적으로 분류:

```python
def classify_effect(prev_objects, curr_objects):
    for prev in prev_objects:
        curr = find_match(curr_objects, prev)
        if curr is None: yield ("DISAPPEARED", prev)
        elif curr.center != prev.center: yield ("MOVED", prev, delta)
        elif curr.shape != prev.shape: yield ("TRANSFORMED", prev, curr)
    for curr in curr_objects:
        if no_match(prev_objects, curr): yield ("APPEARED", curr)
```

패턴이 나타난다:
- "ACTION1은 항상 플레이어를 (-5, 0)만큼 이동시킨다" → 이동 규칙
- "ACTION1은 위에 벽(4)이 있으면 플레이어를 이동시키지 않는다" → 충돌 규칙
- "오브젝트 X와 겹치면 디스플레이 Y가 변한다" → 상호작용 규칙

**Step 3 — Dynamics 코드 생성 (핵심!)**

관찰된 효과를 저장하는 것이 아니라, **실행 가능한 Python 코드를 생성**한다:

```python
# dynamics/sk48_model.py — 점진적으로 작성됨

class SK48World:
    def __init__(self, grid):
        self.player = detect_player(grid)
        self.trail = detect_trail(grid)
        self.targets = detect_targets(grid)
        self.energy = detect_energy(grid)

    def step(self, action):
        if action == "ACTION1":
            self.player.y -= 6  # 발견: 6칸씩 이동
        elif action == "ACTION4":
            self.trail.extend_right(6)  # 발견: 우로 확장
        elif action == "ACTION3":
            self.trail.retract_right(6)  # 발견: 우에서 축소
        # ... 관찰할 때마다 규칙 추가

    def predict_grid(self):
        grid = np.full((64, 64), BACKGROUND)
        self.player.draw(grid)
        self.trail.draw(grid)
        for t in self.targets:
            t.draw(grid)
        return grid
```

이 코드는 **한 번에 완성되는 것이 아니라, 매 관찰마다 점진적으로 확장**된다. 첫 번째 관찰 후에는 `step()` 함수에 규칙이 하나만 있고, 10번의 관찰 후에는 5-6개의 규칙이 있을 것이다.

**Step 4 — 예측-검증 루프**

매 액션 전에:
1. dynamics 코드로 다음 상태를 **예측**
2. 실제로 액션을 수행하고 **관찰**
3. 예측과 현실을 **비교**
4. 일치하면 → 해당 규칙의 confidence 증가
5. 불일치하면 → 어떤 규칙이 틀렸는지 식별하고 **수정**

```python
predicted_grid = world.predict_grid()
actual_grid = take_action_and_observe(action)
diff = compare(predicted_grid, actual_grid)

if diff.num_cells == 0:
    confidence[action_rule] += 0.1  # 예측 정확!
else:
    unexpected = analyze_unexpected_changes(diff)
    # "예측 안 했는데 R55-60이 변했다 → 상호작용 규칙 누락"
    world.add_rule(new_interaction_rule)
    confidence[action_rule] -= 0.05  # 불완전했음
```

**Step 5 — Confidence 기반 의사결정**

confidence 수준에 따라 행동 전략이 달라져야 한다:

- confidence < 0.3: 아직 모르는 게 많다. **탐색 모드** — 안 해본 액션 테스트, 안 가본 영역 방문
- confidence 0.3-0.7: 대략적 이해. **가설 검증 모드** — 특정 가설을 테스트하는 액션 수행
- confidence > 0.7: 대부분 이해. **계획 수립 모드** — 목표를 향한 최적 경로 계산 시작
- confidence > 0.9: 거의 확실. **실행 모드** — 계획 실행

**Step 6 — 계획 수립과 실행**

dynamics가 충분히 확정되면, 이것은 **알려진 상태 공간에서의 탐색 문제**가 된다:

```python
def plan(world_model, goal):
    initial = world_model.get_state()
    queue = [(initial, [])]
    visited = {initial}

    while queue:
        state, actions = queue.pop(0)
        if world_model.is_goal(state):
            return actions  # 최적 액션 시퀀스!
        for action in world_model.available_actions:
            next_state = world_model.simulate(state, action)
            if next_state not in visited:
                visited.add(next_state)
                queue.append((next_state, actions + [action]))
    return None
```

### 6. Qwen 4B로의 이식 전략

Claude Code가 하는 것을 Qwen 4B가 할 수 있게 만드는 것이 Phase C의 과제다. 핵심은 **무엇이 코드로 남고, 무엇을 모델이 해야 하는가**를 구분하는 것이다.

**코드로 고정하는 것** (학습 불필요):
- 오브젝트 감지 (grid_lib.py에 이미 있음)
- diff 계산 및 분류
- 예측-검증 루프의 구조
- BFS/DFS 기반 경로 탐색
- 에너지 추적

**Qwen 4B가 해야 하는 것** (SFT로 학습):
- 액션 효과 분류: "52셀 변화, 블록이 위로 5칸" → `MOVEMENT(UP, 5)`
- 적합한 dynamics 템플릿 선택: `MOVEMENT` / `ROTATION` / `TOGGLE` / `PUSH` / `BOUNDARY_SHIFT`
- 예측 실패 시 수정 방향 제안: "추가 변화 발견 → INTERACTION 규칙 추가"
- 목표 추론: "타겟 패턴과 현재 패턴의 차이 → 회전 3회 필요"

**SFT 데이터 형식** (Phase A에서 생성):
```jsonl
{"input": "Objects: player(12/9) at R40 C29. ACTION1 test: 54 cells changed, player at R35 C29.", "output": "TEMPLATE: movement, object=player, direction=UP, step=5, confidence=0.9"}
{"input": "Predicted 50 cells change, got 58. Extra: R55 changed 9→14.", "output": "REVISION: add_interaction(player, rotator_at_R46_C30, effect=color_cycle_3)"}
{"input": "Dynamics confirmed. Goal: key(111/001/101) → target(111/100/101). Rotator does 90CW.", "output": "PLAN: 3 rotations needed. Path: reach_rotator(17 steps) → rotate×3 → reach_exit"}
```

이렇게 하면 Qwen 4B는 **분류와 자연어 추론만** 하면 되고, 무거운 작업(코드 실행, 예측, 계획)은 고정 코드가 처리한다.

### 7. 리스크와 대비

1. **Claude Code도 많은 게임을 못 풀었다** (8/25 L1+). 월드 모델 접근이 도움은 되겠지만 만능은 아니다. → 대비: StochasticGoose CNN을 fallback으로 유지

2. **Qwen 4B의 분류 정확도가 낮을 수 있다** → 대비: confidence가 낮으면 CNN fallback 사용

3. **계획 수립의 상태 공간이 너무 클 수 있다** → 대비: A* 탐색에 휴리스틱 적용 (맨해튼 거리 등)

4. **Kaggle 시간 제한** → 대비: dynamics 발견에 최대 30초, 이후 계획+실행. 시간 초과 시 CNN으로 전환

---

## 핵심 원칙

1. **픽셀이 아닌 오브젝트로 사고**: 64x64 = 4096 픽셀이 아니라, "5x5 플레이어가 (R40,C29)에 있다"
2. **관찰 → 코드화**: "경계가 4칸 이동했다"를 `boundary += 4`로 즉시 코드화
3. **예측 → 검증**: 코드가 맞으면 confidence++, 틀리면 수정
4. **계획은 dynamics 확정 후**: 확실한 규칙 위에서만 최적 경로 계산
5. **유연한 가설 수정**: 예상 밖 현상 → 기존 가설 폐기하고 새 가설
6. **test-time 즉시 학습**: 별도 training phase 없이, 플레이하면서 배운다
