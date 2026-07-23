# The Simulator-Building Approach (and Alternatives)
# 시뮬레이터 구축 접근법 (및 대안들)

> The strongest approach to ARC-AGI-3 is building an environment simulator on-the-fly, then planning against it. This document explains why, how, and what alternatives exist.
> ARC-AGI-3에 대한 가장 강력한 접근법은 환경 시뮬레이터를 실시간으로 구축한 뒤 이를 기반으로 계획하는 것이다. 이 문서는 그 이유, 방법, 그리고 존재하는 대안들을 설명한다.

---

## 1. Why Build a Simulator?
## 1. 왜 시뮬레이터를 만들어야 하는가?

### The Core Economics / 핵심 경제학

```
Without simulator:  "What happens if I go RIGHT?"  → must ask real game → 1 action consumed
With simulator:     "What happens if I go RIGHT?"  → compute in memory  → 0 actions consumed
```

```
시뮬레이터 없이:  "RIGHT 가면 어떻게 돼?"  → 실제 게임에 물어야 함 → 1 액션 소비
시뮬레이터 있으면: "RIGHT 가면 어떻게 돼?"  → 메모리에서 계산       → 0 액션 소비
```

In ARC-AGI-3, score = `min(1.0, human/agent)²`. Every wasted action **squares** the penalty.

ARC-AGI-3에서 점수 = `min(1.0, human/agent)²`. 낭비된 액션은 패널티를 **제곱**한다.

```
Human baseline: 10 actions
Agent uses 10:  score = (10/10)² = 1.00  (perfect)
Agent uses 15:  score = (10/15)² = 0.44  (less than half!)
Agent uses 20:  score = (10/20)² = 0.25  (quarter credit)
Agent uses 30:  score = (10/30)² = 0.11  (barely anything)
```

**Every action spent on exploration instead of execution directly destroys score.**

**탐색에 쓴 액션은 곧바로 점수를 파괴한다.**

A simulator converts exploration cost from "real actions" to "compute time" — a dramatically better tradeoff.

시뮬레이터는 탐색 비용을 "실제 액션"에서 "계산 시간"으로 전환한다 — 극적으로 나은 트레이드오프.

---

## 2. The Four-Phase Loop
## 2. 4단계 루프

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: EXPLORE (spend real actions, small budget)             │
│ 1단계: 탐색 (실제 액션 소비, 적은 예산)                           │
│                                                                 │
│   Send a few actions to the real game and observe:              │
│   실제 게임에 몇 개 액션을 보내고 관찰:                             │
│                                                                 │
│   ACTION1 → agent jumps up 3 cells                              │
│   ACTION4 → agent jumps right, enemy doesn't move               │
│   ACTION4 → agent jumps right, enemy still doesn't move         │
│   ACTION4 → GAME_OVER! enemy rushed toward agent                │
│                                                                 │
│   Cost: 4 real actions                                          │
│   Learned: movement = 3-cell jumps, enemy reacts when close     │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: MODEL (write simulator code, 0 action cost)           │
│ 2단계: 모델링 (시뮬레이터 코드 작성, 액션 비용 0)                  │
│                                                                 │
│   def simulate(state, action):                                  │
│       new_agent = move_on_graph(state.agent, action)            │
│       new_enemy = state.enemy                                   │
│       if same_row(new_agent, state.enemy):                      │
│           if distance(new_agent, state.enemy) <= 2:  # hypothesis│
│               new_enemy = move_opposite(state.enemy, action)    │
│       if new_agent == new_enemy:                                │
│           return DEAD                                           │
│       return State(new_agent, new_enemy)                        │
│                                                                 │
│   Cost: 0 actions (only LLM reasoning / code generation)       │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 3: PLAN (search over simulator, 0 action cost)           │
│ 3단계: 계획 (시뮬레이터 위에서 탐색, 액션 비용 0)                  │
│                                                                 │
│   Run BFS/MCTS/A* on the simulator:                             │
│   시뮬레이터 위에서 BFS/MCTS/A* 실행:                              │
│                                                                 │
│   for path in all_possible_paths:                               │
│       result = simulate(current_state, path)   # FREE!          │
│       if result == WIN:                                         │
│           best = shortest(path)                                 │
│                                                                 │
│   Test 10,000 paths → find optimal 10-step solution             │
│   10,000개 경로 테스트 → 최적 10스텝 해법 발견                     │
│                                                                 │
│   Cost: 0 actions (pure computation)                            │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 4: EXECUTE & VERIFY (spend real actions on best plan)    │
│ 4단계: 실행 및 검증 (최적 계획에 실제 액션 소비)                    │
│                                                                 │
│   Execute the planned path step by step:                        │
│   계획된 경로를 단계별로 실행:                                      │
│                                                                 │
│   Step 1: RIGHT → actual result matches prediction ✓            │
│   Step 2: RIGHT → matches ✓                                     │
│   Step 3: DOWN  → matches ✓                                     │
│   Step 4: RIGHT → MISMATCH! predicted safe, actual = enemy moved│
│                                                                 │
│   → Prediction failed → go back to Phase 1 with new data       │
│   → 예측 실패 → 새 데이터로 Phase 1로 복귀                        │
│                                                                 │
│   Cost: 4 actions (3 successful + 1 failed)                     │
│   Insight: distance threshold was wrong, update simulator       │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
                    (Loop back to Phase 2 with corrected model)
                    (수정된 모델로 Phase 2로 복귀)
