# Search Strategies for ARC-AGI-3: A Detailed Comparison
# ARC-AGI-3를 위한 탐색 전략: 상세 비교

> Written from hands-on experience solving tu93 (maze + enemy avoidance) in Claude Code CLI session (2026-04-01).
> tu93 (미로 + 적 회피) 게임을 Claude Code CLI에서 직접 풀어본 경험을 바탕으로 작성.

---

## Background: Why Search Matters in ARC-AGI-3
## 배경: 왜 탐색이 중요한가

ARC-AGI-3 games are **interactive reasoning puzzles** where:
- The agent is **never told the rules or goals**
- Each action is **irreversibly consumed** (affects RHAE score)
- Games have **hidden mechanics** (enemies, physics, state transitions)
- Optimal play requires **look-ahead planning**

ARC-AGI-3 게임은 **상호작용 추론 퍼즐**이다:
- 에이전트에게 **규칙이나 목표를 알려주지 않음**
- 매 액션이 **비가역적으로 소비됨** (RHAE 점수에 영향)
- 게임에 **숨겨진 메카닉**이 있음 (적, 물리법칙, 상태 전이)
- 최적 플레이에는 **미래를 내다보는 계획**이 필수

The central challenge: **how do you plan ahead when you don't know the rules?**

핵심 도전: **규칙을 모르는데 어떻게 미래를 계획하는가?**

---

## The Three Approaches We Tested
## 우리가 테스트한 세 가지 접근법

### 1. MCTS (Monte Carlo Tree Search)
### 1. MCTS (몬테카를로 트리 탐색)

#### How It Works / 작동 원리

MCTS requires a **simulator** — a function `simulate(state, action) → next_state` that runs entirely in memory, without touching the real game.

MCTS는 **시뮬레이터**가 필요하다 — 실제 게임을 건드리지 않고 메모리 안에서 `simulate(state, action) → next_state`를 계산하는 함수.

```
Current state S₀:

    S₀ ─── ACTION1 ──→ S₁ (simulator computes instantly)
     │                   ├── ACTION1 → S₄ → ... → win?  score: 0.7
     │                   ├── ACTION2 → S₅ → ... → lose? score: 0.1
     │                   └── ACTION4 → S₆ → ... → win?  score: 0.9 ★
     │
     ├── ACTION2 ──→ S₂ (simulator computes instantly)
     │                   └── best score: 0.3
     │
     └── ACTION4 ──→ S₃ (simulator computes instantly)
                         └── best score: 0.5

→ Choose ACTION1 (subtree best = 0.9)
→ Send ACTION1 to real game (only 1 action consumed)
```

#### Cost Structure / 비용 구조

```
Exploration:  10,000 simulated rollouts     → cost: 0 real actions
Planning:     Select best path              → cost: 0 real actions
Execution:    Play the optimal path         → cost: N real actions (minimal)
────────────────────────────────────────────────────────────────────
Total:        N actions (near-optimal)
```

```
탐색:    10,000번 시뮬레이션            → 비용: 실제 액션 0
계획:    최적 경로 선택                 → 비용: 실제 액션 0
실행:    최적 경로 플레이               → 비용: 실제 액션 N (최소)
────────────────────────────────────────────────────────────────────
합계:    N 액션 (거의 최적)
```

#### Strengths / 강점

- **Zero-cost exploration**: Can test 10,000 paths without spending a single real action
- **Optimal planning**: With enough rollouts, finds the best or near-best path
- **Handles adversaries**: Can model enemy behavior and plan around it
- **Depth**: Can look 20+ moves ahead

- **탐색 비용 0**: 실제 액션 하나 안 쓰고 10,000개 경로 테스트 가능
- **최적 계획**: 충분한 롤아웃으로 최적 또는 준최적 경로를 찾음
- **적 대응**: 적의 행동을 모델링하고 우회 가능
- **깊이**: 20수 이상 내다보기 가능

#### Weaknesses / 약점

- **Requires accurate simulator**: If the simulator's rules are wrong, the plan is wrong
- **Can't build itself**: Someone (or something) must first discover the rules and code the simulator
- **Brittle to rule changes**: If mechanics change between levels, the simulator breaks

- **정확한 시뮬레이터 필요**: 시뮬레이터 규칙이 틀리면 계획이 틀림
- **스스로 만들어지지 않음**: 누군가(또는 무언가)가 먼저 규칙을 발견하고 코드를 짜야 함
- **규칙 변경에 취약**: 레벨 간 메카닉이 바뀌면 시뮬레이터가 깨짐

#### ARC-AGI-3 Feasibility / ARC-AGI-3 적용 가능성

