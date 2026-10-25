# Context Inventory (R0)

- 작성일: 2026-10-25
- 상태: CONFIRMED v4 (사용자 승인 2026-10-25)
- 범위: 공통 하네스 설계용 환경·자료 목록. 프로젝트별 상세 맥락은 `projects/<slug>/`에서 관리한다.
- 시범 프로젝트: 이너베러(무인배달플랫폼)(커머스) → slug: `innerbetter`

## 1. 확인 상태 정의

| 값 | 의미 |
|---|---|
| FETCHED | 본문(또는 화면 스크린샷)을 직접 열어 확인함 |
| SEARCH_ONLY | 검색 결과(제목/경로/요약)만 확인, 본문 미확인 |
| BLOCKED | 접근 권한 없음 |
| NOT_FOUND | 탐색했으나 없음 |
| EXCLUDED | 다른 프로젝트 자료이거나 사용자가 근거에서 제외함 |

## 2. 저장 구조

```
/home/user/ux-harness/            ← git 저장소 (원격 저장소는 R8 전에 연결)
├── CLAUDE.md, docs/, scripts/, .claude/agents/   ← 공통 하네스
└── projects/innerbetter/
    ├── story-service.md                          ← R1-A
    ├── sources/   (Notion·Figma 스냅샷, 확인 상태 기록)
    └── results/   (검증 결과)
```

## 3. 자료 처리 원칙

1. 원본은 Notion에 둔다. 검증할 때는 `sources/`에 스냅샷을 저장하고 URL·확인 날짜·상태를 함께 기록한다. 판정은 스냅샷을 기준으로 한다.
2. Figma는 읽을 수 있는 파일 URL이 있을 때만 쓴다. 없으면 디자인 근거는 `INSUFFICIENT_INFO`로 둔다.
3. 복제본 Figma는 원본 URL과 복제일을 기록한다. 원본과 차이가 의심되는 근거는 `NEEDS_REVIEW`로 둔다.
4. Figma 파일에서 근거로 쓸 페이지는 사용자가 지정한 범위로 한정한다(이너베러: `concept` 페이지만).
5. 기존 스킬(prd-builder, revision-impact-checker, qa-tc-sheet, design-requirement-traceability, feature-spec-sheet)은 작업 에이전트가 호출하는 부품으로 재사용한다. 스킬 결과는 Judge가 판정할 대상이다.

## 4. 로컬 작업 공간 (R0 시점)

- `/home/user`: 비어 있었음. `docs/`, `CLAUDE.md`, `story-service.md`, `story-work.md`, `design.md`, PRD 모두 NOT_FOUND.
- 클라우드 컨테이너라 세션이 끝나면 파일이 사라질 수 있어 git push가 필요하다.

## 5. 도구

| 도구 | 상태 | 비고 |
|---|---|---|
| Notion MCP | 연결됨 | 워크스페이스: 은지 차님의 워크스페이스 |
| Figma MCP | 연결됨 (개인 계정) | 회사 소유 원본 파일은 BLOCKED. 스크린샷은 base64 응답으로만 수신 가능 (figma.com 직접 다운로드는 네트워크 정책상 차단) |

## 6. 이너베러 자료

| ID | 자료 | 플랫폼 | 상태 | 성격 |
|---|---|---|---|---|
| SRC-00 | 사용자앱 PRD (사용자 제공 원문, 2026-10-25) → `projects/innerbetter/sources/prd-user-app.md` | 앱 | FETCHED | **사용자앱 1차 기준** |
| SRC-01 | 사용자앱 PRD v1.0 (Notion 39dcd783cd418139a482cb0f782f8b91, 2026-07-14) | 앱 | FETCHED | 보조. SRC-00에 없는 항목만 참고 |
| SRC-02 | 프로젝트 페이지 (Notion 325cd783cd4180308454c8dca3d4d44e) | 공통 | FETCHED (외부 블록 2개 미확인) | 기획 메모. 참고 의견과 확정 사항이 섞여 있음 |
| SRC-03 | RV (Notion 351cd783cd418009882cd487cbd06ae0) | 공통 | FETCHED | 회고. 배달시간 규칙, 플랫폼별 목표 |
| SRC-04 | 사용자앱 기능정의서 .xlsx (SRC-02 첨부) | 앱 | SEARCH_ONLY | 원본 미열람 |
| SRC-05 | QA-TC 앱 (메인·로그인회원가입·마이·장바구니주문결제) | 앱 | SEARCH_ONLY | |
| SRC-06 | QA-TC 웹 (Notion 39ecd783cd4181a28212c8568b82c28f) | 관리자웹 | FETCHED | 화면 7개 목록. 로그인 외 TC 비어 있음 |
| SRC-07 | Figma 원본 「이너베러 (개발)」 ZwcWEllvBjbgK6ZYO16PKT | 앱+웹 | BLOCKED | 회사 계정 소유 |
| SRC-08 | 관리자웹 기능정의서 | 관리자웹 | NOT_FOUND | |
| SRC-09 | 관리자웹 PRD 초안 v0.1 → `projects/innerbetter/sources/prd-admin-web.md` | 관리자웹 | 작성됨 (사용자 승인) | SRC-10 기반 |
| SRC-10 | Figma 복제본 「디자인 하네스 실험」 wsd2HEsLTV74mUSucqjHVF, `concept` 페이지(18:2) | 앱+웹 | FETCHED (관리자웹 프레임 27/34개 스크린샷, 앱 프레임은 레이어 목록만) | 개인 계정 복제본. 원본: SRC-07, 복제일 미확인 |