```

### Total Cost Comparison / 총 비용 비교

```
Approach                    Exploration    Planning    Execution    Total
────────────────────────────────────────────────────────────────────────
Simulator-building          ~4 actions     0 actions   ~10 actions  ~14
  (with 1 correction)       +3 failed                  +7 remaining
                            = 7                         = 17         ~24 actions

Harness LLM (no sim)        N/A           N/A         30~50 trial   30~50 actions
CLI BFS oracle              N/A           ~48K engine  10 actions    10 (but hours of compute)
                                          calls
```

```
접근법                       탐색          계획         실행         합계
────────────────────────────────────────────────────────────────────────
시뮬레이터 구축              ~4 액션       0 액션       ~10 액션     ~14
  (수정 1회 포함)            +3 실패                    +7 나머지
                            = 7                         = 17         ~24 액션

Harness LLM (시뮬 없음)     N/A           N/A          30~50 시행   30~50 액션
CLI BFS 오라클               N/A           ~48K 엔진    10 액션      10 (하지만 수 시간)
                                          호출
```

---

## 3. When the Simulator Is Wrong
## 3. 시뮬레이터가 틀릴 때

**This is expected, not exceptional.** The simulator WILL be wrong initially.

**이것은 예외가 아니라 예상된 상황이다.** 시뮬레이터는 처음에 틀릴 것이다.

### The Correction Loop / 수정 루프

```
Iteration 1:
    Hypothesis: "Enemy mirrors when distance ≤ 2"
    Simulator predicts: RIGHT RIGHT RIGHT is safe
    Reality: GAME_OVER at step 3 (enemy moved at distance 3!)
    Update: change threshold to ≤ 3
    Cost: 3 wasted actions

Iteration 2:
    Hypothesis: "Enemy mirrors when distance ≤ 3"
    Simulator predicts: RIGHT RIGHT DOWN RIGHT RIGHT UP RIGHT RIGHT UP
    Reality: Works perfectly!
    Cost: 9 actions (optimal)

Total: 4 (explore) + 3 (failed plan) + 9 (successful plan) = 16 actions
vs. pure LLM trial-and-error: 40+ actions
```

### Key Design Principles / 핵심 설계 원칙

1. **Budget exploration**: Spend at most K actions on pure exploration (K ≈ 5~10% of human baseline)
2. **Falsifiable hypotheses**: Each rule in the simulator should be testable with a specific action
3. **Incremental refinement**: Don't try to get it perfect; get it good enough, then fix on failure
4. **Separate concerns**: Maze structure (easy to get right) vs. enemy behavior (hard, refine iteratively)

1. **탐색 예산**: 순수 탐색에 최대 K 액션 소비 (K ≈ 인간 기준의 5~10%)
2. **반증 가능한 가설**: 시뮬레이터의 각 규칙이 특정 액션으로 테스트 가능해야 함
3. **점진적 개선**: 완벽을 추구하지 말고, 충분히 좋게 만든 후 실패 시 수정
4. **관심사 분리**: 미로 구조(맞추기 쉬움) vs. 적 행동(어려움, 반복적으로 개선)

---

## 3.5. The Probabilistic Simulator: Confidence-Weighted Mechanics
## 3.5. 확률적 시뮬레이터: 신뢰도 기반 메카닉

A simulator doesn't need to be a binary "right or wrong" model. **Every discovered mechanic should carry a confidence score** that reflects how much evidence supports it. The simulator is a probabilistic belief system that sharpens over time.

시뮬레이터가 "맞다/틀리다"의 이분법일 필요는 없다. **발견된 모든 메카닉에 신뢰도 점수**가 있어야 하며, 이는 이를 뒷받침하는 증거의 양을 반영한다. 시뮬레이터는 시간이 지나면서 날카로워지는 확률적 신념 체계다.

### Why Probabilistic? / 왜 확률적인가?

In tu93, we discovered "the enemy moves when the agent approaches on the same row." But we couldn't pin down the exact trigger — distance ≤ 2? ≤ 3? Only when moving toward the enemy? Our simulation was wrong because we treated a **hypothesis** as a **fact**.

tu93에서 "에이전트가 같은 행에서 접근하면 적이 움직인다"를 발견했다. 하지만 정확한 트리거를 확정할 수 없었다 — 거리 ≤ 2? ≤ 3? 적을 향해 이동할 때만? 시뮬레이션이 틀린 이유는 **가설**을 **사실**로 취급했기 때문이다.

### Confidence Model / 신뢰도 모델

```python
class Mechanic:
    rule: str               # "enemy mirrors on same row"
    confidence: float       # 0.0 ~ 1.0
    evidence_for: int       # observations supporting this rule
    evidence_against: int   # observations contradicting this rule
    conditions: dict        # e.g., {"min_distance": 3, "axis": "horizontal"}

