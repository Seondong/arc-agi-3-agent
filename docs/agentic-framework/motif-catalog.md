# Motif Catalog: 20개 Harness Narrative에서 추출한 구조화된 Motif 목록

> 이 문서는 20개 harness narrative (bp35, cd82, dc22, ft09, g50t, ka59, lp85, ls20, m0r0, r11l, re86, s5i5, sb26, sc25, sk48, sp80, su15, tr87, tu93, wa30)를 분석하여, Analogy Retriever 모듈이 사용할 수 있는 구조화된 motif catalog을 정리한 것이다.

---

## 1. Motif List -- 전체 목록 및 정의

### 1.1 Navigation (이동/탐색)
에이전트가 그리드/미로/통로를 따라 이동하여 목표 지점에 도달하는 구조.

### 1.2 Sokoban / Push (밀기 퍼즐)
에이전트가 블록을 밀어서 목표 위치에 배치하는 구조. 블록은 밀 수만 있고 당길 수 없는 것이 전형적.

### 1.3 Threading / Assembly (꿰기/조립)
꼬리(trail)를 확장하여 블록을 순서대로 꿰거나, 부품을 조립하여 목표 형태를 완성하는 구조.

### 1.4 Paint / Fill (페인팅/채우기)
커서/브러시를 이동하며 캔버스의 셀 값을 변경하여 참조 패턴을 재현하는 구조.

### 1.5 Toggle / Flip (토글/전환)
셀이나 블록의 상태를 두 값(또는 순환) 사이에서 전환하여 목표 패턴을 만드는 구조.

### 1.6 Pattern Completion / Sequence Logic (패턴 완성)
프레임의 각 변이나 격자에 배치된 색상/값 시퀀스의 규칙을 파악하여 빈 자리를 채우거나 올바른 시퀀스를 완성하는 구조.

### 1.7 Color Assignment / Slot Filling (색상 배정)
N개의 슬롯에 올바른 색상을 배정하는 구조. 참조 이미지가 정답 순서를 보여준다.

### 1.8 Sorting / Rearrangement (정렬/재배치)
블록이나 타일을 목표 순서/위치로 재배열하는 구조. Sliding puzzle, pick-and-place, 교환(swap) 등의 메커닉.

### 1.9 Symmetry / Mirror (대칭/거울)
좌우, 상하, 또는 회전 대칭을 완성하거나, 두 영역의 패턴을 대칭적으로 일치시키는 구조.

### 1.10 Click-Semantics / Coordinate Selection (클릭/좌표 선택)
십자형 조준선(crosshair)이나 커서를 이동하여 특정 좌표의 마커를 선택/클릭하는 구조.

### 1.11 Projectile / Bouncing (발사체/반사)
에이전트나 오브젝트가 특정 방향으로 발사되어 벽에서 반사되거나 목표에 도달하는 구조.

### 1.12 Gravity / Tetris (중력/테트리스)
블록에 중력이 적용되어 낙하하고, 이동/회전시켜 바닥에 쌓거나 특정 형태로 조립하는 구조.

### 1.13 Sliding / Diagonal Movement (미끄러짐/대각선 이동)
오브젝트가 대각선 경로를 따라 미끄러지듯 이동하거나, 2개의 ACTION으로 이진 방향 선택을 하는 구조.

### 1.14 Key-Door (열쇠-문)
특정 조건을 만족시키면 벽이 열리거나 새로운 경로가 활성화되는 구조.

### 1.15 Maze (미로)
벽(불투과 셀)과 통로(투과 셀)로 구성된 미로 내에서 경로를 탐색하는 구조.

### 1.16 Reflect (반사)
축(axis)을 기준으로 오브젝트나 패턴을 반사시켜 대칭 배치를 달성하는 구조.

### 1.17 Merge-Split (합치기/나누기)
블록을 합치거나 분열시켜 새로운 형태를 만드는 구조.

### 1.18 Snake / Trail (뱀/궤적)
에이전트가 이동하면서 뒤에 꼬리(trail)를 남기는 구조. 궤적의 형태가 목표를 달성하는 데 사용된다.

### 1.19 Collection / Pickup (수집)
에이전트가 맵을 이동하며 산재한 아이템/마커를 수집하는 구조.

### 1.20 Sequence Input (시퀀스 입력)
특정 ACTION 순서 자체가 정답이며, 올바른 시퀀스를 입력해야 클리어되는 구조.