### 자료 우선순위 (사용자앱)

SRC-00 > SRC-01 > SRC-02/03(기획 메모·회고). 우선순위가 낮은 자료가 높은 자료와 충돌하면 덮어쓰지 않고 CF로 남긴다.

### 제외 자료 (EXCLUDED)

| 자료 | 사유 |
|---|---|
| SRC-10의 `screens` 페이지(23:29) 전체 (`cart/*`, `home/default`, `key/*`, `concept/components`, `concept/tokens`) | 사용자 지시: concept 페이지만 근거로 사용 |
| work/Today To-do "관리자웹 수정사항 정리"(401cd783…), "관리자웹 수정"(402cd783…) | 뉴스·포럼·Professional 심사·신고 관리 등 커뮤니티 서비스 내용. MARU 자료로 추정. 프로젝트 속성 비어 있음 |
| 엠투피, MARU, SK엠앤서비스, 화이트짐, little my home 자료 일체 | 다른 고객사 |

## 7. 자료 간 충돌 (임의로 선택하지 않음)

| ID | 내용 | 출처 | 상태 |
|---|---|---|---|
| CF-01 | 배송 슬롯 "오후 5시 이전 주문→당일 6~9시"(예시값) vs "시작+3h, 마감은 시작−1h 자동 계산" | SRC-01 §12, SRC-03, SRC-10 지점관리 | NEEDS_REVIEW |
| CF-02 | 마일리지: "적립형X, 다음 주문 시 200원? 자동차감"(SRC-02) vs "결제 후 N% 자동 적립"(SRC-01) vs 주문 상세 "마일리지 −200원 / 적립예정 200원"(SRC-10) | SRC-01/02/10 | NEEDS_REVIEW |
| CF-03 | 홈 구조: 클라이언트 요청 "배민형 홈" vs 채택안 "상품 진입 중심형 홈". SRC-00은 채택안을 따름 | SRC-02, SRC-00 | NEEDS_REVIEW (클라이언트 최종 컨펌 근거 미확인) |
| CF-04 | 배송/취소 마감: "고정 정책"(SRC-00) vs "관리자 커스텀"(SRC-01). SRC-10 지점관리는 관리자가 배송 시작 시각만 입력하고 마감은 −1h 자동 계산(수정 불가) → "고정 오프셋"으로 해석 가능 | SRC-00/01/03/10 | NEEDS_REVIEW |
| CF-05 | 배송 상태: 3단계(SRC-00) vs 4단계 주문취소 포함(SRC-01). SRC-10 관리자 목록에 "결제취소" 표시, 상태 변경 모달은 3단계만 | SRC-00/01/10 | NEEDS_REVIEW |
| CF-06 | 로그인·회원가입·검색·배달불가지역·품절의 범위 포함 여부: SRC-00에 없음 vs SRC-01·SRC-10에 화면 존재(관리자웹 "오픈 요청 지역", "소셜 로그인" 컬럼 포함) | SRC-00/01/10 | NEEDS_REVIEW |

## 8. 미확인·추가 필요 항목

| ID | 항목 | 상태 | 필요한 조치 |
|---|---|---|---|
| GAP-01 | Figma 원본 접근 | 우회 (SRC-10 복제본) | 복제일 기록 필요 |
| GAP-02 | 관리자웹 기능정의서 | NOT_FOUND | 있으면 제공 |
| GAP-03 | 사용자앱 PRD 기준본 | 해소 (SRC-00) | |
| GAP-04 | 프로젝트 페이지 외부 블록 2개 | 미확인 | 무엇인지 사용자 확인 |
| GAP-05 | 디자인 시스템 / design.md | NOT_FOUND | 필요 시 SRC-10 concept 페이지 `컴포넌트` 프레임에서 추출 |
| GAP-06 | 원격 git 저장소 | 미정 | R8 전에 연결 |
| GAP-07 | SRC-10 관리자웹 미확인 프레임 7개 | 변형 화면으로 판단해 생략 | 필요 시 추가 확인 |

## 9. 자료 사용 규칙 (R0 확정분, 게이트는 R5에서 확정)

1. 판정 근거는 FETCHED 자료만 쓴다. SEARCH_ONLY·BLOCKED 자료에 기댄 판정은 `INSUFFICIENT_INFO`로 둔다.
2. EXCLUDED 자료를 인용하면 `FAIL`이다.
3. 자료 간 충돌(CF-*)은 해소되기 전까지 `NEEDS_REVIEW`로 둔다.
