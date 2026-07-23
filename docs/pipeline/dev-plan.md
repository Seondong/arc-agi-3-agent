<!-- [Mar 29] Created by SD with Claude Opus 4.6. -->
# ARC-AGI-3 개발 계획

## 접근 방식: 하네스 엔지니어링

Anthropic의 하네스 엔지니어링 패턴을 적용. Claude Code 자체가 게임을 분석하고 액션을 결정하는 구조.
- 참고: https://www.anthropic.com/engineering/harness-design-long-running-apps

## 아키텍처

```
[harness.py] ← Python 스크립트: 게임 실행, 프레임 출력
     ↕
[Claude Code] ← 하네스: 프레임 분석 → 액션 결정 → harness.py 재실행
```

- 오프라인 모드 (2000+ FPS): 매번 처음부터 재실행해도 빠름
- 그리드 압축: RLE + 동일행 병합 + diff 기반
- API 비용 없음 (Claude Code Max 구독으로 커버)

## 구현 현황

### Phase 1: 기본 인프라 (완료 — 2026-03-29)
- [x] git init, .env 설정, arc-agi 패키지 설치
- [x] 오프라인/온라인 모드 동작 확인
- [x] `harness.py` — Claude Code가 게임을 조작하는 배치 스크립트
- [x] `claude_agent.py` — Claude API 에이전트 (API 키 필요 시 사용 가능)
- [x] 그리드 압축 유틸리티 (RLE, diff)

### Phase 2: 게임 탐색 및 이해 (진행 중)
- [ ] ls20 게임 메커닉 완전 분석
- [ ] 각 액션의 효과 매핑
- [ ] 레벨 1 (튜토리얼) 클리어
- [ ] 탐색 전략 패턴화

### Phase 3: 자동화 에이전트
- [ ] Claude Code 하네스 패턴을 자동화 스크립트로 발전
- [ ] 탐색자(Explorer) → 모델러(Modeler) → 실행자(Executor) 분리
- [ ] 여러 게임에서 테스트

### Phase 4: Kaggle 제출
- [ ] 로컬 모델 (Qwen 등)로 전략 디스틸
- [ ] 또는 CNN + 소형 LM 하이브리드
- [ ] Kaggle 노트북 포맷에 맞춰 제출

## 파일 구조

```
arc-agi-3/
├── CLAUDE.md                  # 프로젝트 컨텍스트
├── .env                       # API 키 (루트)
├── .gitignore
├── docs/
│   └── dev-plan.md            # 이 파일
├── code/
│   ├── ARC-AGI-3-Agents/      # 에이전트 프레임워크
│   │   ├── harness.py         # Claude Code 하네스 스크립트
│   │   ├── agents/
│   │   │   └── templates/
│   │   │       └── claude_agent.py  # Claude API 에이전트
│   │   └── ...
│   └── environment_files/     # 게임 환경 파일 (25개)
├── ARC_AGI_3_Technical_Report.pdf
└── *.ipynb                    # 샘플 제출 노트북
```

## 핵심 도구

| 도구 | 용도 |
|------|------|
| `uv run harness.py --game X --actions '[...]'` | 게임 실행 + 프레임 출력 |
| `uv run main.py --agent=random --game=X` | 기존 에이전트 프레임워크 |
| `--compact` 플래그 | 중간 프레임은 요약, 마지막만 상세 |

## 게임 목록 (public 25개)

ar25, bp35, cd82, cn04, dc22, ft09, g50t, ka59, lf52, lp85,
ls20, m0r0, r11l, re86, s5i5, sb26, sc25, sk48, sp80, su15,
tn36, tr87, tu93, vc33, wa30
