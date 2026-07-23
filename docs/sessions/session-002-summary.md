<!-- [Mar 29] Created by SD with Claude Opus 4.6. -->
# Session 002: Phase 2 구현 + 로컬 LLM 테스트

## 이번 세션 타임라인

### 1. Phase 2 인프라 구축 (완료)
5개 새 파일 생성하여 자동화 에이전트 시스템 구축:

```
agents/
  grid_lib.py         — 공통 그리드 분석 (map2d, diff, objects, energy)
  tool_interface.py   — LLM 도구 4개 (observe, test_action, execute, analyze_region)
  llm_provider.py     — Claude/OpenAI/Local 프로바이더 추상화
  knowledge.py        — 탐색 프로토콜 + diff 휴리스틱 시스템 프롬프트
  templates/
    smart_agent.py    — SmartAgent (내부 도구 루프, 최대 5회)
```

**핵심 구조**: `choose_action()` 안에서 LLM이 observe→test→execute 도구를 호출하는 내부 루프.
execute가 호출될 때만 실제 게임 액션 수행.

### 2. 25개 게임 병렬 탐색 (완료)
10개 서브에이전트로 25개 게임 전부 탐색 시도:
- **12개 게임 Level 1+ 클리어**: ls20, vc33, ft09, tu93, tr87, cn04, re86, sp80, ar25, dc22, m0r0, su15, sc25, s5i5
- **9개 분석만**: sb26, ka59, lf52, lp85, bp35, cd82, g50t, sk48, tn36, wa30, r11l
- ⚠️ **15개 analysis 파일 삭제** — 에이전트가 environment_files 소스를 읽고 풀었음 (오염)
- 8개 clean analysis 파일만 보존 (ft09, m0r0, re86, su15, r11l, bp35, cd82, lf52)

### 3. play.py 인터랙티브 모드 추가 (완료)
- 매번 RESET부터 재실행하는 문제 해결
- 세션 파일(.sessions/)에 액션 히스토리 저장 → 빠른 리플레이로 상태 복원
- `uv run play.py --game vc33 --action ACTION1 --map` 으로 1스텝씩 실행

### 4. test_action에 ACTION6 지원 추가 (완료)
- 기존: ACTION1-5,7만 테스트 가능 → 클릭 전용 게임(vc33 등) 탐색 불가
- 수정: ACTION6 + x,y 좌표 테스트 지원

### 5. OpenAI API 테스트 (부분 성공)
- **gpt-5.4-nano**: 201 액션, 0 레벨 클리어 — 2D 맵 추론 능력 부족
- 도구 루프 자체는 정상 작동 (observe→test→execute 사이클 확인)

### 6. 로컬 Qwen3.5-0.8B 테스트 (실패)
**환경 구성 과정:**
- anaconda Python 3.10에 실수로 설치 → uv + Python 3.12 환경으로 수정
- transformers 5.4.0 + huggingface-hub 호환 문제 → hub 1.8.0으로 업그레이드
- PyTorch 2.11.0 + MPS(Apple Silicon GPU) 확인

**모델 로딩 성공:**
```
Python 3.12.9, PyTorch 2.11.0, MPS: True
Qwen3.5-0.8B: 752M params, ~1.5GB, MPS에서 실행
```

**게임 플레이 실패:**
- 스텝당 ~10초 (MPS 추론)
- 문제: tool call JSON (`{"tool":"observe","arguments":{}}`)을 생성 못 함
- 매번 "LLM returned no tool call" → fallback ACTION5
- 12스텝 실행 후 0 레벨 클리어
- **원인: 0.8B 모델이 structured JSON output을 안정적으로 생성하기엔 너무 작음**

### 7. Git commit (완료)
`b156e42` — 29파일, 5875줄
- .gitignore 정리 (wheels, environment_files, sessions, recordings 제외)
- ARC-AGI-3-Agents의 nested .git 제거 후 일반 파일로 추가

---

## 현재 상태

| 항목 | 상태 |
|------|------|
| 하네스 인프라 | ✅ harness.py, play.py |
| SmartAgent | ✅ 도구 루프 작동 |
| Claude API | ✅ 구조 완성 (키 없어서 미테스트) |
| OpenAI API | ⚠️ 작동하지만 nano로는 게임 못 품 |
| 로컬 Qwen 0.8B | ❌ 모델 로드 OK, tool call 생성 실패 |
| 게임 지식 | ✅ 8개 clean analysis + trajectory |
| Git | ✅ 커밋 완료 |

## Qwen 0.8B 프롬프트 단순화 실험 결과

### 변경 1: JSON → 텍스트 포맷
```
# Before (JSON — 파싱 실패)
{"tool": "observe", "arguments": {}}

# After (한 줄 텍스트)
OBSERVE / TEST ACTION6 62 33 / EXECUTE ACTION1
```

### 변경 2: 유연한 파서
`TEST ACTION6 (1, 1)` → regex로 숫자 추출, 괄호/쉼표 허용

### 변경 3: 시스템 프롬프트 축소
탐색 프로토콜, diff 휴리스틱, 에너지 규칙 → 5줄로 축소

### 변경 4: 맵 샘플링
64x64 전체 → 4행/2열 간격 샘플링 (토큰 75% 감소)

### 직접 테스트 결과 (독립 실행)
- 짧은 프롬프트 (100 토큰): `EXECUTE ACTION6 62 33` ✅ 정확
- 중간 프롬프트 (348 토큰): `OBSERVE` ✅ 정확
- 게임 상태 포함 (616 토큰): `TEST ACTION6 (1, 1)` ✅ (괄호 형식이지만 파싱 가능)

### SmartAgent 통합 테스트 (실패)
- 실제 게임 상태 (2000+ 토큰) → 포맷 깨짐 → fallback ACTION5
- RESET 5회 + ACTION6 1회 + ACTION5 20회 (fallback) = 0 레벨

### 결론
**Qwen 0.8B는 ~600 토큰 이하 입력에서만 포맷을 따름.**
SmartAgent의 실제 입력은 2000+ 토큰 → 모델이 지시를 잊어버림.

## 다음 단계 선택지

1. **프롬프트 단순화** — JSON tool call 대신 `ACTION6 62 33` 같은 텍스트 포맷
   → 0.8B도 가능할 수 있음, 가장 빠른 수정

2. **Qwen3.5-4B로 업그레이드** — 5배 큰 모델, Kaggle T4에 적합
   → tool calling 성공 확률 높음, 다운로드 필요

3. **Few-shot 예제 추가** — 시스템 프롬프트에 tool call 예시 삽입
   → 0.8B의 포맷 따르기 능력 향상 가능

4. **하이브리드**: CNN(StochasticGoose) + 소형 LLM
   → 탐색은 CNN, 판단은 LLM으로 분리