**Not directly usable** — we don't have a simulator for unseen games. But it becomes the endgame once a simulator is built (see Section 3).

**직접 사용 불가** — 처음 보는 게임의 시뮬레이터가 없음. 하지만 시뮬레이터가 만들어지면 최종 단계로 사용 (3장 참조).

---

### 2. Harness LLM Agent (Current Approach)
### 2. Harness LLM Agent (현재 방식)

#### How It Works / 작동 원리

Each turn, the agent sends the current frame to an LLM and asks "what should I do?"

매 턴마다, 에이전트가 현재 프레임을 LLM에 보내고 "뭘 해야 해?"라고 묻는다.

```python
def choose_action(self, frames, latest_frame):
    grid_text = format_grid(latest_frame)
    diff_text = compute_diff(frames[-2], frames[-1])

    response = claude.ask(f"""
        Current grid: {grid_text}
        Previous diff: {diff_text}
        Action history: {self.history}
        Discovered rules: {self.knowledge}
        → What action next?
    """)

    return parse_action(response)
```

```
Turn 1:  LLM sees grid → "There's a block, let me try RIGHT"  → ACTION4
Turn 2:  LLM sees diff → "Block moved. Enemy didn't. Continue" → ACTION4
Turn 3:  LLM sees diff → "Still fine, keep going"              → ACTION4
Turn 4:  GAME_OVER!    → "Enemy rushed me when I got close!"   → (learns)
Turn 5:  After RESET   → "This time, go around via row 34"     → ACTION2
```

#### Cost Structure / 비용 구조

```
Exploration:  Every test IS a real action    → cost: M real actions
Planning:     LLM reasons in-context         → cost: 0 actions, but imperfect
Execution:    Already spent during explore   → cost: 0 additional
────────────────────────────────────────────────────────────────────
Total:        M actions (M >> optimal N, often M = 3~10x N)
```

```
탐색:    모든 테스트가 실제 액션          → 비용: 실제 액션 M
계획:    LLM이 컨텍스트 내에서 추론       → 비용: 0 액션, 하지만 불완전
실행:    탐색 중 이미 소비됨              → 비용: 추가 0
────────────────────────────────────────────────────────────────────
합계:    M 액션 (M >> 최적 N, 보통 M = N의 3~10배)
```

#### The Fundamental Problem / 근본적 문제

**Exploration and execution are not separated.**

**탐색과 실행이 분리되지 않는다.**

```
MCTS:     "What if I go RIGHT?" → simulate → no cost
          → bad result? try LEFT instead → no cost
          → found good path? NOW execute for real

Harness:  "What if I go RIGHT?" → send to real game → 1 action consumed
          → bad result? can't undo. GAME_OVER or wasted action.
          → must RESET and replay everything
```

```
MCTS:     "RIGHT 가면?" → 시뮬레이션 → 비용 없음
          → 결과 나쁘면? LEFT 해봄 → 비용 없음
          → 좋은 경로 찾으면? 그때 실제로 실행

Harness:  "RIGHT 가면?" → 실제 게임에 보냄 → 1 액션 소비
          → 결과 나쁘면? 되돌릴 수 없음. GAME_OVER 또는 낭비.
          → RESET 하고 처음부터 다시 해야 함
```

#### Strengths / 강점

- **No prerequisites**: Works on any game immediately, no simulator needed
- **Adaptive**: LLM can reason about novel situations
- **Cross-level transfer**: Knowledge accumulated in context carries forward
- **Simple architecture**: Just an LLM + prompt, easy to iterate

- **전제 조건 없음**: 시뮬레이터 없이 어떤 게임이든 즉시 작동
- **적응적**: LLM이 새로운 상황에 대해 추론 가능
- **레벨 간 전이**: 컨텍스트에 축적된 지식이 이월됨
- **단순한 구조**: LLM + 프롬프트만 있으면 됨

#### Weaknesses / 약점

- **No look-ahead**: Cannot test "what if" without spending real actions
- **Expensive exploration**: Every hypothesis test costs a real action
- **Greedy**: Effectively 1-step reasoning (or shallow multi-step via LLM chain-of-thought)
- **RHAE punishment**: Score = (human/agent)². 2x human actions → 25% score, 10x → 1%

- **미래 예측 불가**: 실제 액션을 쓰지 않고는 "만약에..."를 테스트할 수 없음
- **탐색 비용 높음**: 모든 가설 테스트가 실제 액션 소비
- **탐욕적**: 사실상 1스텝 추론 (또는 LLM chain-of-thought으로 얕은 다단계)
- **RHAE 패널티**: 점수 = (인간/에이전트)². 인간의 2배 → 25% 점수, 10배 → 1%

---