class ProbabilisticSimulator:
    mechanics: list[Mechanic]

    def predict(self, state, action) -> list[tuple[State, float]]:
        """Returns multiple possible next states with probabilities."""

        # High-confidence mechanics → deterministic prediction
        # Low-confidence mechanics → multiple branches

        # Example for tu93 level 1:
        # Mechanic: "enemy mirrors" (confidence=0.6, seen 2 times, failed 1 time)
        # → Branch A (60%): enemy moves opposite, agent safe at (28,31)
        # → Branch B (40%): enemy stays, agent safe at (28,31)
        #
        # Mechanic: "agent moves to next 0-node" (confidence=0.95, seen 8 times)
        # → deterministic: agent lands at (28,31)

        outcomes = []
        for scenario in self.enumerate_scenarios(state, action):
            prob = self.compute_probability(scenario)
            outcomes.append((scenario.result_state, prob))
        return outcomes
```

```python
class Mechanic:
    rule: str               # "적이 같은 행에서 미러링"
    confidence: float       # 0.0 ~ 1.0
    evidence_for: int       # 이 규칙을 지지하는 관찰 수
    evidence_against: int   # 이 규칙에 반하는 관찰 수
    conditions: dict        # 예: {"min_distance": 3, "axis": "horizontal"}

class ProbabilisticSimulator:
    mechanics: list[Mechanic]

    def predict(self, state, action) -> list[tuple[State, float]]:
        """여러 가능한 다음 상태를 확률과 함께 반환."""
        # 높은 신뢰도 메카닉 → 결정론적 예측
        # 낮은 신뢰도 메카닉 → 여러 분기
        ...
```

### How Confidence Evolves / 신뢰도의 진화

```
Level 0 (tutorial, no enemy):
    "agent moves in 3-cell jumps on graph nodes"     confidence: 0.95 (18 consistent observations)
    "2-blocks are connections, 0-blocks are nodes"    confidence: 0.99 (confirmed throughout)

Level 1 (enemy introduced):
    "enemy exists as 8/f block"                       confidence: 1.0  (directly observed)
    "enemy mirrors agent on same row"                 confidence: 0.3  (seen once, then violated)
    "enemy reacts only when agent is within 2 nodes"  confidence: 0.5  (limited data)
    → Agent uses high-confidence mechanics for navigation,
      treats enemy behavior as uncertain → plans conservatively

Level 2 (more complex):
    "enemy mirrors agent on same row"                 confidence: 0.7  (3 more confirmations)
    "enemy reacts within 2 nodes"                     confidence: 0.2  (contradicted!)
    "enemy reacts within 1 node (adjacent)"           confidence: 0.8  (new hypothesis, fits data)
    → Simulator now makes better predictions → fewer wasted actions
```

```
Level 0 (튜토리얼, 적 없음):
    "에이전트가 그래프 노드 위에서 3셀씩 점프"         신뢰도: 0.95 (18회 일관된 관찰)
    "2블록은 연결, 0블록은 노드"                      신뢰도: 0.99 (전체적으로 확인)

Level 1 (적 등장):
    "적이 8/f 블록으로 존재"                          신뢰도: 1.0  (직접 관찰)
    "적이 같은 행에서 에이전트를 미러링"               신뢰도: 0.3  (1회 관찰 후 위반)
    "적이 2노드 이내일 때만 반응"                      신뢰도: 0.5  (제한된 데이터)
    → 에이전트는 높은 신뢰도 메카닉으로 네비게이션,
      적 행동은 불확실하게 취급 → 보수적으로 계획

Level 2 (더 복잡):
    "적이 같은 행에서 미러링"                         신뢰도: 0.7  (3회 추가 확인)
    "2노드 이내 반응"                                신뢰도: 0.2  (반증됨!)
    "1노드(인접) 이내 반응"                           신뢰도: 0.8  (새 가설, 데이터에 부합)
    → 시뮬레이터가 더 나은 예측 → 낭비 액션 감소