### 1.21 Rotation / Turn (회전)
격자의 행/열을 회전(circular shift)시키거나, 블록을 90도 단위로 회전시켜 정렬하는 구조.

### 1.22 Piece Insertion (조각 끼우기)
특정 형태의 블록을 빈 공간에 정확히 끼워 넣는 구조. 크기/형태 매칭이 핵심.

---

## 2. Per-Motif Entry -- 상세 분석

### 2.1 Navigation (이동/탐색)

**정의**: 에이전트를 4방향으로 이동시켜 통로를 따라 목표 지점에 도달하는 구조.

**Observable features (관찰 가능 특징)**:
- 넓은 이동 가능 영역(값 일정)과 벽(다른 값)으로 구분된 구조
- 에이전트로 보이는 소형 복합 오브젝트(십자형, 다이아몬드 등)
- ACTION 4개 (상하좌우 대응)
- 참조 패턴이나 목표 위치가 별도 영역에 존재

**Best probe actions (최적 탐색 행동)**:
- ACTION1-4를 각 1회씩 시험하여 4방향 이동 확인
- 벽 방향으로 이동하여 충돌/반사/관통 여부 확인

**Common action semantics (일반적 ACTION 매핑)**:
- ACTION1=UP, ACTION2=DOWN, ACTION3=LEFT, ACTION4=RIGHT
- ACTION5/6이 있으면 특수 상호작용(잡기, 놓기, 제출 등)

**등장 게임**: ls20 (0.40), g50t (0.40), ka59 (0.20), re86 (0.25), wa30 (0.40), tu93 (0.20)

**Typical win condition**: 에이전트가 목표 위치에 도달하거나, 참조 패턴을 재현

---

### 2.2 Sokoban / Push (밀기 퍼즐)

**정의**: 에이전트가 블록을 밀어서 지정된 목표 위치에 배치하는 구조. 벽과 다른 블록이 이동을 제한.

**Observable features**:
- 테두리(█) 상자 안에 내용물이 있는 블록 2개 이상
- 에이전트(커서)와 독립된 이동 가능 블록들
- 넓은 이동 영역에 벽으로 구분된 통로
- 참조 이미지에 블록의 목표 위치가 표시됨

**Best probe actions**:
- 에이전트를 블록 방향으로 이동시켜 접촉 시 밀림 여부 확인
- 블록을 벽 방향으로 밀었을 때의 반응 관찰

**Common action semantics**:
- ACTION1-4: 에이전트 4방향 이동 (블록에 닿으면 push)
- ACTION5/6: 잡기(grab)/놓기(drop) 또는 제출

**등장 게임**: ka59 (0.30), ls20 (0.25), sc25 (0.20), sk48 (0.15), sp80 (0.15)

**Typical win condition**: 모든 블록이 목표 위치에 정확히 배치됨

---

### 2.3 Threading / Assembly (꿰기/조립)

**정의**: 꼬리(trail)를 확장하여 블록을 순서대로 관통시키거나, 부품을 올바른 순서/형태로 조립하는 구조.

**Observable features**:
- 다이아몬드/화살표 형태의 에이전트에서 수평 꼬리가 뻗어 있음
- 수직 레일(정거장)이 있어 에이전트가 높이를 조절
- 하단에 "완성된 형태"의 참조 이미지가 있으며, 블록이 꼬리 위에 꿰어진 상태
- 여러 독립 블록이 한쪽 벽에 고정되어 있음

**Best probe actions**:
- ACTION1/2로 수직 이동 시험 (레일 이동)
- ACTION3/4로 꼬리 확장/축소 시험
- 꼬리를 블록 방향으로 확장했을 때 블록과의 상호작용 관찰

**Common action semantics**:
- ACTION1=UP (수직 레일), ACTION2=DOWN
- ACTION3=RETRACT (꼬리 축소), ACTION4=EXTEND (꼬리 확장)
- ACTION6/7: 보조 기능

**등장 게임**: sk48 (0.55)

**Typical win condition**: 참조 이미지에 표시된 순서대로 모든 블록이 꼬리에 꿰어짐

---

### 2.4 Paint / Fill (페인팅/채우기)

**정의**: 커서를 캔버스 위에서 이동시키며 셀 값을 변경하여 참조 패턴을 재현하는 구조.