### 3. CLI BFS with Game Oracle (What We Did)
### 3. 게임 오라클을 이용한 CLI BFS (우리가 한 것)

#### How It Works / 작동 원리

Use the **actual game engine** as a black-box oracle, but replay from scratch for each candidate path. This gives exact results (no simulation error) but at enormous computational cost.

**실제 게임 엔진**을 블랙박스 오라클로 사용하되, 매 후보 경로마다 처음부터 리플레이한다. 정확한 결과를 주지만(시뮬레이션 오류 없음) 계산 비용이 막대하다.

```python
def test_path(prefix_actions, new_actions):
    env = arc.make('tu93')                    # Fresh game every time
    for a in prefix_actions:                   # Replay ALL previous levels
        env.step(GameAction.from_name(a))      # (18 + 10 + 19 = 47 steps for level 3)
    for a in new_actions:                      # Then test the new candidate
        result = env.step(GameAction.from_name(a))
    return result.state, find_agent(env), find_enemy(env)

# BFS: try every possible action sequence
queue = [([], initial_state)]
while queue:
    path, state = queue.popleft()
    for action in [ACTION1, ACTION2, ACTION3, ACTION4]:
        new_state = test_path(all_previous_actions, path + [action])  # FULL REPLAY
        if new_state == WIN:
            return path + [action]
        if new_state != GAME_OVER:
            queue.append((path + [action], new_state))
```

#### Cost Structure / 비용 구조

```
Per BFS node at level L:
    Replay cost:    sum of all actions from level 0 to L-1
    + Test cost:    1 new action
    = Total:        O(cumulative_actions) per node

Level 0:  replay 0  + test = ~1   step/node  × ~100 nodes  = ~100 engine calls
Level 1:  replay 18 + test = ~19  steps/node × ~60 nodes   = ~1,140 engine calls
Level 2:  replay 28 + test = ~29  steps/node × ~200 nodes  = ~5,800 engine calls
Level 3:  replay 47 + test = ~48  steps/node × ~1000 nodes = ~48,000 engine calls
                                                              ↑ TIMEOUT
```

```
레벨 L에서 BFS 노드 하나당:
    리플레이 비용:  level 0부터 L-1까지 모든 액션의 합
    + 테스트 비용:  새 액션 1개
    = 합계:         O(누적 액션 수) / 노드

Level 0:  리플레이 0  + 테스트 = ~1   스텝/노드  × ~100 노드  = ~100 엔진 호출
Level 1:  리플레이 18 + 테스트 = ~19  스텝/노드 × ~60 노드   = ~1,140 엔진 호출
Level 2:  리플레이 28 + 테스트 = ~29  스텝/노드 × ~200 노드  = ~5,800 엔진 호출
Level 3:  리플레이 47 + 테스트 = ~48  스텝/노드 × ~1000 노드 = ~48,000 엔진 호출
                                                              ↑ 시간 초과!
```

This is **exactly why level 3 failed**. The replay overhead grows with every solved level.

이것이 **정확히 level 3이 실패한 이유**다. 리플레이 오버헤드가 해결된 레벨마다 누적됨.

#### Strengths / 강점

- **Perfect accuracy**: Uses the real game engine, no simulation errors
- **Guaranteed optimal**: BFS finds shortest path (within depth limit)
- **No rule discovery needed**: The game IS the oracle

- **완벽한 정확도**: 실제 게임 엔진 사용, 시뮬레이션 오류 없음
- **최적 보장**: BFS가 최단 경로를 찾음 (깊이 제한 내)
- **규칙 발견 불필요**: 게임 자체가 오라클

#### Weaknesses / 약점

- **O(N²) replay overhead**: Each node replays all previous actions
- **Doesn't scale**: Fails at depth ~25 or level 3+ due to time
- **No state persistence**: Can't fork/clone game state, must replay from scratch
- **Offline only**: Requires local game engine (not applicable for online/API games)

- **O(N²) 리플레이 오버헤드**: 매 노드가 이전 액션을 전부 리플레이
- **확장 불가**: 깊이 ~25 또는 level 3+에서 시간 초과
- **상태 유지 불가**: 게임 상태를 복제할 수 없어 매번 처음부터 리플레이
- **오프라인 전용**: 로컬 게임 엔진 필요 (온라인/API 게임에 적용 불가)

---

## Side-by-Side Comparison
## 종합 비교

