# Artifacts & State (R4)

- 상태: CONFIRMED (사용자 승인 2026-10-25)
- 공통 하네스 문서. 규칙은 다시 쓰지 않고 ID로만 참조한다 (공통 규칙 SSOT: `docs/harness-goal.md`).

## 1. 공통 하네스 파일 (프로젝트와 무관, 한 번 정의)

| 경로 | 역할 | 수정 |
|---|---|---|
| `CLAUDE.md` | 진입점. 상세 규칙은 `docs/` 참조만 | 공통 변경 시 사용자 승인 |
| `docs/context-inventory.md` | R0 환경·자료 원칙 (자료 상태값 정의) | 〃 |
| `docs/story-work.md` | 공통 업무 흐름 (고정) | 〃 |
| `docs/harness-goal.md` | **공통 규칙 SSOT** (판정값·실행 상태·해소 조건·DONE-01~10) | 〃 |
| `docs/pipeline.md` | S1~S5, 재실행, 화면 판별 기본 규칙 | 〃 |
| `docs/artifacts.md` | 이 문서 | 〃 |
| `docs/gates.md`, `agents.md`, `orchestrator.md`, `validation-plan.md` | R5~R8 | 〃 |
| `scripts/` | 게이트·판정·초기화 스크립트 | 〃 |
| `.claude/agents/` | 에이전트 정의 | 〃 |
| `templates/project/` | 새 프로젝트 초기화 템플릿 (`story-service.md`, `project.json`, `story-work-exceptions.md`, `sources/index.json`) | 〃 |

## 2. 프로젝트 인스턴스 파일 (`projects/<slug>/`)

새 프로젝트는 `templates/project/`를 `projects/<slug>/`로 복사해 시작한다. 프로젝트끼리 파일을 공유하지 않는다.

| 경로 | 역할 | 쓰는 주체 |
|---|---|---|
| `story-service.md` | 서비스 맥락·필수 규칙(프로젝트 값)·플랫폼 허용 목록·검증 범위·화면 판별 재지정 | 사용자 승인 후 하네스 |
| `story-work-exceptions.md` | 공통 흐름과 다른 점 (있을 때만) | 〃 |
| `project.json` | 기계 설정: slug, Figma fileKey·페이지 ID, Notion 검토 사항 data_source ID, 플랫폼 판별 폭 | 초기화 시 생성 |
| `sources/` | 자료 스냅샷 (PRD 원문, Notion 본문, Figma 메타·스크린샷 목록) | Orchestrator (G1 통과 후 `s1/sources.next/` 반영) |
| `sources/index.json` | 자료 ID·상태·URL·확인일·해시, 자료 충돌(`conflicts`) | 〃 |
| `impact-map.json` | 누적 영향 맵 (화면·컴포넌트·데이터·정책·플랫폼 간 연결 + 근거) | Orchestrator (G4 통과 후 `s4/impact-map.next.json` 반영, 실행 간 유지) |
| `state.json` | 현재 실행 상태 (재개용) | Orchestrator |
| `notion-pending.json` | Notion에 못 보낸 변경분 (있을 때만) | S5 |
| `results/<run-id>/` | 실행별 결과 (3절) | 각 단계 |

run-id 형식: `YYYYMMDD-HHMM` (예: `20261025-1530`)

## 3. 실행별 산출물 (`results/<run-id>/`)

단계별 하위 폴더로 나눈다. 각 에이전트는 자기 단계 폴더에만 쓴다 (R6 agents.md §2).

| 파일 | 단계 | 쓰는 주체 | 내용 | 필수 |
|---|---|---|---|---|
| `s1/s1-context.json` | S1 | Context | 사용한 자료와 상태, REQ 목록, 화면 목록, 변경점, 재검증 대상 (Notion 입력 스냅샷 포함) | O |
| `s1/sources.next/` | S1 | Context | `sources/` 갱신 후보 (index.json 포함). G1 통과 후 Orchestrator가 반영 | O |
| `s2/s2-requirements.json` | S2 | Flow | REQ·흐름·상태·예외·필수 규칙 조건별 판정 | O |
| `s3/s3-components.json` | S3 | Component UX | 컴포넌트별 판정 | O |
| `s4/s4-impact.json` | S4 | Impact | 분석 단위별 7개 항목, 연결 화면별 판정 | O |
| `s4/impact-map.next.json` | S4 | Impact | `impact-map.json` 갱신 후보. G4 통과 후 Orchestrator가 반영 | O |
| `s5/judge.json` | S5 | Orchestrator (Judge 반환값 저장) | 레코드별 동의·이의 | O |
| `s5/final.json` | S5 | Orchestrator (스크립트) | 최종 판정 (Judge 이의 반영, 원 판정 보존) | O |
| `s5/s5-judgement.json` | S5 | Orchestrator (스크립트) | DONE-01~10·GR 결과, 실행 상태, 미해소 항목 상세 사유 | O |
| `s5/report.md` | S5 | Orchestrator (스크립트) | 사람이 읽는 보고서 (JSON에서 생성, 직접 편집 금지) | O |
| `s5/diff.json` | S5 | Orchestrator (스크립트) | 이전 실행 대비 항목별 판정 변화 | 2회차부터 O |