```

### Planning Under Uncertainty / 불확실성 하에서의 계획

With a probabilistic simulator, planning becomes **risk-aware**:

확률적 시뮬레이터로 계획은 **위험 인식적**이 된다:

```
Path A: 8 steps, all high-confidence predictions → expected score: 0.85
Path B: 6 steps, but step 4 uses a low-confidence mechanic → expected score: 0.6
Path C: 10 steps, all high-confidence → expected score: 0.70

→ Choose Path A: longer than B, but safer.
→ Path A 선택: B보다 길지만 더 안전.
```

This is essentially **expectimax** or **risk-sensitive planning**, where the agent prefers paths through well-understood parts of the world model.

이것은 본질적으로 **expectimax** 또는 **위험 민감 계획**으로, 에이전트가 세계 모델에서 잘 이해된 부분을 통과하는 경로를 선호한다.

---

## 3.6. What Environment Code Tells Us About Simulator Design
## 3.6. 환경 코드가 시뮬레이터 설계에 알려주는 것

Examining actual ARC-AGI-3 game source code (e.g., wa30.py) reveals the **internal architecture** that our simulator must approximate. Even without reading every game's code, knowing the common structure helps.

실제 ARC-AGI-3 게임 소스 코드(예: wa30.py)를 보면 시뮬레이터가 근사해야 하는 **내부 아키텍처**가 드러난다. 모든 게임의 코드를 읽지 않더라도, 공통 구조를 아는 것은 도움이 된다.

### Common Game Architecture / 공통 게임 아키텍처

All ARC-AGI-3 games are built on `arcengine` with these primitives:

모든 ARC-AGI-3 게임은 `arcengine` 위에 다음 원시 요소들로 구축된다:

```python
# From arcengine:
Sprite(pixels, name, visible, collidable, tags, layer)
Camera(position, size)               # viewport into the world
Level(sprites, camera, actions)      # one level's configuration
ARCBaseGame                          # base class all games inherit

# A typical game defines:
# 1. sprites{} — named pixel arrays with collision/layer properties
# 2. levels[] — sequences of Level objects with sprite placements
# 3. step() — the core logic: how actions transform the world state
```

### What This Means for Simulator Design / 시뮬레이터 설계에의 시사점

```
Game internals:                    Simulator must model:
─────────────────────────────      ──────────────────────────────
Sprites with positions (x, y)   →  Entity tracking (who is where)
Collision detection              →  "Can agent move here?" checks
Layers (sprite rendering order)  →  Which entities block which
Tags on sprites                  →  Entity types (agent, enemy, wall, goal)
Camera / viewport               →  Visible area vs full world
Level transitions                →  Win conditions, state resets
```

```
게임 내부:                           시뮬레이터가 모델링해야 할 것:
─────────────────────────────      ──────────────────────────────
위치 (x, y)를 가진 스프라이트     →  엔티티 추적 (누가 어디에)
충돌 감지                         →  "에이전트가 여기로 갈 수 있나?" 체크
레이어 (스프라이트 렌더링 순서)   →  어떤 엔티티가 어떤 것을 막는지
스프라이트의 태그                 →  엔티티 유형 (에이전트, 적, 벽, 목표)
카메라 / 뷰포트                  →  가시 영역 vs 전체 세계
레벨 전환                        →  승리 조건, 상태 리셋
```

### The Simulator Is Not a Full Engine Clone / 시뮬레이터는 전체 엔진 복제가 아니다

We don't replicate `arcengine`. We build a **minimal abstract model** informed by what we observe:

`arcengine`을 복제하는 게 아니다. 관찰한 것에 기반한 **최소한의 추상 모델**을 만든다:

```python
# NOT this (impossible without reading game code):
class FullSimulator:
    def step(self, action):
        for sprite in self.sprites:
            sprite.update(action)           # unknown logic!
            self.check_collisions()          # unknown rules!
            self.check_win_condition()       # unknown condition!

# THIS (built from observations):
class ObservedSimulator:
    def step(self, action):
        # Mechanic 1: agent movement (confidence: 0.95)
        self.agent = self.graph.move(self.agent, action)

        # Mechanic 2: enemy response (confidence: 0.6)
        if self.enemy and self.same_axis(self.agent, self.enemy):
            if self.adjacent(self.agent, self.enemy):  # confidence: 0.8
                self.enemy = self.graph.move_opposite(self.enemy, action)

        # Mechanic 3: collision = death (confidence: 1.0)
        if self.agent == self.enemy:
            return GAME_OVER

        # Mechanic 4: reaching goal = win (confidence: 1.0)
        if self.agent == self.goal:
            return WIN
