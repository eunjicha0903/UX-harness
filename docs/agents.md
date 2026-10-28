# Agents (R6)

- 상태: CONFIRMED (사용자 승인 2026-10-25)
- 공통 하네스 문서. 판정 규칙은 `docs/harness-goal.md`·`story-service.md` ID로만 참조한다. 게이트는 `docs/gates.md`.
- 실행 정의 파일: `.claude/agents/*.md`

## 1. 역할 구성

| 역할 | 형태 | 단계 | 통합 여부 |
|---|---|---|---|
| Orchestrator | 메인 세션 (`CLAUDE.md`) | 전체 | — |
| Context Agent | 하위 에이전트 `ux-context` | S1 | — |
| Flow Agent | 하위 에이전트 `ux-flow` | S2 | 요구사항 검증 + User Flow 통합 |
| Component UX Agent | 하위 에이전트 `ux-component` | S3 | — |
| Impact Analysis Agent | 하위 에이전트 `ux-impact` | S4 | — |
| Judge Agent | 하위 에이전트 `ux-judge` (읽기 전용) | S5 | — |

## 2. 에이전트별 정의

| 에이전트 | 편집 가능 폴더 (1개) | 읽기 | 입력 | 출력 | 도구 | 스킬 |
|---|---|---|---|---|---|---|
| Orchestrator | `projects/<slug>/` (단, `results/<run-id>/s1~s4/` 제외) | 전체 | 사용자 명령, `state.json` | `state.json`, `sources/`·`impact-map.json` 반영, `s5/` 저장, `report.md`, Notion 쓰기, 커밋 | 전부 + `scripts/` | — |
| Context | `results/<run-id>/s1/` | `docs/`, story-service, `sources/`, Notion, Figma | `project.json`, `sources/index.json`, Notion 검토 사항 DB | `s1-context.json`, `sources.next/` | Read, Write, Glob, Grep, Notion 읽기, Figma 읽기 | prd-builder (PRD 부족 시) |
| Flow | `results/<run-id>/s2/` | `s1/`, story-service, `sources/`, Figma | `s1-context.json` | `s2-requirements.json` | Read, Write, Glob, Grep, Figma 읽기 | design-requirement-traceability |
| Component UX | `results/<run-id>/s3/` | `s1/`, `sources/`, Figma, `design.md`(있으면) | `s1-context.json` | `s3-components.json` | Read, Write, Glob, Grep, Figma 읽기 | — |
| Impact | `results/<run-id>/s4/` | `s1/`~`s3/`, `impact-map.json`, `sources/`, Figma | s1~s3 결과, `impact-map.json` | `s4-impact.json`, `impact-map.next.json` | Read, Write, Glob, Grep, Figma 읽기 | revision-impact-checker |
| Judge | **없음 (쓰기 도구 없음)** | `s1/`~`s4/`, `docs/`, story-service, `sources/` | s1~s4 결과 | 최종 메시지로 JSON 반환 → Orchestrator가 `s5/judge.json`으로 저장 | Read, Grep, Glob만 | — |

공통 금지:

- 자기 폴더 밖 쓰기 금지 (G5② 해시 검사와 Orchestrator 확인으로 강제)
- Notion 쓰기는 Orchestrator만. 사용자 칸(수정 완료·결정 메모)은 Orchestrator도 쓰지 않는다
- Figma 쓰기 도구(`use_figma`, `generate_*`, `upload_assets` 등) 사용 금지 — 검증 대상을 수정하지 않는다
- EXCLUDED 자료 읽기·인용 금지 (`sources/index.json` 확인)

## 3. 실행 순서·인계

| 순서 | 트리거 조건 | 실행 | 인계 방식 | 실패 처리 |
|---|---|---|---|---|
| 0 | 사용자 명령 | Orchestrator: G0 | — | G0 FAIL → 초기화 안내 |
| 1 | G0 PASS | Context | `s1/` 경로를 다음 에이전트 프롬프트에 전달 | G1 FAIL → Context 재실행 (2회 실패 시 사용자 질문) |
| 2 | G1 PASS → Orchestrator가 `sources.next/` 반영 | Flow, Component UX (병렬 가능) | `s2/`, `s3/` 경로 전달 | G2·G3 FAIL → 해당 에이전트 재실행 또는 S1 |
| 3 | G2·G3 PASS | Impact | `s4/` 경로 전달 | G4 FAIL → 재실행 또는 S1 |
| 4 | G4 PASS → Orchestrator가 `impact-map.next.json` 반영 | Judge | 반환 JSON을 Orchestrator가 `s5/judge.json`으로 저장 | — |
| 5 | Judge 완료 | Orchestrator: scripts로 최종 판정 계산(5절), DONE·GR·G5 검사, `report.md` 생성, Notion 반영, 커밋 | — | G5 FAIL → 해당 단계로 |
| 6 | — | H1: 사용자 결과 확인 | Notion | — |

## 4. 자연어 트리거

| 사용자 명령 (예시) | 동작 |
|---|---|
| "새 프로젝트 초기화: <프로젝트명>" | 초기화(B): `templates/project` 복사 → R1-A 절차로 story-service 작성 → H0 승인 대기 |
| "<프로젝트> UX 검증 시작" | 전체 검증 S1~S5 |
| "수정 후 재검증" / "<프로젝트> 다시 검증" | 전체 검증 (report에서 재검증 대상·판정 변화를 맨 앞에) |
| "변경된 화면의 영향 범위 분석" | 전체 검증 (report에서 S4 결과를 맨 앞에) |
| "수정 피드백: <내용>" / "<프로젝트> 이 피드백 반영하면 어디까지 봐야 해?" | 전체 검증 + 피드백 항목을 영향 분석 기점으로 추가 (pipeline §7). report에서 "피드백 영향 영역"을 맨 앞에 |
| "검증 재개" | `state.json` 기준 재개 (artifacts §6) |
| "검증 상태 알려줘" | `state.json`·최근 report 요약만 출력 (실행 안 함) |

## 5. Judge 이의 처리

- Judge 출력: 레코드별 `{id, agree: true|false, objection_reason, evidence_check}`
- 최종 판정(`s5/final.json`) = agree이면 원 판정 / 이의이면 `NEEDS_REVIEW` (`original_verdict` 보존, reason에 Judge 사유)
- Judge는 판정을 PASS 쪽으로 올릴 수 없다 (이의는 강등만 가능)
- 원 판정이 `FAIL`인 레코드는 이의가 있어도 `FAIL`을 유지한다 (강등 대상 아님). 필수 규칙(GR) 레코드도 동일
