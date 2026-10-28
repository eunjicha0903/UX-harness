# UX 검증 하네스

PRD·업무 자료와 Figma 화면을 대조해 요구사항 누락, 흐름·예외 문제, 컴포넌트 문제, 화면 간·플랫폼 간 영향, 근거 부족을 찾는다. 최종 결정은 디자이너가 한다.

이 파일은 진입점이다. 규칙은 아래 문서에만 있고, 여기에 다시 쓰지 않는다.

## 문서 지도

| 필요할 때 | 읽을 문서 |
|---|---|
| 판정값·실행 상태(승인/검토 필요)·해소 조건·DONE (공통 규칙 SSOT) | `docs/harness-goal.md` |
| 단계 S1~S5, 재실행, 화면 판별, 수정 피드백, 질문 금지 | `docs/pipeline.md` |
| 게이트 G0~G5·GR, 사람 승인 H0·H1 | `docs/gates.md` |
| 에이전트·편집 폴더·트리거·Judge 이의 | `docs/agents.md`, `.claude/agents/` |
| 실행 순서·초기화·보고 형식 | `docs/orchestrator.md` |
| 파일 위치·상태·재개·커밋 | `docs/artifacts.md` |
| 자료 상태값·자료 사용 원칙 | `docs/context-inventory.md` |
| 디자이너 업무 흐름 (공통·고정) | `docs/story-work.md` |
| 하네스 자체 검증 시나리오 | `docs/validation-plan.md` |
| 프로젝트 값 | `projects/<slug>/story-service.md`, `project.json` |

## 명령

| 사용자가 이렇게 말하면 | 할 일 |
|---|---|
| "새 프로젝트 초기화: <이름>" | orchestrator §2 |
| "<프로젝트> UX 검증 시작" / "다시 검증" | orchestrator §3 |
| "수정 피드백: <내용>" | orchestrator §3 + pipeline §7 |
| "검증 재개" | artifacts §6 |
| "검증 상태 알려줘" | `python3 scripts/harness.py status --slug <slug>` |

## 반드시 지킬 것

1. 검증 실행 중에는 사용자에게 묻지 않는다. 끝난 뒤 상태와, 미승인이면 이유를 보고한다.
2. 프로젝트 자료를 섞지 않는다. 지금 작업 중인 `projects/<slug>/`의 자료만 쓴다.
3. 근거 없이 PASS를 주지 않는다. 확인하지 않은 것을 확인했다고 말하지 않는다.
4. Figma에 쓰지 않는다. Notion의 사용자 칸(수정 완료·결정 메모)에 쓰지 않는다.
5. 공통 하네스 파일(`docs/`, `.claude/`, `scripts/`, `templates/`, `CLAUDE.md`)은 사용자 승인 없이 바꾸지 않는다. 프로젝트 차이는 `projects/<slug>/`에만 기록한다.
6. 커밋은 프로젝트 단위로 나눈다: `[<slug>] run <run-id>: <상태>`.