**Observable features**:
- 대형 단색 캔버스(값 일정) 영역
- 캔버스 위에 작은 커서/브러시 오브젝트
- 별도의 참조 패턴(상단 또는 하단)이 존재
- ACTION 중 "칠하기(paint)" 역할이 있는 것 (ACTION6 등)

**Best probe actions**:
- ACTION3/4로 커서 이동 확인
- ACTION6으로 현재 위치에 칠하기 시도
- 칠한 후 이동하여 칠하기의 영속성 확인

**Common action semantics**:
- ACTION1-4: 커서 4방향 이동
- ACTION6: 칠하기 (셀 값 변경)
- ACTION7: 지우기 또는 undo

**등장 게임**: bp35 (0.40), dc22 (0.35), ls20 (0.20), sc25 (0.40)

**Typical win condition**: 캔버스가 참조 패턴과 완전히 일치

---

### 2.5 Toggle / Flip (토글/전환)

**정의**: 셀이나 블록의 상태를 두 값 사이에서 전환(또는 순환)하여 목표 패턴을 만드는 구조.

**Observable features**:
- 두 가지 값(○/②, ○/⑮ 등)이 교대로 나타나는 격자
- ACTION이 1-2개만 사용 가능한 경우가 많음 (ACTION6만 등)
- 커서가 격자 위를 이동하며, 이동 시 또는 특수 ACTION으로 토글

**Best probe actions**:
- ACTION6 1회 시험 → 어떤 셀이 변화하는지 관찰
- ACTION6 2회 연속 시험 → 원래로 복귀하는지 (binary toggle) 또는 다른 상태로 진행 (cycle)

**Common action semantics**:
- ACTION1-4: 커서 이동 (있는 경우)
- ACTION6: 토글/전환
- ACTION7: 역방향 전환 또는 제출

**등장 게임**: ft09 (0.20), ka59 (0.15), tu93 (0.35), cd82 (0.35)

**Typical win condition**: 모든 셀이 목표 상태(체커보드, 단일 색, 참조 패턴)와 일치

---

### 2.6 Pattern Completion / Sequence Logic (패턴 완성)

**정의**: 프레임의 변(edge)이나 격자에 배치된 색상 시퀀스의 규칙을 파악하고, 빈 자리를 채우거나 올바른 시퀀스를 완성하는 구조.

**Observable features**:
- 프레임의 4변(상하좌우)에 4x4 색상 블록이 시퀀스로 배치
- ACTION6만 사용 가능 (관찰 후 제출 유형)
- 참조 영역에 ▓ 블록이 나열되어 있을 수 있음
- 프레임 코너에 ★ 등의 마커가 있음

**Best probe actions**:
- ACTION6 실행 전에 패턴을 철저히 분석 (스텝 소모 없음)
- ACTION6 1회 시험 → 제출인지 변환인지 확인

**Common action semantics**:
- ACTION6: 제출(submit) 또는 색상 순환

**등장 게임**: lp85 (0.45), ft09 (0.40)

**Typical win condition**: 시퀀스 규칙이 모든 변에서 만족됨

---

### 2.7 Color Assignment / Slot Filling (색상 배정)

**정의**: N개의 빈 슬롯에 올바른 색상을 배정하는 구조. 하단 참조 이미지가 정답 순서를 보여준다.

**Observable features**:
- N개의 빈 슬롯(② 등)이 일렬로 배치
- 상단에 색상 팔레트(사용 가능한 색 목록)
- 하단에 정답 색상 순서 (참조 이미지)
- ACTION이 3개 정도 (커서 이동 + 색 순환 + 제출)
- 방향 이동 ACTION(1-4)이 없음

**Best probe actions**:
- ACTION6으로 슬롯 색상 변화 시험 → 순환 순서 파악
- ACTION5로 슬롯 간 이동 시험
- ACTION7로 제출 시험

**Common action semantics**:
- ACTION5: 커서 이동 (다음 슬롯)
- ACTION6: 색상 순환 (정방향)
- ACTION7: 제출 또는 역방향 순환

**등장 게임**: sb26 (0.50)

**Typical win condition**: 모든 슬롯의 색상이 참조 순서와 일치

---

### 2.8 Sorting / Rearrangement (정렬/재배치)

**정의**: 블록이나 타일을 참조 패턴의 순서/위치와 일치하도록 재배열하는 구조.

**Observable features**:
- 다수의 패턴 블록이 격자 형태로 배치 (4x3 등)
- 하단에 목표 순서를 보여주는 참조 패턴이 별도로 존재
- 에이전트(○ 프레임 등)가 블록 크기와 동일한 빈 컨테이너
- 4방향 이동 ACTION