### 공통 항목 레코드 (s2~s4의 모든 항목)

| 필드 | 설명 |
|---|---|
| `id` | 실행 간 유지되는 ID (예: `CHK-S2-014`) |
| `title` | 한 줄 요약 |
| `stage` | S2 / S3 / S4 |
| `platform[]` | story-service 허용 목록 값 |
| `screen_ids[]`, `figma_node_ids[]` | 대상 화면 |
| `rule_ref` | 필수 규칙 조건 ID (예: `1-a`) 또는 null |
| `verdict` | `PASS` / `FAIL` / `NEEDS_REVIEW` / `INSUFFICIENT_INFO` |
| `evidence[]` | `{source_id, locator}` (locator: 섹션 또는 Figma 노드 ID) |
| `reason` | 판정 사유 |
| `impact_screens[]` | 영향 화면 |
| `follow_up` | 후속 조치 |
| `prev_verdict` | 이전 실행 판정 (없으면 null) |

### 단계별 JSON 형식 (scripts/harness.py가 검사하는 필드)

| 파일 | 최상위 필드 |
|---|---|
| `s1-context.json` | `run_id`, `requirements[] {id, title, source_id, locator}`, `screens[] {id(APP-01 등), platform, number, name, frames[] {name, node_id, width, height}, overrides[]}`, `platform_gaps[] {platform, reason}`, `excluded_requests[] {request, reason}`, `excluded_sources[] {source, reason}`, `changes[] {id, target, detail}`, `recheck_targets[]`(항목 ID), `notion_read`(ok/failed), `notion_inputs[] {item_id, page_url, 수정 완료, 컨펌 완료, 결정 메모}`, `feedback[] {id, text, targets[], change, figma_reflected, verdict?}` |
| `s2-requirements.json` | `records[]` (공통 항목 레코드 + `req_refs[]`) |
| `s3-components.json` | `components[] {id, name, node_id, used_in[]}`, `records[]` (공통 항목 레코드 + `component_refs[]`). `design.md`가 없으면 `id: CHK-S3-GUIDE` INSUFFICIENT_INFO 레코드 1건 |
| `s4-impact.json` | `units[] {id, origin {type: change/fail/recheck/feedback, ref}, origin_screens[], change_target, related_screens[] {screen_id, platform, decision, reason}, relation_evidence[] {source_id, locator}, expected_problem, needs_fix, verdict, follow_up, consider_areas[]?, rule_ref?}`, `records[]` |
| `impact-map(.next).json` | `edges[] {from, to, type, evidence}` (화면 ID 기준) |
| `judge.json` | `records[] {id, agree, objection_reason, evidence_check}`, `missing_coverage[]` |

## 4. SSOT와 사본의 관계

| 정보 | SSOT | 사본·창구 | 충돌 시 |
|---|---|---|---|
| 공통 판정 규칙 | `docs/harness-goal.md` | 다른 문서는 ID로만 참조 | SSOT 기준 |
| 프로젝트 규칙 | `projects/<slug>/story-service.md` (프로젝트 값) | — | — |
| 항목 판정 결과 | `results/<run-id>/s*.json` | Notion 검토 사항 DB (미해소 항목 미러) | 로컬 JSON 기준 |
| **실행 결과 보고서 (사용자 최종 산출물)** | Notion `업무 도우미 / UX검토 / <프로젝트>` 아래 실행 결과 페이지 (`UX 검증 결과 <run-id> · <상태>`) | `s5/report.md` (같은 내용, git 기록용) | 둘 다 같은 report.md에서 생성 |
| 사용자 결정 (수정 완료·컨펌·메모) | Notion 검토 사항 DB | `s1-context.json`에 실행 시점 스냅샷 | Notion 기준 |
| 영향 관계 | `projects/<slug>/impact-map.json` | `s4-impact.json` (실행 시점) | impact-map 기준 |

스크립트는 `harness-goal.md`와 `story-service.md`의 표를 ID(`DONE-01`, `1-a` 등)로 직접 읽는다. 표 형식이 깨지면 스크립트가 실패하며, 이 형식 검사를 게이트로 둔다 (R5).