```

---

## 4. Implementation Architecture
## 4. 구현 아키텍처

```python
class SimulatorBuildingAgent(Agent):

    def __init__(self):
        self.phase = "explore"
        self.observations = []        # (state, action, next_state) tuples
        self.simulator = None         # Generated Python code
        self.plan = []                # Planned action sequence
        self.plan_index = 0           # Current position in plan

    def choose_action(self, frames, latest_frame):
        state = parse_grid(latest_frame)

        if self.phase == "explore":
            # Phase 1: Systematic exploration
            action = self.next_exploration_action(state)
            self.observations.append((state, action))
            if self.exploration_budget_exhausted():
                self.phase = "model"
            return action

        elif self.phase == "model":
            # Phase 2: Build simulator from observations
            self.simulator = self.llm_generate_simulator(self.observations)
            self.phase = "plan"
            return self.choose_action(frames, latest_frame)  # immediately plan

        elif self.phase == "plan":
            # Phase 3: Search over simulator
            self.plan = self.search(state, self.simulator)
            self.plan_index = 0
            self.phase = "execute"
            return self.choose_action(frames, latest_frame)  # immediately execute

        elif self.phase == "execute":
            # Phase 4: Execute plan, verify each step
            if self.plan_index >= len(self.plan):
                self.phase = "explore"  # plan exhausted without winning
                return self.choose_action(frames, latest_frame)

            action = self.plan[self.plan_index]
            predicted = self.simulator(state, action)
            self.plan_index += 1

            # Will verify prediction on next call
            self.last_prediction = predicted
            return action

    def on_frame_received(self, actual_state):
        """Called after each action to verify prediction"""
        if self.phase == "execute" and self.last_prediction:
            if actual_state != self.last_prediction:
                # Prediction failed! Record the discrepancy
                self.observations.append(discrepancy)
                self.phase = "model"  # Rebuild simulator
```

---

## 5. Alternative Approaches
## 5. 대안 접근법들

### 5a. Hybrid CNN + LLM (StochasticGoose++)
### 5a. 하이브리드 CNN + LLM (StochasticGoose++)

**Core idea**: Use a CNN to learn action→frame_change mappings online (like StochasticGoose), but add an LLM layer for high-level planning.

**핵심 아이디어**: CNN으로 액션→프레임변화 매핑을 온라인 학습하고 (StochasticGoose처럼), LLM 레이어로 고수준 계획을 추가.

```
CNN learns:   "ACTION4 causes the block to move right" (low-level dynamics)
LLM reasons:  "I need to reach the top-right, so I should go UP then RIGHT" (goal)
CNN predicts: "If I go UP, the grid will look like THIS" (simulator!)
LLM plans:    "Given CNN's predictions, the optimal path is..." (search)
```

```
CNN 학습:    "ACTION4는 블록을 오른쪽으로 이동시킨다" (저수준 역학)
LLM 추론:   "오른쪽 위에 도달해야 하니까, UP 후 RIGHT" (목표)
CNN 예측:    "UP 하면 그리드가 이렇게 될 것이다" (시뮬레이터!)
LLM 계획:   "CNN의 예측을 기반으로 최적 경로는..." (탐색)
```

**Advantage**: CNN can learn the simulator implicitly from frame data, without explicit rule extraction. Handles continuous/complex dynamics that are hard to code.

**장점**: CNN이 명시적 규칙 추출 없이 프레임 데이터에서 시뮬레이터를 암묵적으로 학습. 코드로 짜기 어려운 연속적/복잡한 역학을 처리.

**Disadvantage**: Needs many frames to train (action budget!), CNN predictions may be noisy, can't explain its model.

**단점**: 학습에 많은 프레임 필요 (액션 예산!), CNN 예측이 불안정할 수 있음, 모델 설명 불가.

**Kaggle feasibility**: Yes — CNN runs locally, no API needed. This is the most Kaggle-viable approach.

**Kaggle 적용성**: 가능 — CNN은 로컬 실행, API 불필요. Kaggle에 가장 적합한 접근법.

---

### 5b. LLM-as-Simulator (No Explicit Code)
### 5b. LLM을 시뮬레이터로 사용 (명시적 코드 없이)

**Core idea**: Instead of writing simulator code, use the LLM itself to predict next states.

**핵심 아이디어**: 시뮬레이터 코드를 작성하는 대신, LLM 자체를 다음 상태 예측에 사용.

```python
def llm_simulate(state_description, action):
    response = claude.ask(f"""
        Given this game state: {state_description}
        And the rules I've observed:
        - Agent moves in 3-cell jumps on the graph
        - Enemy mirrors movement when on same row and close

        If I take {action}, what will the new state be?
        Predict: new agent position, new enemy position, alive/dead
    """)
    return parse_prediction(response)