**Best probe actions**:
- ACTION1-4로 에이전트 이동 → 이동 단위(1칸 vs 블록 크기) 확인
- 에이전트를 블록 위치까지 이동 → 상호작용(pick/swap/push) 확인

**Common action semantics**:
- ACTION1-4: 에이전트 4방향 이동
- 블록 위에서 자동 pick 또는 swap

**등장 게임**: tr87 (0.50), sb26 (0.25)

**Typical win condition**: 모든 블록이 참조 패턴의 순서와 일치하도록 배치됨

---

### 2.9 Symmetry / Mirror (대칭/거울)

**정의**: 좌우 또는 상하 분할된 두 영역의 패턴을 대칭적으로 일치시키는 구조.

**Observable features**:
- 화면이 좌우 또는 상하로 명확히 분할 (서로 다른 색/값으로 채워진 두 반면)
- 두 영역의 패턴이 "비슷하지만 다름"
- 분할 축에 벽(⑮ 등)이 있을 수 있음
- 양쪽에 대칭적으로 배치된 마커(⑩ 등)

**Best probe actions**:
- ACTION1로 이동 → 한쪽만 변하는지, 양쪽 동시 변하는지 확인
- ACTION5/6으로 좌우 전환 또는 대칭 조작 확인

**Common action semantics**:
- ACTION1-4: 이동 또는 구멍 경계 편집
- ACTION5: 좌우 전환 또는 회전
- ACTION6: 제출 또는 추가 조작

**등장 게임**: m0r0 (0.35), ka59 (0.35), s5i5 (0.45)

**Typical win condition**: 두 영역의 패턴이 분할 축에 대해 완벽한 거울 대칭

---

### 2.10 Click-Semantics / Coordinate Selection (클릭/좌표 선택)

**정의**: 십자형 조준선(crosshair)을 이동시켜 마커 위치에 교차점을 맞추고, ACTION5 등으로 "클릭"하는 구조.

**Observable features**:
- 거대한 십자형(+) 구조가 화면을 관통
- 교차점에 ○(커서) 마커
- 그리드 곳곳에 산재한 소형 마커들(★, ◆)
- 5개 ACTION (4방향 + 클릭)

**Best probe actions**:
- ACTION1 시험 → 십자형 전체가 이동하는지, ○만 이동하는지 확인
- ACTION5 시험 → 마커와 겹칠 때/겹치지 않을 때의 차이 관찰

**Common action semantics**:
- ACTION1-4: 십자형 이동 (4방향)
- ACTION5: 클릭/선택/실행

**등장 게임**: re86 (0.35)

**Typical win condition**: 모든 목표 마커를 클릭 (순서가 중요할 수 있음)

---

### 2.11 Projectile / Bouncing (발사체/반사)

**정의**: 에이전트가 특정 방향으로 발사되어 벽에서 반사되거나 목표에 도달하는 구조.

**Observable features**:
- 에이전트에서 대각선 궤적(trail)이 뻗어 있음
- ACTION6만 사용 가능 (단일 버튼)
- 거대한 ▓ blob 형태의 장애물
- 상단에 목표 위치(다이아몬드 등)

**Best probe actions**:
- ACTION6 1회 → 에이전트가 이동하는지 방향이 바뀌는지 확인
- ACTION6 연속 → 궤적 패턴 관찰

**Common action semantics**:
- ACTION6: 1스텝 이동 또는 방향 전환 또는 발사

**등장 게임**: r11l (0.40)

**Typical win condition**: 에이전트가 목표 위치에 정확히 도달

---

### 2.12 Gravity / Tetris (중력/테트리스)

**정의**: 블록에 중력이 적용되어 낙하하며, 좌우 이동/회전으로 바닥에 배치하는 구조.

**Observable features**:
- L자형/T자형 블록이 존재 (테트리스 피스 형태)
- 하단에 "바닥(●)" 영역
- 상단에 작은 블록이 "매달려" 있거나 떠 있는 형태
- 6개 ACTION (좌, 우, CW, CCW, soft drop, hard drop)
- 블록들이 4행 높이 단위로 규격화

**Best probe actions**:
- ACTION1/2로 좌우 이동 시험
- ACTION3/4로 회전 시험 (블록 형태 변화 관찰)
- ACTION5로 하드드롭 시험 (주의: 비가역적일 수 있음)