## 5. 상태 기록 (`state.json`)

```json
{
  "slug": "innerbetter",
  "run_id": "20261025-1530",
  "started_at": "...",
  "current_stage": "S3",
  "completed_stages": ["S1", "S2"],
  "stage_outputs": { "S1": ["s1-context.json"], "S2": ["s2-requirements.json"] },
  "source_hashes": { "SRC-00": "..." },
  "last_status": null,
  "last_error": null
}
```

## 6. 중단 후 재개

1. `state.json`의 run_id가 S5 완료 전이면 "재개 가능"으로 본다.
2. `completed_stages`의 마지막 단계 산출물이 존재하고 게이트를 통과하는지 다시 검사한다.
3. `sources/index.json` 해시와 현재 자료 해시를 비교한다. 바뀌었으면 재개하지 않고 새 run-id로 S1부터 시작한다.
4. 바뀌지 않았으면 다음 단계부터 이어서 실행한다.

## 7. 저장 (커밋)

- S5가 끝날 때마다 해당 프로젝트만 자동 커밋한다. 커밋 대상은 `projects/<slug>/` 아래 파일로 한정한다.
- 커밋 메시지: `[<slug>] run <run-id>: <승인|검토 필요>`
- 원격 저장소를 연결한 뒤부터는 push까지 한다 (R8 전 연결).
- 공통 하네스 파일 변경은 프로젝트 실행 커밋에 섞지 않고 별도 커밋으로 한다.

## 8. 미해결 항목 기록

- 미해소 항목은 `s5-judgement.json`에 상세 사유 5개 필드(무엇이·왜·근거·영향 화면·후속 조치)와 함께 기록하고, Notion 검토 사항 DB에 미러링한다.
- 자료 충돌(CF-*)은 각 프로젝트의 `sources/index.json` `conflicts`에 기록한다. 공통 문서에는 쓰지 않는다.
- 이너베러 CF-01~06은 R0 당시 `docs/context-inventory.md`에 기록돼 있으므로 프로젝트 초기화 시 이관하고, inventory에는 "이관됨" 표시만 남긴다.

## 10. 사용자 표시 규칙 (Notion·report, 사용자 지시 2026-10-28)

| 항목 | 규칙 |
|---|---|
| 검토 사항(제목) | 해당 항목의 **화면 프레임 이름**. 여러 프레임이면 쉼표로 나열한다 |
| 판정 | 한국어: 승인 / 검토 필요 (harness-goal 5-1 표). 판정 유형: 문제 확인 / 사람 판단 필요 / 자료 부족 |
| 설명·근거·영향 화면·후속 조치 | 모든 화면 언급은 **프레임 이름**으로 쓴다. 화면 ID(`APP-33`)와 노드 ID(`36:19883`)는 프레임 이름으로 바꿔 표시한다. 문서 근거는 자료 이름과 절을 쓴다 |
| 카테고리 | Figma **TAG 프레임** 기준. 프레임 위쪽에서 가로로 겹치는 TAG 중 구역 제목 TAG(같은 플랫폼 프레임 태그보다 1.4배 이상 높은 TAG, 세로로 긴 플랫폼 표지는 제외) 가운데 가장 가까운 것 = 카테고리, 프레임 바로 위(400px 이내) 일반 TAG = 프레임 태그 |

| 핵심 검증 관점 (선택) | `project.json`의 `report.focus`에 질문이 있으면 보고서 맨 앞에 **"한눈에 보기"**를 둔다. 질문마다 결론 한 줄(✅ 문제 없음 / ⚠ 검토 필요 N건) → 해당 프레임과 한 줄 요약(최대 8개) 순서로 두괄식으로 쓴다. 레코드의 `focus` 필드(Q1 등)로 분류하고, 없으면 `default` 질문에 넣는다. Notion DB에는 "검증 관점" 칸으로 표시한다 |
| 프레임 이름이 숫자뿐인 경우 | `플랫폼 번호 · 프레임 TAG` 형태로 표시한다 (예: `관리자웹 28 · 포럼 관리`) |

변환은 `scripts/harness.py`가 `s1-context.json`의 프레임 목록과 `project.json`의 `figma.metadata_file`로 수행한다. 내부 JSON은 화면 ID·노드 ID를 그대로 유지한다.

## 9. Notion 연동 실패

| 상황 | 처리 |
|---|---|
| S1 읽기 실패 | 사용자 입력 없음으로 진행. 이번 실행의 해소 인정 0건. `report.md` 상단 경고 |
| S5 쓰기 실패 | 로컬 결과 확정, `notion-pending.json`에 적재, 다음 실행 S5에서 재전송. 실행 상태는 바뀌지 않음 |