# Use LLM predictions for BFS
for action in possible_actions:
    predicted_state = llm_simulate(current_state, action)  # LLM call, not game call
    if predicted_state.alive:
        queue.append(predicted_state)
```

**Advantage**: No code to write/debug. LLM can handle fuzzy, hard-to-formalize rules. Can leverage chain-of-thought for complex dynamics.

**장점**: 작성/디버깅할 코드 없음. LLM이 형식화하기 어려운 모호한 규칙을 처리. 복잡한 역학에 chain-of-thought 활용 가능.

**Disadvantage**: Slow (API call per simulation step), expensive ($), LLM predictions may be inconsistent, can't do 10,000 rollouts.

**단점**: 느림 (시뮬레이션 스텝당 API 호출), 비용 ($), LLM 예측이 일관되지 않을 수 있음, 10,000번 롤아웃 불가.

**Best for**: Quick prototyping, games where rules are too complex to code but can be described in natural language.

**적합한 경우**: 빠른 프로토타이핑, 규칙이 코드로 짜기엔 복잡하지만 자연어로 설명 가능한 게임.

---

### 5c. Action-Replay with State Checkpointing
### 5c. 상태 체크포인팅을 이용한 액션 리플레이

**Core idea**: Improve CLI BFS by saving/restoring game state instead of replaying from scratch.

**핵심 아이디어**: 게임 상태를 저장/복원하여 CLI BFS를 개선, 처음부터 리플레이하지 않음.

```python
# Instead of:
env = arc.make('tu93')
for a in all_47_previous_actions:   # replay EVERY time
    env.step(a)
env.step(new_action)                # test 1 new action

# Do this:
checkpoint = save_state(env)        # save after level 2
for action in candidates:
    restore_state(env, checkpoint)  # instant restore
    env.step(action)                # test 1 new action
```

**Advantage**: Keeps the "perfect accuracy" of using the real game, but eliminates replay overhead. O(1) per node instead of O(N).

**장점**: 실제 게임 사용의 "완벽한 정확도"를 유지하면서 리플레이 오버헤드 제거. O(N) 대신 O(1)/노드.

**Disadvantage**: Requires game engine to support state serialization (may not be available). Depends on `deepcopy` or `pickle` of game internals.

**단점**: 게임 엔진이 상태 직렬화를 지원해야 함 (불가능할 수 있음). 게임 내부의 `deepcopy` 또는 `pickle`에 의존.

**Feasibility**: The `arc_agi` local engine loads game classes from Python files. If we can `deepcopy(env)`, this becomes the easiest high-performance approach.

**실현 가능성**: `arc_agi` 로컬 엔진은 Python 파일에서 게임 클래스를 로드. `deepcopy(env)`가 가능하면 가장 쉬운 고성능 접근법이 됨.

---

### 5d. Program Synthesis / Symbolic Regression
### 5d. 프로그램 합성 / 기호 회귀

**Core idea**: Automatically generate simulator code from input-output observations using program synthesis techniques.

**핵심 아이디어**: 입출력 관찰에서 프로그램 합성 기법으로 시뮬레이터 코드를 자동 생성.

```
Observations:
    (agent=A, enemy=E, action=RIGHT) → (agent=A+6, enemy=E, alive)
    (agent=A, enemy=E, action=RIGHT) → (agent=A+6, enemy=E, alive)
    (agent=A, enemy=E, action=RIGHT) → (agent=A+6, enemy=E-6, DEAD)

Synthesized program:
    def next_state(agent, enemy, action):
        new_agent = agent + delta[action]
        if abs(new_agent - enemy) <= threshold:
            new_enemy = enemy - delta[action]
        else:
            new_enemy = enemy
        collision = (new_agent == new_enemy)
        return new_agent, new_enemy, not collision