**Common action semantics**:
- ACTION1: LEFT, ACTION2: RIGHT
- ACTION3: ROTATE_CW, ACTION4: ROTATE_CCW
- ACTION5: HARD_DROP, ACTION6: SOFT_DROP

**등장 게임**: sp80 (0.35)

**Typical win condition**: 블록을 빈 틈 없이 배치하거나, 특정 조건 달성

---

### 2.13 Sliding / Diagonal Movement (미끄러짐/대각선 이동)

**정의**: 오브젝트가 대각선 경로를 따라 미끄러지며, 2개의 ACTION으로 방향을 제어하는 구조.

**Observable features**:
- 대각선 · 마커들이 45도 각도로 경로를 형성
- 도넛(중앙이 빈) 형태의 오브젝트
- ACTION이 2개만 사용 가능 (ACTION6, ACTION7)
- 경로의 시작점(오브젝트)과 끝점(목표 마커)이 존재

**Best probe actions**:
- ACTION6 1회 → 이동 방향과 거리 확인
- ACTION7 1회 → ACTION6과의 차이 확인 (방향?)
- ACTION6/7 교대 → 경로 유연성 확인

**Common action semantics**:
- ACTION6: 방향 A (예: 좌하 대각선)
- ACTION7: 방향 B (예: 우하 대각선)

**등장 게임**: su15 (0.35)

**Typical win condition**: 오브젝트가 대각선 경로를 따라 목표 지점에 도달

---

### 2.14 Maze (미로)

**정의**: ▓ 벽과 ○ 통로로 구성된 미로 내에서 에이전트를 이동시켜 목표에 도달하는 구조.

**Observable features**:
- 대형 직사각형 구조물 내에 벽(▓)과 통로(○)가 교대
- 참조 영역에 에이전트의 원형/형태가 표시
- 트랙(♥ 등)이 이동 가능 경로를 시각적으로 보여줌
- 5개 ACTION (4방향 + 특수)

**Best probe actions**:
- ACTION1-4로 미로 내 이동 확인
- 벽에 부딪힐 때의 반응 관찰

**Common action semantics**:
- ACTION1-4: 4방향 이동
- ACTION5: 잡기/놓기 또는 특수 조작

**등장 게임**: g50t (0.40), m0r0 (0.25)

**Typical win condition**: 미로의 출구(목표 지점)에 도달

---

### 2.15 Collection / Pickup (수집)

**정의**: 에이전트가 맵을 이동하며 산재한 아이템/위성을 수집하여 중앙으로 가져오는 구조.

**Observable features**:
- 넓은 빈 배경에 소수의 오브젝트(위성)가 산재
- 중앙에 프레임 구조(수집 결과 표시)
- 에이전트(⑭ 등)가 독립적 위치에 존재
- 5개 ACTION (4방향 + 수집/전달)

**Best probe actions**:
- ACTION1-4로 에이전트 이동
- 위성에 접근 후 ACTION5로 상호작용 시험

**Common action semantics**:
- ACTION1-4: 에이전트 4방향 이동
- ACTION5: 수집(grab) 또는 전달(deliver)

**등장 게임**: wa30 (0.40), dc22 (0.20)

**Typical win condition**: 모든 위성/아이템을 수집하여 중앙 프레임에 전달

---

### 2.16 Rotation / Turn (회전)

**정의**: 격자의 행 또는 열을 circular shift하거나, 블록/패턴을 90도 단위로 회전시켜 정렬하는 구조.

**Observable features**:
- 3x3 블록 격자 구조
- 커서(◆)와 목표 마커(⑭)가 대각선 양 끝에 배치
- 4개 ACTION (각각 행/열 회전에 대응?)
- 참조 패턴이 없는 경우가 많음 (규칙 기반 목표)

**Best probe actions**:
- ACTION1 시험 → 커서 이동인지 행/열 회전인지 확인
- 변화한 셀 패턴으로 회전 축과 방향 파악

**Common action semantics**:
- ACTION1/2: 행 좌/우 회전 또는 상/하 이동
- ACTION3/4: 열 상/하 회전 또는 좌/우 이동

**등장 게임**: tu93 (0.15), s5i5 (0.20)

**Typical win condition**: 격자가 체커보드 패턴 또는 특정 정렬 상태 달성

---

### 2.17 Piece Insertion (조각 끼우기)

