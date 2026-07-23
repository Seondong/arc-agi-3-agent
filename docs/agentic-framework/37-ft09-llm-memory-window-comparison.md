<!-- [Mar 31] Created by SD with GPT-5.4. -->
# ft09 LLM Memory Window Comparison

이 문서는 `ft09`를 대상으로 `LLMBrain`의 rolling memory window를 실제 OpenAI 호출로 비교한 결과를 Claude에게 전달하기 위한 짧은 handoff 메모다. 목적은 단순하다. 최근에 `llm_brain.py`에 compact rolling memory가 들어갔고, 이 memory를 몇 step까지 유지하는 것이 적절한지에 대한 첫 번째 empirical check가 필요했다.

이번 비교는 다음 세 조건으로 진행했다.

- `window=0`
- `window=4`
- `window=8`

모델은 모두 `gpt-5.4-mini`, 게임은 `ft09`, step budget은 `16`으로 고정했다. 실행 artifact는 아래에 있다.

- [`window0 episode`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/ft09_llm_compare/window0/ft09-0d8bbf25-3360f354)
- [`window4 episode`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/ft09_llm_compare/window4/ft09-0d8bbf25-b19c5348)
- [`window8 episode`](/Users/sundong/Documents/arc-agi-3/code/ARC-AGI-3-Agents/artifacts/ft09_llm_compare/window8/ft09-0d8bbf25-5babcc7c)

실험 전에 `llm_memory_window`를 실제 실험 단위로 다룰 수 있도록 solver/wrapper/supervisor/queue signature seam도 같이 닫아 두었다. 즉 이제는 동일한 `llm_model`이라도 `memory_window`가 다르면 다른 solve-loop job으로 구분된다.

## 결과 요약

세 조건 모두 `levels_completed = 0`, `steps = 16`, `final_state = NOT_FINISHED`였다. 즉 이번 `ft09` 비교에서는 memory window를 늘리는 것만으로는 solve outcome이 좋아지지 않았다.

행동 패턴도 사실상 동일했다.

- 세 조건 모두 `ACTION6`만 선택
- nonzero diff `0/16`
- phase 분포 동일: `epistemic 11`, `instrumental 3`, `recovery 2`

즉 실제 행동 정책 차원에서는 `window=0`, `window=4`, `window=8`이 거의 같은 solver trajectory를 만들어냈다.

## 정성적 차이

정성적으로는 `window=4`, `window=8` 쪽 reasoning이 조금 더 자연스럽게 “이전에 무엇을 시도했고 무엇을 배웠는지”를 이어 말한다. 예를 들어 step 5, 8, 12에서 `window=0`은 “previous probe at (10,14) produced no change” 정도의 참조를 하는 반면, `window=4`와 `window=8`은 “first control candidate was inert”, “remaining untested 0-valued control”, “last plausible visible trigger” 같은 식으로 조금 더 압축된 진행 감각을 보인다.

하지만 이 정성 개선이 행동 변화로 이어지진 않았다. 결국 세 조건 모두 같은 `ACTION6` 반복에 머물렀고, 어떤 state change도 만들지 못했다.

## Prompt budget 해석

같은 `ft09` fresh episode artifact를 사용해 오프라인으로 `LLMBrain._build_prompt(...)`를 재조립하여 memory window별 prompt growth도 계산했다. 이 값은 실제 API accounting이 아니라 prompt text 길이 기반의 근사치다.

- `window 0`: 평균 `1874` chars, 약 `469` tokens
- `window 4`: 평균 `2614` chars, 약 `654` tokens
- `window 8`: 평균 `3105` chars, 약 `776` tokens
- `window 12`: 평균 `3394` chars, 약 `849` tokens

즉 현재 compact memory 구현은 raw full-history accumulation보다 훨씬 싸다. `window=8`까지는 충분히 감당 가능해 보인다. 다만 이번 `ft09`에서는 비용이 감당 가능하다는 사실과 solve quality 개선은 별개였다.

## 해석

이번 결과는 “memory length가 중요하지 않다”는 뜻은 아니다. 오히려 `ft09`가 memory의 어떤 내용이 중요한지를 보여준다.

`ft09`는 사실상 `ACTION6` 하나만 있는 click-semantics 게임이다. 이런 게임에서는 단순히 최근 reasoning 문장을 더 오래 들고 가는 것보다, 아래 같은 구조화된 click history가 더 중요하다.

- 이미 눌러본 좌표 목록
- 눌러봤지만 no-op이었던 `target_pid` / `target_region`
- reference pattern과 연결된 click candidate의 우선순위 변화
- “visible ○ candidates are all inert” 같은 명시적 avoid list

현재 `RollingMemoryEntry`는 `action / why / surprise / learned / unresolved`를 저장한다. 이 구조는 movement 게임이나 일반 탐색 게임엔 도움이 될 수 있지만, `ft09`처럼 “어느 좌표를 눌렀는가” 자체가 핵심인 게임에선 충분히 직접적이지 않다.

즉 이번 비교는 memory를 더 길게 가져가는 것 자체보다, memory의 내용이 click-specific하게 더 구조화되어야 한다는 쪽을 지지한다.

## 추천

현재 기준 추천은 이렇다.

1. 기본값은 `window=4` 유지
2. 분석용/추가 실험용으로는 `window=8` 허용
3. `window=12+`는 지금 단계에선 우선순위 낮음
4. 다음 개선은 length가 아니라 content

가장 유망한 다음 티켓은 다음과 같다.

- `RollingMemoryEntry`에 `clicked_coordinate` 추가
- `target_pid` 또는 `target_region` 추가
- `failed_targets` 또는 `avoid_candidates` 요약 추가
- `reference_pattern`과 연결된 unresolved question을 명시적으로 넣기

한 줄로 정리하면, `ft09`에서는 “더 긴 memory”가 아니라 “더 구조화된 click memory”가 맞는 다음 단계다.