```

**Advantage**: Principled, can find rules that LLMs might miss. Guarantees consistency with observations.

**장점**: 원칙적, LLM이 놓칠 수 있는 규칙 발견 가능. 관찰과의 일관성 보장.

**Disadvantage**: Computationally expensive, limited to simple dynamics, requires careful feature engineering.

**단점**: 계산 비용 높음, 단순한 역학으로 제한, 신중한 특성 엔지니어링 필요.

---

### 5e. Model-Free RL with UNDO
### 5e. 모델-프리 RL + UNDO 활용

**Core idea**: Some games offer ACTION7 (UNDO). Use it to explore freely, then commit to the best path.

**핵심 아이디어**: 일부 게임은 ACTION7 (UNDO)를 제공. 이를 활용해 자유롭게 탐색한 후 최적 경로에 전념.

```
Explore:   RIGHT → observe → UNDO → LEFT → observe → UNDO → UP → observe → UNDO
Decide:    RIGHT was best
Execute:   RIGHT (for real this time, no UNDO)
```

**Advantage**: Free exploration within the real game! UNDO acts as a "free simulator."

**장점**: 실제 게임 안에서 무료 탐색! UNDO가 "무료 시뮬레이터" 역할.

**Disadvantage**: Not all games have UNDO. UNDO might not be perfect (some state may persist). Uses 2 actions per exploration step (action + undo).

**단점**: 모든 게임에 UNDO가 없음. UNDO가 완벽하지 않을 수 있음 (일부 상태가 유지). 탐색 스텝당 2 액션 사용 (액션 + 취소).

**Note**: tu93 only had ACTION1-4 (no UNDO available).

**참고**: tu93는 ACTION1-4만 사용 가능 (UNDO 없음).

---

## 6. Recommended Strategy for ARC-AGI-3
## 6. ARC-AGI-3를 위한 권장 전략

### For Local Development (Claude API available) / 로컬 개발 (Claude API 사용 가능)

```
Priority 1: Try state checkpointing (5c)
    → deepcopy(env) works? Use game-oracle BFS without replay overhead
    → deepcopy 가능? 리플레이 오버헤드 없이 게임 오라클 BFS

Priority 2: Simulator-building loop (Section 2) with probabilistic model (Section 3.5)
    → LLM writes simulator code with confidence-weighted mechanics
    → LLM이 신뢰도 가중 메카닉으로 시뮬레이터 코드 작성

Priority 3: LLM-as-simulator (5b)
    → Use Claude to predict states, do shallow search
    → Claude로 상태 예측, 얕은 탐색 수행

Fallback: Harness LLM with knowledge accumulation
    → Current approach, enhanced with better prompting
    → 현재 접근법, 개선된 프롬프팅으로 강화
```

### For Kaggle Submission (No internet) / Kaggle 제출 (인터넷 없음)

**The Kaggle environment has NO internet.** This means no Claude API, no GPT, no external services. Everything must run locally on Kaggle's GPU. This fundamentally changes the approach: **an SLM (Small Language Model) must do everything the frontier LLM does during local development** — including writing simulator code.

**Kaggle 환경에는 인터넷이 없다.** Claude API, GPT, 외부 서비스 모두 불가. 모든 것이 Kaggle GPU에서 로컬로 실행되어야 한다. 이것이 접근법을 근본적으로 바꾼다: **SLM(소형 언어 모델)이 로컬 개발에서 프론티어 LLM이 하는 모든 것을 해야 한다** — 시뮬레이터 코드 작성 포함.

```
Priority 1: SLM-driven simulator-building (★ PRIMARY STRATEGY)
    → Qwen 3.5 7B (or similar) observes frames, writes simulator code,
      plans against it, refines on failure
    → SLM이 프레임을 관찰하고, 시뮬레이터 코드를 작성하고,
      이를 기반으로 계획하고, 실패 시 수정

Priority 2: Hybrid CNN + SLM
    → CNN learns low-level dynamics (frame prediction)
    → SLM handles high-level planning and goal inference
    → CNN이 저수준 역학 학습 (프레임 예측)
    → SLM이 고수준 계획 및 목표 추론

Priority 3: Pure CNN (StochasticGoose-style)
    → Proven baseline at 12.58%, no LM needed
    → 12.58% 검증된 기준, LM 불필요
```

### What "SLM Writes Simulator" Means Concretely
### "SLM이 시뮬레이터를 짠다"의 구체적 의미

This is the critical capability gap we must close for Kaggle. The SLM must:

이것이 Kaggle을 위해 우리가 메워야 할 핵심 능력 격차다. SLM이 해야 할 것:

```
Step 1: Observe a few frames and diffs
        몇 개 프레임과 diff를 관찰

Step 2: Identify entities (agent, walls, enemies, goals) from pixel patterns
        픽셀 패턴에서 엔티티 식별 (에이전트, 벽, 적, 목표)

Step 3: Hypothesize mechanics as Python functions
        메카닉을 Python 함수로 가설화

        def predict_next(state, action):
            agent_new = move(state.agent, action, state.walls)
            enemy_new = maybe_mirror(state.enemy, action)  # confidence: 0.6
            ...

Step 4: Run BFS/MCTS on the generated simulator
        생성된 시뮬레이터에서 BFS/MCTS 실행

Step 5: Execute plan, observe discrepancy, fix simulator
        계획 실행, 불일치 관찰, 시뮬레이터 수정