**정의**: 특정 형태/크기의 블록을 빈 공간에 정확히 끼워 넣는 구조. 크기 매칭이 핵심.

**Observable features**:
- 큰 오브젝트에 빈 공간(hole)이 있음
- 별도의 블록이 빈 공간과 정확히 같은 크기
- 빈 공간 → 블록 크기 매칭이 시각적으로 명확

**Best probe actions**:
- ACTION6/7로 블록 이동 방향 시험
- 블록을 빈 공간 쪽으로 이동시켜 삽입 메커닉 확인

**Common action semantics**:
- ACTION6/7: 블록 이동 (2방향만 사용 가능한 경우)

**등장 게임**: su15 (0.20)

**Typical win condition**: 블록이 빈 공간에 정확히 삽입됨

---

## 3. Motif Co-occurrence Matrix (공출현 매트릭스)

같은 게임에서 상위 후보로 동시에 거론된 motif 쌍을 정리한다. 빈도가 높을수록 두 motif가 혼합되어 나타날 가능성이 크다.

| Motif A | Motif B | 공출현 게임 수 | 대표 게임 |
|---------|---------|:---:|---------|
| Navigation | Sokoban/Push | 4 | ls20, ka59, g50t, wa30 |
| Navigation | Paint/Fill | 3 | ls20, dc22, sc25 |
| Navigation | Collection | 3 | wa30, dc22, g50t |
| Paint/Fill | Pattern Completion | 2 | bp35, sc25 |
| Toggle | Sliding Puzzle | 2 | tu93, ft09 |
| Symmetry | Toggle | 2 | ka59, m0r0 |
| Symmetry | Maze | 1 | m0r0 |
| Gravity | Assembly | 1 | sp80 |
| Threading | Navigation | 1 | sk48 |
| Color Assignment | Sorting | 1 | sb26 |
| Click-Semantics | Reflect | 1 | re86 |
| Projectile | Toggle | 1 | r11l |
| Sliding | Piece Insertion | 1 | su15 |
| Sorting | Selection/Matching | 1 | tr87 |
| Pattern Completion | Color Matching | 1 | lp85 |

**핵심 공출현 패턴**:
- **Navigation + Sokoban/Push**가 가장 빈번한 공출현 쌍이다. 4방향 이동 기반 게임에서 블록 밀기가 추가되는 복합 구조.
- **Navigation + Paint/Fill**도 빈번하다. 이동 후 셀 값을 변경하는 "이동 + 칠하기" 복합 구조.
- **Navigation + Collection**이 세 번째로 빈번하다. 에이전트가 이동하며 아이템을 수집하는 구조.
- **Symmetry + Toggle**이 특수한 공출현이다. 좌우 대칭 구조에서 셀을 토글하여 대칭을 완성하는 구조.

---

## 4. Feature --> Motif Mapping (특징 기반 Motif 추론 표)

관찰된 특징(feature)으로부터 가장 가능성 높은 motif를 추론하기 위한 참조 테이블.

### 4.1 가용 ACTION 수 기반 추론

| 가용 ACTION | 가능성 높은 Motif | 가능성 낮은 Motif | 대표 게임 |
|:---:|---------|---------|---------|
| **1개 (ACTION6만)** | Pattern Completion, Toggle, Projectile, Symmetry | Navigation, Sokoban, Threading | ft09, lp85, r11l, s5i5 |
| **2개 (ACTION6+7)** | Sliding/Diagonal, Binary Toggle, Piece Insertion | Sokoban, Sorting, Click-Semantics | su15 |
| **3개 (ACTION5+6+7)** | Color Assignment, Slot Filling | Navigation, Maze | sb26 |
| **4개 (ACTION1-4)** | Navigation, Sokoban, Toggle, Sorting, Rotation | Click-Semantics, Threading | ls20, tr87, tu93 |
| **5개 (ACTION1-4+5 or 6)** | Navigation+특수, Maze, Click-Semantics, Collection | 단순 Toggle | g50t, ka59, re86, sc25, wa30, dc22 |
| **6개 (ACTION1-6)** | Gravity/Tetris, Symmetry+편집, Assembly | 단순 Navigation | sp80, m0r0, cd82 |

### 4.2 장면 구조 기반 추론

