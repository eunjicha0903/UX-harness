# Orchestrator (R7)

- 상태: CONFIRMED (사용자 승인 2026-10-25)
- Orchestrator = `CLAUDE.md`를 읽는 메인 세션. 상세 규칙은 아래 문서를 참조만 한다 (중복 금지).

## 1. 참조 지도

| 알아야 할 것 | 문서 |
|---|---|
| 업무 흐름·멈칫 (W1~W14) | `docs/story-work.md` |
| 판정값·실행 상태·해소·DONE (공통 규칙 SSOT) | `docs/harness-goal.md` |
| 단계 S1~S5·재실행·화면 판별 | `docs/pipeline.md` |
| 파일·상태·재개·커밋 | `docs/artifacts.md` |
| 게이트 G0~G5·GR·H0·H1 | `docs/gates.md` |
| 에이전트·트리거·Judge 이의 | `docs/agents.md`, `.claude/agents/` |
| 자료 상태값·자료 원칙 | `docs/context-inventory.md` |
| 프로젝트 값 | `projects/<slug>/story-service.md`, `project.json` |

## 2. 프로젝트 초기화 ("새 프로젝트 초기화: <이름>")

1. slug를 정해 사용자에게 확인한다 (영문 소문자·하이픈).
2. `templates/project/` → `projects/<slug>/` 복사 (`python3 scripts/harness.py init <slug>`).
3. 자료 수집: 사용자가 준 PRD·Notion·Figma를 확인하고 `sources/index.json`에 상태를 기록한다 (context-inventory §3 원칙). 다른 고객사 자료는 EXCLUDED로 기록한다.
4. R1-A 절차로 `story-service.md` 초안을 쓴다: 사용자 스토리(5문장 이내), 필수 규칙 1~2개(PRD 근거), 플랫폼 허용 목록, 검증 범위, 필수 규칙 판정 조건(ID), 화면 판별 재지정(필요 시).
5. **H0**: 사용자 승인 → `approved_at` 기록. 승인 전에는 검증을 시작하지 않는다 (G0).
6. `project.json`을 쓰고, Notion `업무 도우미 / UX검토 / <프로젝트>` 아래 검토 사항 DB를 만든다 (스키마는 innerbetter와 동일).
7. 실제 업무 흐름이 story-work와 다르면 `story-work-exceptions.md`에만 기록한다 (`docs/story-work.md`는 수정 금지).
8. 공통 파일과 섞지 않고 `[<slug>] init` 커밋.

## 3. 검증 실행 ("<프로젝트> UX 검증 시작" 등)

1. `state.json` 확인: 미완료 run이 있으면 묻지 않고 artifacts §6 기준으로 결정한다 (자료 해시가 같으면 재개, 다르면 새 run). 사용자 수정 피드백이 함께 들어오면 새 run으로 시작한다.
2. run-id 생성, `state.json` 기록 → G0.
3. `ux-context` → G1 → `sources.next/` 반영.
4. `ux-flow`, `ux-component` (병렬 가능) → G2, G3.
5. `ux-impact` → G4 → `impact-map.next.json` 반영.
6. s1~s4 해시 기록 → `ux-judge` → 반환 JSON을 `s5/judge.json`에 저장 → 해시 재검사 (G5②).
7. scripts: `final.json`(이의 반영) → DONE-01~10·GR → `s5-judgement.json` → `report.md`·`diff.json`.
8. G5 → Notion 반영 (실패 시 `notion-pending.json`) → `[<slug>] run <run-id>: <상태>` 커밋 (원격 연결 시 push).
9. 사용자에게 결과를 보고 → H1 대기.
   - 상태 (통과 / 검토 필요 = 미승인)
   - 미승인이면 이유: 필수 규칙 위반, 미해소 항목별 상세 사유(무엇이·왜·근거·영향 화면·후속 조치)
   - 피드백이 있었으면 피드백 항목별 고려해야 할 영역
   - report 경로, Notion 검토 사항 링크

실행 중에는 사용자에게 묻지 않는다 (pipeline §8). 단계가 끝날 때마다 한 줄 진행 표시만 한다 (예: `S2 완료 · G2 PASS · FAIL 3 / NEEDS_REVIEW 5`).
게이트 FAIL 시 gates.md §1 "실패 시" 열의 단계로 되돌아가고, 같은 게이트가 2회 FAIL이면 "실행 실패"로 끝내고 사유를 보고한다 (gates §3).

## 4. 재개 ("검증 재개")

`docs/artifacts.md` §6 절차를 그대로 따른다.

## 5. 사용자 승인·확인 시점

| 시점 | 무엇 | 근거 |
|---|---|---|
| 초기화 4단계 후 | H0 story-service 승인 | gates §2 |
| 실행 9단계 후 | H1 결과 확인 (Notion) | gates §2 |

검증 실행 중(실행 1~8단계)에는 사용자 확인 시점이 없다.
| 공통 하네스 파일 변경 | 사용자 승인 | artifacts §1 |

## 6. Orchestrator 금지

- 판정값 직접 수정 (판정은 에이전트, 최종 계산은 scripts)
- Notion 사용자 칸 쓰기, Figma 쓰기
- 프로젝트 실행 중 공통 하네스 파일 수정
- 사용자 승인 없이 H0·H1 완료 처리

## 7. scripts 구성

Python 3 표준 라이브러리만 사용한다 (설치 불필요).

`scripts/harness.py` 하위 명령:

| 명령 | 역할 |
|---|---|
| `init <slug>` | 템플릿 복사 |
| `gate <G0~G5\|GR> --slug --run` | 게이트 판정, PASS/FAIL + 사유 출력, 종료 코드 0/1 |
| `finalize --slug --run` | final.json·s5-judgement.json·report.md·diff.json 생성 |
| `notion-sync --slug --run` | Notion 반영 내용 생성 (실제 쓰기는 Orchestrator가 Notion MCP로 수행), 실패분 pending 적재 |
| `status --slug` | state.json·최근 결과 요약 |

## 8. 이너베러 소급 초기화 (구현 단계)

이너베러는 초기화 절차 확정 전에 만들어졌으므로, 최종 `CLAUDE.md` 승인 뒤 구현 단계에서 다음을 수행한다:
`project.json` 생성 / `sources/index.json` 생성 (SRC-00~10 상태, CF-01~06 이관) / story-service.md `approved_at: 2026-10-25` 기록 / context-inventory CF 표에 "이관됨" 표시.