```
                    MCTS             CLI BFS Oracle      Harness LLM
                    ─────────────    ─────────────────   ─────────────────
Prerequisite        Accurate         Local game engine   None
전제 조건           시뮬레이터       로컬 게임 엔진      없음

Explore cost        0 (simulated)    O(N²) replays       Every test = real
탐색 비용           0 (시뮬)         O(N²) 리플레이      매 테스트 = 실제

Plan quality        Optimal          Optimal (in depth)  Heuristic/greedy
계획 품질           최적             최적 (깊이 내)      휴리스틱/탐욕

Look-ahead          Deep (20+)       Deep but slow       None (1-step)
선읽기              깊음 (20+)       깊지만 느림         없음 (1스텝)

Adaptability        Brittle          Perfect accuracy    Highly adaptive
적응성              깨지기 쉬움       완벽한 정확도       매우 적응적

Scales to L3+       Yes              No (timeout)        Yes (but wasteful)
Level 3+ 확장       가능             불가 (시간 초과)    가능 (하지만 낭비)

Enemy handling      Perfect model    Perfect (oracle)    "Probably moves left"
적 대응             완벽한 모델      완벽 (오라클)       "아마 왼쪽으로 갈 듯"

Real actions used   N (optimal)      N (optimal found)   3~10× N
실제 액션 사용량     N (최적)         N (최적 발견)       3~10× N
```

---

## Concrete Example: tu93 Level 1 Enemy Problem
## 구체적 사례: tu93 Level 1 적 문제

The maze has an enemy (8/f block) blocking the only horizontal path. The agent must navigate around it without collision.

미로에 유일한 수평 경로를 막고 있는 적(8/f 블록)이 있다. 에이전트는 충돌 없이 우회해야 한다.

```
. . . . . . . . . . . . G .   (goal at top-right)
. . . . . . . . . . . . | .
O - O - O - O - X - O - O .   (X = enemy on main path)
|       .   |   |   |          (| and - are connections)
A . . . O - O - O . . . . .   (A = agent at bottom-left)
```

### How Each Approach Handles This / 각 접근법의 처리 방식

**MCTS approach / MCTS 접근:**
```
simulate(agent=A, enemy=X, action=RIGHT):
    → agent moves to next node, enemy moves opposite
    → check collision → safe
simulate(agent=new_pos, enemy=new_pos, action=RIGHT):
    → collision detected!
    → backtrack, try different path (DOWN first, then RIGHT)
→ Finds path in ~100 simulations, 0 real actions
```

**CLI BFS approach / CLI BFS 접근:**
```
replay(level0_18_actions + [UP, RIGHT, RIGHT]):
    → game engine says: agent=(28,26), enemy=(28,36), alive
replay(level0_18_actions + [UP, RIGHT, RIGHT, RIGHT]):
    → game engine says: GAME_OVER (collision!)
replay(level0_18_actions + [UP, RIGHT, RIGHT, DOWN, RIGHT, RIGHT, UP, RIGHT, RIGHT, UP]):
    → game engine says: level advanced! (10 actions)
→ Finds path after ~60 replays, each replaying 18+ actions = ~1,140 engine steps
```

**Harness LLM approach / Harness LLM 접근:**
```
Turn 1: "I see a maze. Let me go UP then RIGHT."     → UP    (1 action spent)
Turn 2: "Moved to main path. Continue RIGHT."         → RIGHT (1 action spent)
Turn 3: "Progressing. Keep going."                     → RIGHT (1 action spent)
Turn 4: "Keep going."                                  → RIGHT → GAME_OVER!
                                                         (4 actions wasted)
Turn 5: RESET → replays 18 level-0 actions             (18 actions spent)
Turn 6: "Enemy killed me. I need to go around..."      → tries different path
Turn 7-15: Trial and error...                          (more actions spent)
→ Eventually finds path, but spent 30~50 total actions vs optimal 10
```

---

## Key Insight
## 핵심 통찰

The fundamental tradeoff is:

근본적인 트레이드오프는:

```
Accuracy of world model  ←→  Cost of planning
세계 모델의 정확도        ←→  계획 비용

Perfect simulator  → free planning, but hard to build
완벽한 시뮬레이터  → 계획은 공짜, 하지만 만들기 어려움

No simulator       → planning costs real actions
시뮬레이터 없음     → 계획에 실제 액션 소비

Imperfect simulator → cheap planning, occasionally wrong
불완전한 시뮬레이터 → 저렴한 계획, 가끔 틀림  ★ sweet spot
```

This leads us to the **simulator-building approach** described in the companion document.

이것이 동반 문서에서 설명하는 **시뮬레이터 구축 접근법**으로 이어진다.

---

## References
- tu93 game session: claude-code-dialogue-tu93-apr1-noharness
- CLAUDE.md: "관찰→코드화→예측→검증" loop
- StochasticGoose: CNN approach without any planning (12.58% score)
- RHAE formula: `level_score = min(1.0, human_baseline / ai_actions)²`