| 관찰된 특징 | 1순위 Motif | 2순위 Motif | 3순위 Motif |
|---------|---------|---------|---------|
| 대형 단색 캔버스 + 소형 커서 + 참조 패턴 | Paint/Fill | Navigation | Pattern Completion |
| 좌우 분할 + 유사하지만 다른 패턴 | Symmetry | Toggle | Sliding Puzzle |
| 십자형(+) 구조 + 산재 마커 | Click-Semantics | Reflect | Navigation |
| 수직 레일 + 수평 꼬리 + 독립 블록 | Threading | Navigation | Sokoban |
| 3x3 블록 격자 + ○/② 교대 | Toggle | Sliding Puzzle | Rotation |
| N개 빈 슬롯 + 색상 팔레트 + 참조 순서 | Color Assignment | Sorting | Toggle |
| 패턴 블록 격자 + 하단 참조 일렬 배치 | Sorting | Selection | Sokoban |
| L자형 블록 + 바닥 + 6 ACTION | Gravity/Tetris | Assembly | Sokoban |
| 대각선 trail + 단일 ACTION | Projectile | Toggle | Bouncing |
| 대각선 · 마커 + 2 ACTION + 도넛 형태 | Sliding/Diagonal | Binary Toggle | Piece Insertion |
| 미로 벽(▓) + 통로(○) + 트랙(♥) | Maze | Navigation | Snake/Trail |
| 넓은 빈 배경 + 소수 위성 + 중앙 프레임 | Collection | Sokoban | Snake |
| 화살표/포인터 + 체커보드 + 보조 패턴 | Paint/Fill | Pointer Navigation | Block Push |
| 프레임 4변에 색상 시퀀스 + ACTION6만 | Pattern Completion | Submit & Check | Color Rotation |
| 프레임 내 대칭 패턴 + 분할선 + 포인터 | Symmetry | Pattern Matching | Rotation |

### 4.3 에너지 바 위치/값 기반 추론

| 에너지 바 특징 | 시사점 |
|---------|---------|
| R63에 ○(값 0) 64셀 | 표준 에너지 바 (64스텝) |
| R63에 ◆(값 9) 64셀 | 표준 에너지 바 (64스텝), 오브젝트 색과 연관 가능 |
| R63에 ⑮(값 15) 64셀 | 표준 에너지 바 |
| R63에 ▲(값 12) 64셀 | 에너지 또는 제출 카운터 |
| R63에 █(값 4) 64셀 | 에너지 바 또는 단순 경계선 (확인 필요) |
| 수직 바 (C0 또는 C62-63) | 세로 방향 에너지 바 (비표준) |
| R0에 ⑭(값 14) 64셀 | 상단 에너지 바 또는 상태 표시 |
| R60-63에 ●(값 1) 256셀 | 바닥/지면 (에너지 아닌 환경 요소) |
| 명시적 에너지 바 부재 | 에너지 제한 없거나 숨겨져 있음 |

### 4.4 특수 패턴 기반 추론

| 특수 패턴 | 시사하는 Motif |
|---------|---------|
| 참조 이미지에 블록이 꼬리 위에 꿰어진 형태 | **Threading** (sk48) |
| 두 색상의 반복적 대비 (○/⑮) + 범례 상자 | **Color Fill** (cd82) |
| ②/○ lock 블록 내부에 ♥ 셀 포함 | **Lock/Unlock** 또는 **Toggle** (ft09) |
| 다이아몬드 형태 에이전트 + 대각선 trail(●) | **Projectile** (r11l) |
| 도넛 형태(중앙 빈 공간) + 대각선 · 마커 경로 | **Sliding** (su15) |
| ♥ L자형 트랙이 미로 내부에 있음 | **Maze + Trail** (g50t) |
| 거대 십자형 + 교차점에 ○ | **Click-Semantics** (re86) |
| 프레임 내 대칭 패턴 + 중앙 분할선(·) | **Symmetry Completion** (s5i5) |
| 4x4 색상 프레임이 일렬 + 참조 순서 | **Color Assignment** (sb26) |
| 좌우 ★/▲ 분할 + 같은 구조의 구멍 패턴 | **Symmetry** (m0r0) |

---

## 5. 게임별 Motif 요약표

