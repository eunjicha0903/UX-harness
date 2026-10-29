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
| `notion/sync-<S1~S5>.json`, `notion/page-<S1~S5>-header.md`, `notion/page-<S1~S5>-section.md` | 매 단계 | Orchestrator (스크립트) | 단계별 Notion 반영 계획 (§11) | O |

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
| `review_case` | 검토 case (§10). 선택 필드 |
| `fix_platforms[]` | 수정 대상 플랫폼 (APP/WEB, 수정 불필요면 `[]`). 선택 필드이며 없으면 §10 규칙으로 추정한다 |
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
| 검토 사항(제목) | **`검토 case · 페이지 case`** (예: `오타 · 관리자웹 Professional 심사/심사 거절`). 페이지 case = 수정 대상 플랫폼 + 카테고리 + 프레임 TAG. 프레임 번호는 `프레임 번호` 칸에 작게, 전체 프레임 이름은 `화면 프레임` 칸에 둔다 (사용자 지시 2026-10-29) |
| 검토 case (공통) | `오타` / `명칭·문구` / `UI` / `로직` / `추가 고려사항` / `반영 확인` / `자료 확인`. 레코드 `review_case` → `s5/display-overrides.json` → 제목 키워드 추정 순서로 정한다. Notion `검토 case` 칸(이전 '검증 관점' 칸 대체). 핵심 검증 관점(Q1~Q3)은 보고서 '한눈에 보기'에만 쓴다 |
| 중복 미포함 (공통) | 같은 문제를 가리키는 항목은 보드에 한 번만 둔다. 대표 항목만 행으로 만들고, 중복 항목은 대표 행 `근거`에 '같은 문제'로 남긴 뒤 이미 만든 행은 휴지통으로 옮긴다(`archive`). 중복 판정 출처: S4 FAIL 기점 단위, Judge `duplicates[]`·이의 사유, `s5/display-overrides.json` `duplicates` |
| 판정 | 한국어: 승인 / 검토 필요 (harness-goal 5-1 표). 판정 유형: 문제 확인 / 사람 판단 필요 / 자료 부족 |
| 설명·근거·영향 화면·후속 조치 | 모든 화면 언급은 **프레임 이름**으로 쓴다. 화면 ID(`APP-33`)와 노드 ID(`36:19883`)는 프레임 이름으로 바꿔 표시한다. 문서 근거는 자료 이름과 절을 쓴다 |
| 카테고리 | Figma **TAG 프레임** 기준. 프레임 위쪽에서 가로로 겹치는 TAG 중 구역 제목 TAG(같은 플랫폼 프레임 태그보다 1.4배 이상 높은 TAG, 세로로 긴 플랫폼 표지는 제외) 가운데 가장 가까운 것 = 카테고리, 프레임 바로 위(400px 이내) 일반 TAG = 프레임 태그 |

| 핵심 검증 관점 (**공통**) | 모든 프로젝트 공통 기본 관점: **Q1 수정사항 반영** — 관리자웹 수정사항을 제대로 반영했는가 / **Q2 앱 크로스 체크** — 사용자앱(모바일)과 크로스 체크했을 때 연결이 잘 되는가 (story-service 허용 플랫폼에 사용자앱·관리자웹이 모두 있을 때만) / **Q3 고려 못한 사항** — 고려하지 못한 사항이 있는가 (기본, 어느 관점에도 안 맞는 항목). `project.json` `report.focus`가 비어 있으면 이 기본값을 쓰고, 값이 있으면 그 프로젝트만 덮어쓴다 (사용자 지시 2026-10-28). 보고서 맨 앞에 **"한눈에 보기"**를 둔다. 질문마다 결론 한 줄(✅ 문제 없음 / ⚠ 검토 필요 N건) → 해당 프레임과 한 줄 요약(최대 8개) 순서로 두괄식으로 쓴다. 레코드의 `focus` 필드(Q1 등)로 분류하고, 없으면 `default` 질문에 넣는다. Notion DB에는 "검증 관점" 칸으로 표시한다 |
| 플랫폼 분류 (공통) | 검토 사항은 **수정 대상 플랫폼**(사용자앱 / 관리자웹)으로 나눈다. 사용자앱 줄에는 사용자앱을 고쳐야 하는 항목만, 관리자웹 줄에는 관리자웹을 고쳐야 하는 항목만 보인다 (양쪽 다 고쳐야 하면 두 줄 모두). 판별 순서: ① 레코드 `fix_platforms` ② 후속 조치가 '조치 없음'이면 없음 ③ 후속 조치에 적힌 화면의 플랫폼 ④ 항목 프레임이 가장 많은 플랫폼(같으면 모두). 카테고리도 수정 대상 플랫폼 프레임으로 정하고, 다른 플랫폼 프레임은 제목 뒤쪽과 영향 화면에 남는다. 수정 대상이 없는 항목은 `전체 공통`. report는 플랫폼 → 카테고리 순으로 묶고, Notion 기본 보기는 보드형으로 열 = 카테고리, 가로 묶음(sub group) = 플랫폼이다 |
| 보드 = to do (공통) | 기본 보기 `검토 중`(보드)은 할 일 목록이다. **판정 = 승인**이거나 **수정 완료 체크**(to do 완료)면 보드에서 빠지고, 기록은 지우지 않고 `완료`(같은 구성의 보드) 보기에 모인다. 수정 완료 후 재검증에서 여전히 FAIL이면 보드에 다시 나타난다. 항목은 수정 대상 플랫폼 줄에만 보인다. Notion 칸 `판정 유형`은 두지 않고, `항목 ID`·`정렬 순서`는 페이지에서 숨긴다(하네스 매칭·정렬용으로 유지) |
| 프레임 번호 | Figma 프레임 이름 번호만 따로 적는다 (예: `03, 04, 26`), 제목과 같은 순서 |
| 검토 사항 정렬 | 화면 프레임 **번호 오름차순**(01부터, 위→아래). 같은 번호는 `project.json` platforms 순서. 여러 프레임이면 가장 작은 번호 기준이고, 제목 안 프레임도 번호 순으로 나열한다. Notion DB는 "정렬 순서" 칸(번호×10 + 플랫폼 순서) 오름차순 보기로 표시하고, report 표도 같은 순서로 쓴다 (사용자 지시 2026-10-28) |
| 프레임 이름이 숫자뿐인 경우 | `플랫폼 번호 · 프레임 TAG` 형태로 표시한다 (예: `관리자웹 28 · 포럼 관리`) |