```

### Training the SLM for Simulator Writing
### 시뮬레이터 작성을 위한 SLM 훈련

**This is a capability we must actively develop**, not assume. Strategies:

**이것은 우리가 적극적으로 개발해야 하는 능력**이지, 가정할 수 있는 것이 아니다. 전략:

```
1. Distillation from Claude sessions:
   Claude가 tu93 등을 풀면서 생성한 시뮬레이터 코드를
   (observation, simulator_code) 쌍으로 SFT 데이터 구축

2. Synthetic training data:
   공개 25개 게임에 대해 Claude로 시뮬레이터를 짜고,
   이 데이터로 Qwen을 파인튜닝

3. Scaffolded generation:
   SLM이 전체 시뮬레이터를 한번에 짜는 대신,
   템플릿 + 빈칸 채우기 방식으로 난이도를 낮춤:

   TEMPLATE:
   def predict(state, action):
       agent_new = ___  # SLM fills: move_on_graph(state.agent, action)
       enemy_new = ___  # SLM fills: mirror_if_adjacent(state.enemy, action)
       alive = ___      # SLM fills: agent_new != enemy_new
       return State(agent_new, enemy_new), alive

4. Progressive complexity:
   Level 0 시뮬레이터 → Level 1에 적 추가 → Level 2에 새 메카닉 추가
   레벨이 올라가면서 시뮬레이터도 점진적으로 복잡해짐
```

### The SLM Capability Ladder / SLM 능력 사다리

```
Level 1 (minimum): Grid parsing + entity detection
    → "I see a 3x3 block of 9s with a 4 — that's the agent"
    → SLM이 그리드를 파싱하고 엔티티를 식별

Level 2 (basic): Action→effect mapping
    → "ACTION4 moves the agent right by 6 pixels"
    → SLM이 액션과 효과를 매핑

Level 3 (intermediate): Write simple simulator functions
    → "def move(agent, action): return agent + delta[action]"
    → SLM이 간단한 시뮬레이터 함수를 작성

Level 4 (advanced): Multi-entity interaction modeling
    → "enemy mirrors when adjacent AND on same row"
    → SLM이 다중 엔티티 상호작용을 모델링

Level 5 (expert): Probabilistic reasoning + self-correction
    → "my prediction was wrong → the trigger condition must be different"
    → SLM이 예측 실패를 인식하고 스스로 수정
```

**Current state**: Frontier LLMs (Claude, GPT) are at Level 4-5. Qwen 3.5 7B is likely at Level 2-3. **The gap between Level 3 and Level 5 is where the competition will be won or lost.**

**현재 상태**: 프론티어 LLM (Claude, GPT)은 Level 4-5. Qwen 3.5 7B는 아마 Level 2-3. **Level 3과 Level 5 사이의 격차가 대회의 승부처.**

---

## 7. Open Questions
## 7. 남은 질문들

1. **Can we `deepcopy` the arc_agi game environment?** If yes, this is a game-changer — perfect accuracy with O(1) per BFS node.

   **arc_agi 게임 환경을 `deepcopy`할 수 있는가?** 가능하면 게임 체인저 — BFS 노드당 O(1)에 완벽한 정확도.

2. **How many exploration actions does simulator-building need per game?** If 5% of human baseline suffices, it's viable. If 50%, it's not worth it.

   **시뮬레이터 구축에 게임당 탐색 액션이 몇 개 필요한가?** 인간 기준의 5%면 실행 가능. 50%면 가치 없음.

3. **Can LLMs accurately predict grid states?** If LLM-as-simulator (5b) works at 90%+ accuracy, it might be simpler than code generation.

   **LLM이 그리드 상태를 정확히 예측할 수 있는가?** LLM-as-simulator(5b)가 90%+ 정확도면 코드 생성보다 단순할 수 있음.

4. **Do game mechanics carry across levels?** If yes, the simulator built for level 1 works for level 5. If mechanics change, the simulator must be rebuilt per level.

   **게임 메카닉이 레벨 간에 유지되는가?** 유지되면 level 1 시뮬레이터가 level 5에서도 작동. 변경되면 레벨마다 재구축 필요.

5. **What's the minimum viable simulator?** Maybe we don't need to model everything — just the parts that affect the agent's path. Partial simulators might suffice.

   **최소한의 실행 가능한 시뮬레이터는?** 모든 것을 모델링할 필요 없을 수 있음 — 에이전트 경로에 영향을 미치는 부분만. 부분 시뮬레이터로 충분할 수 있음.

---

## References
- Companion doc: [search-strategies-comparison.md](search-strategies-comparison.md)
- CLAUDE.md: "관찰→코드화→예측→검증" loop
- StochasticGoose: CNN baseline (12.58%)
- tu93 session: empirical evidence for all claims in this document