| 게임 | 1순위 Motif | Confidence | 가용 ACTION | 에너지 바 |
|------|---------|:---:|:---:|---------|
| bp35 | Paint/Fill (Pattern Painting) | 0.40 | 3,4,6,7 | R63 ○ 64셀 |
| cd82 | Color Fill / Toggle | 0.35 | 1-6 | 불명확 (R63 █) |
| dc22 | Paint/Drawing + Placement | 0.35 | 1-4,6 | R63 ○ 64셀 |
| ft09 | Pattern Matching / Toggle | 0.40 | 6만 | R63 ▲ 64셀 |
| g50t | Maze Navigation | 0.40 | 1-5 | R63 ◆ 64셀 |
| ka59 | Symmetry (Match/Mirror) | 0.35 | 1-4,6 | R63 █ (불확실) |
| lp85 | Pattern Completion | 0.45 | 6만 | ⑭ 수직 바 또는 ▓ 블록 |
| ls20 | Navigation | 0.40 | 1-4 | R61-62 ★/♥ |
| m0r0 | Symmetry Completion | 0.35 | 1-6 | 미확인 |
| r11l | Projectile | 0.40 | 6만 | ② ~36셀 |
| re86 | Click-Semantics | 0.35 | 1-5 | R63 ⑮ 64셀 |
| s5i5 | Symmetry Puzzle | 0.45 | 6만 | 미확인 |
| sb26 | Color Assignment | 0.50 | 5,6,7 | R53 ② 64셀 |
| sc25 | Tile Painting | 0.40 | 1-4,6 | C62-63 ⑭ 128셀 |
| sk48 | Threading/Assembly | 0.55 | 1-4,6,7 | R53 ② |
| sp80 | Gravity/Tetris | 0.35 | 1-6 | R0 ⑭ 64셀 |
| su15 | Sliding/Diagonal | 0.35 | 6,7 | R63 ○ 64셀 |
| tr87 | Sorting/Rearrangement | 0.50 | 1-4 | R63 ● 64셀 |
| tu93 | Toggle / Sliding Puzzle | 0.35 | 1-4 | R63 ♦ 64셀 |
| wa30 | Collection (Collect & Deliver) | 0.40 | 1-5 | R63 ⑦ 64셀 |

---

## 6. Analogy Retriever 활용 가이드

이 catalog을 Analogy Retriever 모듈에서 사용하는 방법:

### 6.1 입력 (Input)
새 게임의 초기 프레임을 분석한 후 다음 feature vector를 추출:
1. `available_actions`: 가용 ACTION 목록
2. `scene_structure`: 주요 영역 (캔버스, 참조, 에너지 바 등)
3. `object_types`: 식별된 오브젝트 종류와 형태
4. `special_patterns`: 대칭, 대각선, 격자, 십자형 등

### 6.2 검색 (Retrieval)
1. Section 4의 Feature --> Motif Mapping 테이블을 참조하여 상위 3개 motif 후보를 선별
2. Section 3의 Co-occurrence Matrix를 참조하여 복합 motif 가능성을 평가
3. Section 5의 게임별 요약표에서 유사한 feature를 가진 과거 게임을 검색

### 6.3 출력 (Output)
```json
{
  "motif_candidates": [
    {"motif": "navigation", "confidence": 0.40, "similar_game": "ls20"},
    {"motif": "sokoban", "confidence": 0.25, "similar_game": "ka59"},
    {"motif": "paint", "confidence": 0.20, "similar_game": "bp35"}
  ],
  "probe_plan": ["ACTION1 x1", "ACTION2 x1", "ACTION3 x1", "ACTION4 x1"],
  "critical_observation": "에이전트 이동 방향/단위, 벽 충돌 반응"
}
```

### 6.4 핵심 판별 규칙 요약

1. **ACTION이 1개뿐이면** → 반드시 "그 ACTION의 의미"를 먼저 파악. 이동이 아닌 토글/제출/발사 계열.
2. **ACTION이 4개이면** → 대부분 4방향 이동. Navigation 기반 게임.
3. **ACTION이 6개이면** → 이동 + 회전 + 드롭 또는 이동 + 좌우 전환 + 특수. 복합 메커닉.
4. **참조 이미지가 있으면** → 참조와 현재 상태의 차이(diff)를 계산하여 필요한 변환을 역산.
5. **참조 이미지가 없으면** → 규칙 기반 목표 (체커보드, 대칭, 도달 등). 목표 자체를 추론해야 함.
6. **에너지 바가 있으면** → 첫 실험에서 ACTION당 에너지 소비량을 반드시 확인. 탐색 예산을 미리 할당.
7. **좌우/상하 분할이 있으면** → Symmetry 계열 motif를 우선 검토.
8. **대각선 패턴이 있으면** → Projectile 또는 Sliding 계열 motif를 우선 검토.