변환은 `scripts/harness.py`가 `s1-context.json`의 프레임 목록과 `project.json`의 `figma.metadata_file`로 수행한다. 내부 JSON은 화면 ID·노드 ID를 그대로 유지한다.

## 11. 단계별 Notion 반영 (사용자 지시 2026-10-28)

결과를 S5까지 모아 한 번에 올리지 않는다. **단계가 끝나 게이트를 통과할 때마다** 그 단계에서 나온 내용을 바로 Notion에 반영하고, 뒤 단계에서 바뀐 내용은 같은 행·같은 페이지를 갱신한다.

| 단계 | 실행 결과 페이지 | 검토 사항 DB (항목 ID 기준 upsert. 사용자가 휴지통으로 옮긴 행은 `display-overrides.json` `user_removed`에 기록하고 다시 만들지 않는다) |
|---|---|---|
| S1 | `UX 검증 결과 <run-id> · 진행 중` 페이지 생성, 맨 위 진행 상황 + 검증 대상 요약 | 없음 |
| S2 / S3 | 맨 위 진행 상황 교체, 단계 섹션 추가 (관점별 잠정 결과 두괄식) | 미해소 레코드 생성·갱신, 단계 칸으로 구분 |
| S4 | 맨 위 교체, 피드백·기점별 영향 섹션 추가 | 기점 행의 영향 화면·후속 조치 갱신(update_only), 새 레코드 생성, 단계 칸으로 구분 |
| S5 | 페이지 제목 `· <상태>`로 변경, 맨 위를 결론·한눈에 보기·필수 규칙 위반으로 교체, Judge 변경 섹션 추가 | 최종 판정으로 갱신, 중복은 archive / 해소된 항목은 판정 = 승인, 재검증 결과 = PASS |

- 계획은 `python3 scripts/harness.py notion-sync --slug <slug> --run <run> --stage <S1~S5>`가 `results/<run>/notion/`에 만든다. Orchestrator는 계획대로만 Notion MCP로 쓴다 (`upsert`: 같은 항목 ID 행이 있으면 갱신·없으면 생성, `update_only`: 있는 행만 갱신).
- 하네스 칸만 쓴다. 사용자 칸(수정 완료·결정 메모)은 스크립트가 계획에 넣지 않으며 넣으면 오류로 멈춘다.
- 단계 반영이 실패해도 실행은 멈추지 않는다. 실패한 계획은 `notion-pending.json`에 적재하고 다음 단계 반영 때 먼저 재전송한다. G5 ④는 S5 계획까지 반영됐거나 pending에 적재됐는지를 본다.

## 9. Notion 연동 실패

| 상황 | 처리 |
|---|---|
| S1 읽기 실패 | 사용자 입력 없음으로 진행. 이번 실행의 해소 인정 0건. `report.md` 상단 경고 |
| 단계별(S1~S5) 쓰기 실패 | 로컬 결과 확정, `notion-pending.json`에 적재, 다음 실행 S5에서 재전송. 실행 상태는 바뀌지 않음 |
