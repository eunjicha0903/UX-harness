# Gates (R5)

- 상태: CONFIRMED (사용자 승인 2026-10-25)
- 공통 하네스 문서. 판정 조건은 SSOT(`docs/harness-goal.md`, `projects/<slug>/story-service.md`)의 ID로만 참조한다.
- 모든 게이트는 `scripts/`가 판정한다 (사람 승인 H0·H1 제외). 결과: `PASS` / `FAIL` + 실패 사유 목록.

## 1. 게이트 목록

| 게이트 | 시점 | story-work 근거 | 검사 (모두 참이어야 PASS) | 실패 시 |
|---|---|---|---|---|
| **G0 형식** | 매 실행 시작 | W1 "출처와 기준 문서 확인" | ① harness-goal.md 5-1~5-3 표를 ID로 읽을 수 있음 ② story-service.md에 플랫폼 허용 목록·검증 범위·필수 규칙 판정 조건(ID 형식 `숫자-영문`)이 있음 ③ project.json 필수 필드(slug, Figma fileKey·page, Notion data_source) 존재 ④ H0 승인 기록 존재 | 실행 중단 → 프로젝트 초기화(B)로 |
| **G1 맥락** | S1 종료 | W1, W2 | ① sources/index.json의 모든 자료에 상태값 존재 ② 모든 REQ에 source_id가 있고 그 자료가 FETCHED ③ 화면 목록이 비어 있지 않고 허용 플랫폼마다 1개 이상 (없으면 해당 플랫폼 INSUFFICIENT_INFO 기록 필수) ④ 화면 platform ⊂ 허용 목록 (DONE-06) ⑤ EXCLUDED 자료 인용 0건 (DONE-05) ⑥ Notion 읽기 결과(성공/실패) 기록됨 | S1 |
| **G2 요구사항·흐름** | S2 종료 | W6 멈칫 "기능이 성립하지 않는 곳" | ① 모든 REQ에 레코드 1개 이상 ② 모든 레코드가 공통 항목 레코드 형식 충족 (DONE-02, DONE-03) ③ FETCHED가 아닌 근거로 PASS 0건 (DONE-04) ④ story-service 필수 규칙 판정 조건 ID 전부에 레코드 존재 (DONE-07) | S2 / 화면·REQ 부족이면 S1 |
| **G3 컴포넌트** | S3 종료 | W6, W14(조건부) | ① 화면 목록에 쓰인 컴포넌트(인스턴스 원본 기준) 전부에 레코드 ② 레코드 형식 (DONE-02, DONE-03, DONE-04) ③ design.md가 없으면 가이드 검사 레코드가 INSUFFICIENT_INFO 1건으로 존재 | S3 / 목록 부족이면 S1 |
| **G4 영향 분석** | S4 종료 | W3 멈칫 "기존 기능과 충돌·누락", W7 | ① 기점(변경점 + S2·S3 FAIL + 재검증 대상) 전부에 분석 단위 존재 ② DONE-08 ③ DONE-09 ④ 기점이 플랫폼 간 연결을 가지면 상대 플랫폼 화면이 관련 화면에 포함 ⑤ impact-map 갱신 기록 | S4 / 근거 부족이면 S1 |
| **G5 판정** | S5 종료 | W8 | ① DONE-01~DONE-10 전부 참 ② **Judge 무결성**: S5 전후 s1~s4 산출물 해시 동일 ③ 실행 상태가 harness-goal 5-2 규칙대로 계산됨 ④ Notion 반영 성공 또는 notion-pending.json 적재 | 어긴 조건을 만든 단계로 / ② 위반은 실행 실패 처리 후 S2부터 |
| **GR 필수 규칙** | G5 안에서 | story-service 필수 규칙 | rule_ref가 있는 레코드 중 FAIL 0건이면 PASS. 1건 이상이면 FAIL: 상태 "검토 필요" 강제, report.md 최상단 표시, Notion `필수 규칙` 표시, 컨펌으로 해소 불가 | 실행은 끝까지 계속 |

## 2. 사람 승인

| ID | 시점 | 누가 | 무엇을 | 기록 위치 | 없으면 |
|---|---|---|---|---|---|
| H0 | 프로젝트 초기화 (프로젝트당 1회) | 디자이너 | story-service.md 내용 승인 (판정 기준을 정하는 문서이므로) | story-service.md 상단 `approved_at` | G0 FAIL |
| H1 | S5 이후 (매 실행) | 디자이너 | report.md 확인, NEEDS_REVIEW 결정 | Notion 컨펌 완료 + 결정 메모 | 해당 항목 미해소 유지 (다음 실행에서 반영) |

H1은 실행을 막지 않는다. H1 결과는 다음 실행 S1에서 읽혀 상태 계산에 반영된다.

## 3. 반복 실패

- 같은 run에서 같은 게이트가 2회 FAIL이면 실행을 멈추고, 실패 사유와 필요한 자료를 사용자에게 묻는다.
- 멈춘 상태는 state.json `last_error`에 기록하고, 사용자 응답 후 해당 단계부터 재개한다.

## 4. 게이트 ↔ 문제 유형 커버리지 (harness-goal §1)

| P1 | P2 | P3 | P4 | P5 | P6 | P7 |
|---|---|---|---|---|---|---|
| G2 | G2 | G3 | G2·G4 | G4 | G1④·G4④ | G1②·G2③·DONE-10 |
