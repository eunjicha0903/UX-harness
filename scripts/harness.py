#!/usr/bin/env python3
"""UX 검증 하네스 게이트·판정 스크립트 (Python 3 표준 라이브러리만 사용).

규칙의 기준 문서(SSOT)는 docs/harness-goal.md 와 projects/<slug>/story-service.md 이다.
이 스크립트는 두 문서의 표를 ID로 읽고, 규칙 문장을 따로 복제하지 않는다.

하위 명령:
  init <slug>                         templates/project 복사
  state start|done|fail ...           state.json 기록
  promote --slug --run --what sources|impact-map
  hash --slug --run                   Judge 실행 전 s1~s4 해시 기록
  gate <G0|G1|G2|G3|G4|G5|GR> --slug --run
  finalize --slug --run               final·s5-judgement·report·diff 생성
  notion-sync --slug --run            Notion 반영 계획(notion-sync.json) 생성
  notion-result --slug --run --ok|--failed   Notion 반영 결과 기록
  status --slug
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERDICTS = ["PASS", "FAIL", "NEEDS_REVIEW", "INSUFFICIENT_INFO"]
UNRESOLVED = {"FAIL", "NEEDS_REVIEW", "INSUFFICIENT_INFO"}
SRC_STATUSES = ["FETCHED", "SEARCH_ONLY", "BLOCKED", "NOT_FOUND", "EXCLUDED"]
DECISIONS = ["수정 필요", "수정 불필요", "추가 확인 필요"]
STAGE_LABEL = {"S2": "S2 요구사항·흐름", "S3": "S3 컴포넌트", "S4": "S4 영향 분석"}
USER_FIELDS = {"수정 완료", "결정 메모", "컨펌 완료", "승인 완료"}   # 사용자 칸(뒤 둘은 이전 이름, 쓰기 금지 유지)
UNIT_FIELDS = ["change_target", "related_screens", "relation_evidence",
               "expected_problem", "needs_fix", "verdict", "follow_up"]
RECORD_FIELDS = ["id", "title", "stage", "platform", "screen_ids", "verdict",
                 "evidence", "reason", "follow_up"]


# ---------- 공통 ----------

def now():
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def proj(slug):
    return ROOT / "projects" / slug


def run_dir(slug, run):
    return proj(slug) / "results" / run


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dir_hash(path):
    h = hashlib.sha256()
    for p in sorted(Path(path).rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(path)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


class Gate:
    def __init__(self, name):
        self.name = name
        self.errors = []

    def check(self, ok, msg):
        if not ok:
            self.errors.append(msg)
        return ok

    def report(self):
        status = "PASS" if not self.errors else "FAIL"
        print(f"{self.name}: {status}")
        for e in self.errors:
            print(f"  - {e}")
        return 0 if not self.errors else 1


# ---------- SSOT 읽기 ----------

def read_goal():
    """harness-goal.md에서 판정값과 DONE ID를 읽는다."""
    text = (ROOT / "docs" / "harness-goal.md").read_text(encoding="utf-8")
    done_ids = re.findall(r"^\|\s*(DONE-\d\d)\s*\|", text, re.M)
    verdicts = [v for v in VERDICTS if f"`{v}`" in text]
    return {"done_ids": done_ids, "verdicts": verdicts}


def read_service(slug):
    """story-service.md에서 H0 기록, 플랫폼 허용 목록, 검증 범위, 규칙 조건 ID를 읽는다."""
    text = (proj(slug) / "story-service.md").read_text(encoding="utf-8")
    approved = re.search(r"approved_at:\s*(\d{4}-\d{2}-\d{2})", text)
    sec_a = re.search(r"^### A\..*?(?=^### )", text, re.M | re.S)
    allowed_labels = []
    if sec_a:
        for row in re.findall(r"^\|\s*([^|]+?)\s*\|\s*([OX])\s*\|", sec_a.group(0), re.M):
            if row[1] == "O":
                allowed_labels.append(row[0])
    sec_d = re.search(r"^### D\..*?(?=^### |\Z)", text, re.M | re.S)
    rule_ids = re.findall(r"^- (\d+-[a-z]) ", sec_d.group(0), re.M) if sec_d else []
    return {
        "approved_at": approved.group(1) if approved else None,
        "allowed_labels": allowed_labels,
        "has_scope": bool(re.search(r"^### C\.", text, re.M)),
        "rule_ids": rule_ids,
    }


def allowed_codes(slug):
    cfg = load(proj(slug) / "project.json", {})
    labels = read_service(slug)["allowed_labels"]
    codes = []
    for p in cfg.get("platforms", []):
        if any(lbl.startswith(p["label"]) for lbl in labels):
            codes.append(p["code"])
    return codes


def source_index(slug, run):
    nxt = run_dir(slug, run) / "s1" / "sources.next" / "index.json"
    return load(nxt) or load(proj(slug) / "sources" / "index.json", {"sources": []})


def source_status(slug, run):
    idx = source_index(slug, run)
    st = {s["id"]: s.get("status") for s in idx.get("sources", [])}
    s1 = load(run_dir(slug, run) / "s1" / "s1-context.json", {}) or {}
    for fb in s1.get("feedback", []):
        st[fb["id"]] = "FETCHED"   # 사용자 제공 피드백 원문
    st.setdefault("FB", "FETCHED")
    return st


def stage_records(slug, run):
    rd = run_dir(slug, run)
    out = []
    for stage, rel in (("S2", "s2/s2-requirements.json"), ("S3", "s3/s3-components.json"),
                       ("S4", "s4/s4-impact.json")):
        data = load(rd / rel, {}) or {}
        for r in data.get("records", []):
            r.setdefault("stage", stage)
            out.append(r)
    return out


def impact_units(slug, run):
    data = load(run_dir(slug, run) / "s4" / "s4-impact.json", {}) or {}
    return data.get("units", [])


def unit_as_record(u):
    screens = [s.get("screen_id") for s in u.get("related_screens", [])]
    return {
        "id": u.get("id"), "title": u.get("change_target"), "stage": "S4",
        "platform": sorted({s.get("platform") for s in u.get("related_screens", []) if s.get("platform")}),
        "screen_ids": u.get("origin_screens", []), "figma_node_ids": [],
        "rule_ref": u.get("rule_ref"), "verdict": u.get("verdict"),
        "evidence": u.get("relation_evidence", []), "reason": u.get("expected_problem"),
        "impact_screens": [s for s, d in zip(screens, u.get("related_screens", []))
                           if d.get("decision") != "수정 불필요"],
        "follow_up": u.get("follow_up"), "prev_verdict": u.get("prev_verdict"),
        "unit": True,
    }


def record_errors(r):
    errs = []
    for k in RECORD_FIELDS:
        v = r.get(k)
        if v is None or v == "" or (k == "evidence" and not v):
            errs.append(f"{r.get('id', '?')}: 필드 '{k}' 비어 있음")
    if r.get("verdict") not in VERDICTS:
        errs.append(f"{r.get('id', '?')}: 판정값 '{r.get('verdict')}' 허용되지 않음")
    for e in r.get("evidence") or []:
        if not e.get("source_id") or not e.get("locator"):
            errs.append(f"{r.get('id', '?')}: 근거에 source_id/locator 누락")
    return errs


def previous_run(slug, run):
    res = proj(slug) / "results"
    if not res.exists():
        return None
    runs = sorted(d.name for d in res.iterdir()
                  if d.is_dir() and d.name < run and (d / "s5" / "final.json").exists())
    return runs[-1] if runs else None


# ---------- init / state / promote / hash ----------

def cmd_init(a):
    dst = proj(a.slug)
    if dst.exists():
        print(f"이미 존재: {dst}")
        return 1
    shutil.copytree(ROOT / "templates" / "project", dst)
    cfg = load(dst / "project.json")
    cfg["slug"] = a.slug
    save(dst / "project.json", cfg)
    idx = load(dst / "sources" / "index.json")
    idx["slug"] = a.slug
    save(dst / "sources" / "index.json", idx)
    print(f"초기화 완료: {dst}")
    return 0


def cmd_state(a):
    path = proj(a.slug) / "state.json"
    st = load(path, {}) or {}
    if a.action == "start":
        st = {"slug": a.slug, "run_id": a.run, "started_at": now(), "current_stage": "S1",
              "completed_stages": [], "stage_outputs": {}, "source_hashes": {},
              "gate_failures": {}, "last_status": st.get("last_status"), "last_error": None}
        for s in source_index(a.slug, a.run).get("sources", []):
            st["source_hashes"][s["id"]] = s.get("hash")
    elif a.action == "done":
        if a.stage not in st["completed_stages"]:
            st["completed_stages"].append(a.stage)
        order = ["S1", "S2", "S3", "S4", "S5"]
        rest = [s for s in order if s not in st["completed_stages"]]
        st["current_stage"] = rest[0] if rest else "DONE"
        if a.status:
            st["last_status"] = a.status
    elif a.action == "fail":
        n = st["gate_failures"].get(a.stage, 0) + 1
        st["gate_failures"][a.stage] = n
        st["last_error"] = f"{a.stage} 실패 {n}회: {a.reason or ''}".strip()
        if n >= 2:
            st["current_stage"] = "FAILED"
            print("같은 게이트 2회 실패 → 실행 실패로 종료 (gates §3)")
    save(path, st)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    return 0


def cmd_promote(a):
    rd = run_dir(a.slug, a.run)
    if a.what == "sources":
        src = rd / "s1" / "sources.next"
        dst = proj(a.slug) / "sources"
        for p in src.rglob("*"):
            if p.is_file():
                t = dst / p.relative_to(src)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, t)
    else:
        shutil.copy2(rd / "s4" / "impact-map.next.json", proj(a.slug) / "impact-map.json")
    print(f"반영 완료: {a.what}")
    return 0


def cmd_hash(a):
    rd = run_dir(a.slug, a.run)
    hashes = {s: dir_hash(rd / s) for s in ("s1", "s2", "s3", "s4") if (rd / s).exists()}
    save(rd / "s5" / "hashes.pre.json", hashes)
    print(json.dumps(hashes, indent=2))
    return 0


# ---------- 게이트 ----------

def gate_g0(a, g):
    goal = read_goal()
    g.check(len(goal["done_ids"]) == 10 and goal["done_ids"][0] == "DONE-01",
            f"harness-goal.md DONE 표를 읽을 수 없음 (읽은 ID {len(goal['done_ids'])}개)")
    g.check(goal["verdicts"] == VERDICTS, "harness-goal.md 판정값 4종을 읽을 수 없음")
    sv = read_service(a.slug)
    g.check(bool(sv["allowed_labels"]), "story-service A절 플랫폼 허용 목록 없음")
    g.check(sv["has_scope"], "story-service C절 검증 범위 없음")
    g.check(bool(sv["rule_ids"]), "story-service D절 필수 규칙 판정 조건 ID 없음")
    g.check(bool(sv["approved_at"]), "H0 승인 기록(approved_at) 없음")
    cfg = load(proj(a.slug) / "project.json", {}) or {}
    g.check(bool(cfg.get("slug")), "project.json slug 없음")
    g.check(bool(cfg.get("figma", {}).get("file_key")) and bool(cfg.get("figma", {}).get("page_id")),
            "project.json Figma file_key/page_id 없음")
    g.check(bool(cfg.get("notion", {}).get("review_data_source")), "project.json Notion data_source 없음")
    g.check(len(allowed_codes(a.slug)) == len(sv["allowed_labels"]),
            "story-service 허용 플랫폼과 project.json platforms label이 맞지 않음")


def gate_g1(a, g):
    rd = run_dir(a.slug, a.run)
    s1 = load(rd / "s1" / "s1-context.json")
    if not g.check(s1 is not None, "s1-context.json 없음"):
        return
    idx = load(rd / "s1" / "sources.next" / "index.json")
    if not g.check(idx is not None, "s1/sources.next/index.json 없음"):
        return
    for s in idx.get("sources", []):
        g.check(s.get("status") in SRC_STATUSES, f"자료 {s.get('id')} 상태값 '{s.get('status')}' 허용되지 않음")
    st = source_status(a.slug, a.run)
    for r in s1.get("requirements", []):
        sid = r.get("source_id")
        g.check(bool(sid), f"{r.get('id')}: source_id 없음")
        g.check(st.get(sid) == "FETCHED", f"{r.get('id')}: 근거 {sid} 상태가 FETCHED가 아님 ({st.get(sid)})")
    screens = s1.get("screens", [])
    g.check(bool(screens), "화면 목록이 비어 있음")
    allow = allowed_codes(a.slug)
    gaps = {x.get("platform") for x in s1.get("platform_gaps", [])}
    for code in allow:
        g.check(any(s.get("platform") == code for s in screens) or code in gaps,
                f"허용 플랫폼 {code} 화면 0개이고 INSUFFICIENT_INFO 기록도 없음")
    for s in screens:
        g.check(s.get("platform") in allow, f"화면 {s.get('id')}: 허용 목록 밖 플랫폼 {s.get('platform')} (DONE-06)")
    excluded = {k for k, v in st.items() if v == "EXCLUDED"}
    for r in s1.get("requirements", []):
        g.check(r.get("source_id") not in excluded, f"{r.get('id')}: EXCLUDED 자료 {r.get('source_id')} 인용 (DONE-05)")
    g.check(s1.get("notion_read") in ("ok", "failed"), "Notion 읽기 결과(notion_read) 기록 없음")
    for fb in s1.get("feedback", []):
        g.check(bool(fb.get("targets")) or fb.get("verdict") == "INSUFFICIENT_INFO",
                f"{fb.get('id')}: 대상 없음인데 INSUFFICIENT_INFO 기록 없음")


def _record_checks(a, g, records):
    st = source_status(a.slug, a.run)
    excluded = {k for k, v in st.items() if v == "EXCLUDED"}
    allow = allowed_codes(a.slug)
    for r in records:
        for e in record_errors(r):
            g.check(False, e)
        srcs = [e.get("source_id") for e in r.get("evidence") or []]
        if r.get("verdict") == "PASS":
            g.check(all(st.get(s) == "FETCHED" for s in srcs),
                    f"{r.get('id')}: FETCHED가 아닌 근거로 PASS (DONE-04)")
        g.check(not (set(srcs) & excluded), f"{r.get('id')}: EXCLUDED 자료 인용 (DONE-05)")
        for p in r.get("platform") or []:
            g.check(p in allow, f"{r.get('id')}: 허용 목록 밖 플랫폼 {p} (DONE-06)")


def gate_g2(a, g):
    rd = run_dir(a.slug, a.run)
    s1 = load(rd / "s1" / "s1-context.json", {}) or {}
    s2 = load(rd / "s2" / "s2-requirements.json")
    if not g.check(s2 is not None, "s2-requirements.json 없음"):
        return
    recs = s2.get("records", [])
    covered = {ref for r in recs for ref in (r.get("req_refs") or [])}
    for req in s1.get("requirements", []):
        g.check(req["id"] in covered, f"{req['id']}: 판정 레코드 없음")
    _record_checks(a, g, recs)
    rule_refs = {r.get("rule_ref") for r in recs}
    for rid in read_service(a.slug)["rule_ids"]:
        g.check(rid in rule_refs, f"필수 규칙 조건 {rid} 판정 레코드 없음 (DONE-07)")


def gate_g3(a, g):
    rd = run_dir(a.slug, a.run)
    s3 = load(rd / "s3" / "s3-components.json")
    if not g.check(s3 is not None, "s3-components.json 없음"):
        return
    recs = s3.get("records", [])
    covered = {ref for r in recs for ref in (r.get("component_refs") or [])}
    for c in s3.get("components", []):
        g.check(c["id"] in covered, f"컴포넌트 {c['id']}({c.get('name')}): 판정 레코드 없음")
    _record_checks(a, g, recs)
    if not (proj(a.slug) / "design.md").exists():
        g.check(any(r.get("id") == "CHK-S3-GUIDE" and r.get("verdict") == "INSUFFICIENT_INFO" for r in recs),
                "design.md 없음 → CHK-S3-GUIDE INSUFFICIENT_INFO 레코드 필요")


def gate_g4(a, g):
    rd = run_dir(a.slug, a.run)
    s1 = load(rd / "s1" / "s1-context.json", {}) or {}
    s4 = load(rd / "s4" / "s4-impact.json")
    if not g.check(s4 is not None, "s4-impact.json 없음"):
        return
    units = s4.get("units", [])
    origins = {u.get("origin", {}).get("ref") for u in units}
    expected = [c["id"] for c in s1.get("changes", [])]
    expected += [r["id"] for r in stage_records(a.slug, a.run) if r.get("stage") in ("S2", "S3") and r.get("verdict") == "FAIL"]
    expected += [t if isinstance(t, str) else t.get("id") for t in s1.get("recheck_targets", [])]
    expected += [f["id"] for f in s1.get("feedback", [])]
    for e in expected:
        g.check(e in origins, f"기점 {e}: 영향 분석 단위 없음")
    for u in units:
        for k in UNIT_FIELDS:
            v = u.get(k)
            g.check(v not in (None, "", []), f"{u.get('id')}: 영향 분석 항목 '{k}' 비어 있음 (DONE-08)")
        g.check(u.get("verdict") in VERDICTS, f"{u.get('id')}: 판정값 허용되지 않음")
        for s in u.get("related_screens", []):
            g.check(s.get("decision") in DECISIONS, f"{u.get('id')}: 화면 {s.get('screen_id')} 판정 '{s.get('decision')}' 허용되지 않음 (DONE-09)")
    _record_checks(a, g, s4.get("records", []))
    plat = {s["id"]: s.get("platform") for s in s1.get("screens", [])}
    imap = load(proj(a.slug) / "impact-map.json", {"edges": []}) or {"edges": []}
    for u in units:
        related = {s.get("screen_id") for s in u.get("related_screens", [])}
        for o in u.get("origin_screens", []):
            for e in imap.get("edges", []):
                if e.get("from") == o and plat.get(e.get("to")) and plat.get(e.get("to")) != plat.get(o):
                    g.check(e["to"] in related, f"{u.get('id')}: 영향 맵상 플랫폼 간 연결 {o}→{e['to']} 누락 (G4④)")
    nxt = load(rd / "s4" / "impact-map.next.json")
    g.check(nxt is not None and "edges" in nxt, "impact-map.next.json 없음 또는 형식 오류")


def done_checks(slug, run, judgement=None):
    rd = run_dir(slug, run)
    res = {}
    need = ["s1/s1-context.json", "s1/sources.next/index.json", "s2/s2-requirements.json",
            "s3/s3-components.json", "s4/s4-impact.json", "s4/impact-map.next.json",
            "s5/judge.json", "s5/final.json", "s5/s5-judgement.json", "s5/report.md"]
    if previous_run(slug, run):
        need.append("s5/diff.json")
    missing = [n for n in need if not (rd / n).exists()]
    res["DONE-01"] = (not missing, missing)
    final = load(rd / "s5" / "final.json", {"records": []}) or {"records": []}
    recs = final.get("records", [])
    st = source_status(slug, run)
    excluded = {k for k, v in st.items() if v == "EXCLUDED"}
    allow = allowed_codes(slug)
    bad2 = [r.get("id") for r in recs if r.get("verdict") not in VERDICTS]
    res["DONE-02"] = (not bad2, bad2)
    bad3 = [r.get("id") for r in recs if not r.get("evidence") or not r.get("follow_up")
            or any(not e.get("source_id") or not e.get("locator") for e in r.get("evidence") or [])]
    res["DONE-03"] = (not bad3, bad3)
    bad4 = [r.get("id") for r in recs if r.get("verdict") == "PASS"
            and any(st.get(e.get("source_id")) != "FETCHED" for e in r.get("evidence") or [])]
    res["DONE-04"] = (not bad4, bad4)
    bad5 = [r.get("id") for r in recs if {e.get("source_id") for e in r.get("evidence") or []} & excluded]
    res["DONE-05"] = (not bad5, bad5)
    s1 = load(rd / "s1" / "s1-context.json", {}) or {}
    bad6 = [s.get("id") for s in s1.get("screens", []) if s.get("platform") not in allow]
    bad6 += [r.get("id") for r in recs for p in r.get("platform") or [] if p not in allow]
    res["DONE-06"] = (not bad6, bad6)
    refs = {r.get("rule_ref") for r in recs}
    bad7 = [rid for rid in read_service(slug)["rule_ids"] if rid not in refs]
    res["DONE-07"] = (not bad7, bad7)
    units = impact_units(slug, run)
    bad8 = [u.get("id") for u in units if any(u.get(k) in (None, "", []) for k in UNIT_FIELDS)]
    res["DONE-08"] = (not bad8, bad8)
    bad9 = [u.get("id") for u in units for s in u.get("related_screens", []) if s.get("decision") not in DECISIONS]
    res["DONE-09"] = (not bad9, bad9)
    j = judgement or load(rd / "s5" / "s5-judgement.json", {}) or {}
    bad10 = []
    if j.get("status") == "검토 필요":
        for u in j.get("unresolved", []):
            if any(not u.get(k) for k in ("what", "why", "evidence", "impact_screens", "follow_up")):
                bad10.append(u.get("id"))
    res["DONE-10"] = (not bad10, bad10)
    return res


def gate_g5(a, g):
    rd = run_dir(a.slug, a.run)
    j = load(rd / "s5" / "s5-judgement.json")
    if not g.check(j is not None, "s5-judgement.json 없음 (finalize 먼저 실행)"):
        return
    for k, (ok, detail) in done_checks(a.slug, a.run).items():
        g.check(ok, f"{k} 위반: {detail[:10]}")
    pre = load(rd / "s5" / "hashes.pre.json")
    if g.check(pre is not None, "Judge 실행 전 해시(hashes.pre.json) 없음"):
        for s, h in pre.items():
            g.check(dir_hash(rd / s) == h, f"Judge 무결성 위반: {s} 산출물이 Judge 실행 후 바뀜 (G5②)")
    recomputed = compute_status(a.slug, a.run)
    g.check(recomputed["status"] == j.get("status"), f"실행 상태 불일치: 기록 {j.get('status')} / 재계산 {recomputed['status']}")
    sync = load(rd / "s5" / "notion-result.json")
    pending = load(proj(a.slug) / "notion-pending.json", []) or []
    g.check((sync and sync.get("ok") and sync.get("report_page_url")) or any(p.get("run_id") == a.run for p in pending),
            "Notion 반영 성공 기록(검토 사항 DB + 실행 결과 페이지 URL)도 notion-pending 적재도 없음")


def gate_gr(a, g):
    final = load(run_dir(a.slug, a.run) / "s5" / "final.json", {"records": []}) or {"records": []}
    for r in final.get("records", []):
        if r.get("rule_ref") and r.get("verdict") == "FAIL":
            g.check(False, f"필수 규칙 위반 {r['rule_ref']}: {r.get('id')} {r.get('title')}")


def cmd_gate(a):
    g = Gate(a.name)
    {"G0": gate_g0, "G1": gate_g1, "G2": gate_g2, "G3": gate_g3,
     "G4": gate_g4, "G5": gate_g5, "GR": gate_gr}[a.name](a, g)
    return g.report()


# ---------- finalize ----------

def notion_inputs(slug, run):
    s1 = load(run_dir(slug, run) / "s1" / "s1-context.json", {}) or {}
    return {n["item_id"]: n for n in s1.get("notion_inputs", []) if n.get("item_id")}


def compute_final(slug, run):
    rd = run_dir(slug, run)
    judge = load(rd / "s5" / "judge.json", {}) or {}
    opinion = {j["id"]: j for j in judge.get("records", [])}
    out = []
    recs = stage_records(slug, run) + [unit_as_record(u) for u in impact_units(slug, run)]
    # S2에서 S4 결과가 필요해 INSUFFICIENT_INFO로 남긴 규칙 조건은, S4가 같은 rule_ref로 판정하면 대체된다.
    s4_rules = {r.get("rule_ref"): r.get("id") for r in recs if r.get("stage") == "S4" and r.get("rule_ref")}
    for r in recs:
        f = dict(r)
        if (r.get("stage") == "S2" and r.get("verdict") == "INSUFFICIENT_INFO"
                and r.get("rule_ref") in s4_rules):
            f["superseded_by"] = s4_rules[r["rule_ref"]]
        j = opinion.get(r.get("id"))
        f["judge"] = j
        if j and not j.get("agree") and r.get("verdict") != "FAIL":
            f["original_verdict"] = r.get("verdict")
            f["verdict"] = "NEEDS_REVIEW"
            f["reason"] = f"{r.get('reason')} / Judge 이의: {j.get('objection_reason')}"
        out.append(f)
    return out, judge.get("missing_coverage", [])


def compute_status(slug, run):
    rd = run_dir(slug, run)
    final = load(rd / "s5" / "final.json", {"records": []}) or {"records": []}
    inputs = notion_inputs(slug, run)
    prev = previous_run(slug, run)
    prev_recs = {}
    if prev:
        prev_recs = {r["id"]: r for r in (load(run_dir(slug, prev) / "s5" / "final.json", {}) or {}).get("records", [])}
    unresolved, resolved_by_confirm = [], []
    for r in final.get("records", []):
        v = r.get("verdict")
        if v not in UNRESOLVED or r.get("superseded_by"):
            continue
        n = inputs.get(r.get("id"), {})
        # 보드는 to do 구조: 수정 완료 = 할 일 완료. 사람 판단 필요 항목은 수정 완료로 해소된다 (harness-goal §4)
        if v == "NEEDS_REVIEW" and not r.get("rule_ref") and n.get("수정 완료"):
            pr = prev_recs.get(r.get("id"))
            same_evidence = pr is None or pr.get("evidence") == r.get("evidence")
            if same_evidence:
                resolved_by_confirm.append(r.get("id"))
                continue
        unresolved.append({
            "id": r.get("id"), "verdict": v, "rule_ref": r.get("rule_ref"),
            "what": r.get("title"), "why": r.get("reason"),
            "evidence": [f"{e.get('source_id')} {e.get('locator')}" for e in r.get("evidence") or []],
            # CHK-S3-GUIDE(디자인 가이드 부재)는 하네스가 요구하는 프로젝트 전체 항목이므로 영향 범위가 전체 화면이다.
            "impact_screens": r.get("impact_screens") or r.get("screen_ids")
                              or (["전체 화면"] if r.get("id") == "CHK-S3-GUIDE" else []),
            "follow_up": r.get("follow_up"),
        })
    gr_fail = [r.get("id") for r in final.get("records", []) if r.get("rule_ref") and r.get("verdict") == "FAIL"]
    status = "승인" if not unresolved else "검토 필요"
    return {"status": status, "unresolved": unresolved, "gr_fail": gr_fail,
            "resolved_by_confirm": resolved_by_confirm}


# ---------- 사용자 표시 (artifacts §10) ----------

VERDICT_KO = {"PASS": "승인", "FAIL": "검토 필요", "NEEDS_REVIEW": "검토 필요", "INSUFFICIENT_INFO": "검토 필요"}
VTYPE_KO = {"PASS": "", "FAIL": "문제 확인", "NEEDS_REVIEW": "사람 판단 필요", "INSUFFICIENT_INFO": "자료 부족"}
DECISION_ORDER = {"수정 필요": 0, "추가 확인 필요": 1, "수정 불필요": 2}


def _figma_layout(slug):
    """metadata XML에서 최상위 노드 위치·TAG 텍스트·하위 노드→최상위 프레임 이름을 읽는다."""
    cfg = load(proj(slug) / "project.json", {}) or {}
    mf = cfg.get("figma", {}).get("metadata_file")
    path = proj(slug) / mf if mf else None
    if not path or not path.exists():
        return {}, [], {}
    lines = path.read_text(encoding="utf-8").split("\n")
    tops, tags, owner = {}, [], {}
    cur = None
    for line in lines:
        attrs = {k: html.unescape(v) for k, v in re.findall(r'(\w+)="([^"]*)"', line)}
        if re.match(r"^  <\w", line):
            cur = {"id": attrs.get("id"), "name": attrs.get("name"), "text": None,
                   "x": float(attrs.get("x", 0)), "y": float(attrs.get("y", 0)),
                   "w": float(attrs.get("width", 0)), "h": float(attrs.get("height", 0))}
            tops[cur["id"]] = cur
            if cur["name"] == "TAG":
                tags.append(cur)
        elif cur and attrs.get("id"):
            owner[attrs["id"]] = cur["id"]
            if cur["name"] == "TAG" and cur["text"] is None and line.lstrip().startswith("<text"):
                cur["text"] = attrs.get("name")
    return tops, tags, owner


class Display:
    """프레임은 노드 ID로 구분한다 (플랫폼마다 같은 이름 '17'이 있을 수 있으므로)."""

    def __init__(self, slug, run):
        s1 = load(run_dir(slug, run) / "s1" / "s1-context.json", {}) or {}
        self.fname, self.fplat, self.screen = {}, {}, {}
        for s in s1.get("screens", []):
            nids = []
            for f in s.get("frames", []):
                self.fname[f["node_id"]] = f["name"]
                self.fplat[f["node_id"]] = s.get("platform")
                nids.append(f["node_id"])
            self.screen[s["id"]] = nids
        self.src = {x["id"]: x.get("title", x["id"]) for x in source_index(slug, run).get("sources", [])}
        cfg = load(proj(slug) / "project.json", {}) or {}
        self.plat_label = {p["code"]: p["label"] for p in cfg.get("platforms", [])}
        self.plat_rank = {p["code"]: i for i, p in enumerate(cfg.get("platforms", []))}
        tops, tags, self.owner = _figma_layout(slug)
        self.tops = tops
        self.category, self.frame_tag = self._tags(tops, tags)

    def _tags(self, tops, tags):
        cat, ftag = {}, {}
        frames = [(nid, tops[nid]) for nid in self.fname if nid in tops]

        def covering(t):
            return [g for g in tags if g["h"] < 1000 and g["text"] and g["y"] < t["y"]
                    and g["x"] < t["x"] + t["w"] and g["x"] + g["w"] > t["x"]]
        base = {}
        for nid, t in frames:
            near = [g for g in covering(t) if t["y"] - g["y"] < 400]
            if near:
                base.setdefault(self.fplat.get(nid), []).append(min(g["h"] for g in near))
        med = {p: sorted(v)[len(v) // 2] for p, v in base.items()}
        for nid, t in frames:
            h0 = med.get(self.fplat.get(nid), 0) or 0
            cands = covering(t)
            secs = [g for g in cands if h0 and g["h"] >= 1.4 * h0]
            own = [g for g in cands if not (h0 and g["h"] >= 1.4 * h0) and t["y"] - g["y"] < 400]
            if secs:
                cat[nid] = max(secs, key=lambda g: g["y"])["text"]
            if own:
                ftag[nid] = max(own, key=lambda g: g["y"])["text"]
        return cat, ftag

    def _frame_of(self, nid):
        if nid in self.fname:
            return nid
        o = self.owner.get(nid)
        return o if o in self.fname else None

    def frames(self, r):
        """레코드가 가리키는 프레임 노드 ID 목록."""
        out = [self._frame_of(n) for n in r.get("figma_node_ids") or []]
        out = [n for n in out if n]
        if not out:
            for sid in r.get("screen_ids") or []:
                out += self.screen.get(sid, [])
        return list(dict.fromkeys(out))

    def display_name(self, nid):
        """프레임 이름. 숫자뿐인 이름은 플랫폼과 프레임 TAG를 붙인다 (artifacts §10)."""
        name = self.fname.get(nid)
        if name is None:
            return str(nid)
        if re.fullmatch(r"\d+", str(name)):
            tag = self.frame_tag.get(nid)
            return f"{self.plat_label.get(self.fplat.get(nid), '')} {name}" + (f" · {tag}" if tag else "")
        return name

    def frame_no(self, nid):
        """프레임 이름 앞 숫자 (없으면 맨 뒤로)."""
        m = re.match(r"\s*(\d+)", str(self.fname.get(nid, "")))
        return int(m.group(1)) if m else 99999

    def sort_key(self, nids):
        """검토 사항 정렬: 프레임 번호 오름차순 → 플랫폼 순서 (artifacts §10)."""
        keys = [(self.frame_no(n), self.plat_rank.get(self.fplat.get(n), 9)) for n in nids]
        return min(keys) if keys else (99999, 9)

    def order_value(self, nids):
        no, pr = self.sort_key(nids)
        return no * 10 + min(pr, 9)

    def frame_numbers(self, nids, first=None):
        """Figma 프레임 이름 번호만 (제목과 같은 순서). Notion '프레임 번호' 칸."""
        nids = sorted(dict.fromkeys(nids), key=lambda n: (first is not None and self.fplat.get(n) != first,
                                                          self.sort_key([n])))
        return ", ".join(dict.fromkeys(str(self.fname[n]) for n in nids if n in self.fname))

    def frame_label(self, nids, cap=4, first=None):
        """프레임 이름 목록 (번호순). first가 있으면 그 플랫폼 프레임을 앞에 둔다."""
        nids = sorted(dict.fromkeys(nids), key=lambda n: (first is not None and self.fplat.get(n) != first,
                                                          self.sort_key([n])))
        if not nids:
            return "(특정 프레임 없음 · 전체 화면)"
        shown = list(dict.fromkeys(self.display_name(n) for n in nids))
        return ", ".join(shown[:cap]) + (f" 외 {len(shown) - cap}개" if len(shown) > cap else "")

    def text(self, s):
        if not s:
            return s
        s = str(s)

        def node_sub(m):
            nid = self._frame_of(m.group(0))
            if nid:
                return f"「{self.display_name(nid)}」"
            t = self.tops.get(m.group(0))
            return f"「{t['name']}」" if t and t["name"] != "TAG" else m.group(0)
        s = re.sub(r"(?<![\d:])\d+:\d+(?![\d:])", node_sub, s)
        s = re.sub(r"(?<![A-Za-z])(APP|WEB)-(\d+)(?!\d)",
                   lambda m: f"「{self.display_name(self.screen[m.group(0)][0])}」"
                   if self.screen.get(m.group(0)) else m.group(0), s)
        s = re.sub(r"「([^」]+)」\s*\(\s*\1\s*\)", r"「\1」", s)   # 「이름」 (이름) 중복 제거
        return s

    def evidence(self, e):
        sid, loc = e.get("source_id"), e.get("locator") or ""
        m = re.search(r"(?<![\d:])\d+:\d+(?![\d:])", loc)
        if m and (self._frame_of(m.group(0)) or m.group(0) in self.tops):
            return f"Figma {self.text(m.group(0))}"
        return f"{self.src.get(sid, sid)} {self.text(loc)}".strip()

    def platforms(self, nids, r=None):
        """프레임 기준 플랫폼 코드 (project.json platforms 순서)."""
        codes = {self.fplat.get(n) for n in nids if self.fplat.get(n)} or set((r or {}).get("platform") or [])
        return sorted(codes, key=lambda c: self.plat_rank.get(c, 9))

    def fix_platforms(self, nids, r=None):
        """수정 대상 플랫폼 (artifacts §10). 보드의 플랫폼 줄은 '그 플랫폼을 고쳐야 하는 항목'만 보여 준다.
        ① 레코드 fix_platforms ② 후속 조치가 '조치 없음' → 없음 ③ 후속 조치에 적힌 화면의 플랫폼
        ④ 항목 프레임이 가장 많은 플랫폼 (같으면 모두)."""
        r = r or {}
        rank = lambda c: self.plat_rank.get(c, 9)
        if r.get("fix_platforms") is not None:
            return sorted(set(r["fix_platforms"]), key=rank)
        fu = str(r.get("follow_up") or "").strip()
        if fu.startswith("조치 없음"):
            return []
        named = set(m.group(1) for m in re.finditer(r"(?<![A-Za-z])(APP|WEB)-\d+", fu))
        named |= {self.fplat.get(self._frame_of(m.group(0))) for m in re.finditer(r"(?<![\d:])\d+:\d+(?![\d:])", fu)}
        for code, label in self.plat_label.items():
            if re.search(re.escape(label) + r"\s*\d+", fu):
                named.add(code)
        named.discard(None)
        if named:
            return sorted(named, key=rank)
        count = {}
        for n in nids:
            if self.fplat.get(n):
                count[self.fplat[n]] = count.get(self.fplat[n], 0) + 1
        if not count:
            plats = r.get("platform") or []
            return plats if len(plats) == 1 else []   # 프레임 없는 전체 공통 항목
        top = max(count.values())
        return sorted([c for c, k in count.items() if k == top], key=rank)

    def primary_platform(self, nids, r=None):
        fp = self.fix_platforms(nids, r)
        return fp[0] if fp else None

    def primary_frames(self, nids, r=None):
        """수정 대상 플랫폼 프레임만 (카테고리·정렬 기준)."""
        fp = set(self.fix_platforms(nids, r))
        return [n for n in nids if self.fplat.get(n) in fp] or list(nids)

    def platform_group(self, nids, r=None):
        """검토 사항 플랫폼 분류: 수정 대상 플랫폼 (사용자앱 / 관리자웹 / 둘 다 / 전체 공통)."""
        fp = self.fix_platforms(nids, r)
        return (len(fp) or 9, tuple(self.plat_rank.get(c, 9) for c in fp)), \
            (" · ".join(self.plat_label.get(c, c) for c in fp) or "전체 공통")

    def page_label(self, nids, r=None):
        """페이지 case: '관리자웹 뉴스 관리/상세' (수정 대상 플랫폼 · 카테고리 / 프레임 태그)."""
        fp = self.fix_platforms(nids, r)
        plat = "·".join(self.plat_label.get(c, c) for c in fp) or "전체 공통"
        main = self.primary_frames(nids, r)
        main = sorted(main, key=lambda n: self.sort_key([n]))
        if not main:
            return plat
        n0 = main[0]
        cat, tag = self.category.get(n0), self.frame_tag.get(n0)
        page = cat or tag or self.display_name(n0)
        if tag and cat and tag.replace(" ", "").startswith(cat.replace(" ", "")):
            tag = re.sub(r"^\s*" + r"\s*".join(map(re.escape, cat.replace(" ", ""))) + r"\s*/?\s*", "", tag)
        if tag and tag != cat:
            page += f"/{tag}"
        return f"{plat} {page}"

    def categories(self, nids):
        out = list(dict.fromkeys(self.category[n] for n in nids if n in self.category))
        return out or ["분류 없음"]

    def tags(self, nids):
        return ", ".join(dict.fromkeys(self.frame_tag[n] for n in nids if n in self.frame_tag))


REVIEW_CASES = ["오타", "명칭·문구", "UI", "로직", "추가 고려사항", "반영 확인", "자료 확인"]


def display_overrides(slug, run):
    """Orchestrator 표시 보정 s5/display-overrides.json + Judge duplicates (artifacts §12). 판정은 바꾸지 않는다."""
    rd = run_dir(slug, run)
    o = load(rd / "s5" / "display-overrides.json", {}) or {}
    dup = dict(o.get("duplicates") or {})
    for d in (load(rd / "s5" / "judge.json", {}) or {}).get("duplicates", []) or []:
        if d.get("id") and d.get("same_as"):
            dup.setdefault(d["id"], d["same_as"])
    return {"review_case": o.get("review_case") or {}, "duplicates": dup,
            "user_removed": set(o.get("user_removed") or [])}


def review_case(r, ov=None):
    """검토 case: 레코드 review_case → 보정 파일 → 제목 키워드 추정."""
    if r.get("review_case") in REVIEW_CASES:
        return r["review_case"]
    c = ((ov or {}).get("review_case") or {}).get(r.get("id"))
    if c:
        return c
    t = f"{r.get('title') or ''} {r.get('reason') or ''}"
    if r.get("verdict") == "INSUFFICIENT_INFO" or "판단 불가" in t:
        return "자료 확인"
    if "오타" in t:
        return "오타"
    if re.search(r"반영됨|충돌하지 않음|대응됨", r.get("title") or ""):
        return "반영 확인"
    if re.search(r"명칭|문구|표기|라벨|용어|이름", t):
        return "명칭·문구"
    if re.search(r"정해지지 않|화면 없|기준 없|알림이 없", t):
        return "추가 고려사항"
    if re.search(r"상태|컴포넌트|variant|버튼|모달|배지|표시|가려", t):
        return "UI"
    return "로직"


def merged_view(slug, run, final_records, unresolved):
    """표시용 병합 (판정은 바꾸지 않는다, artifacts §10).
    - S4에서 FAIL 레코드를 기점으로 한 분석 단위는 기점 항목에 합친다 (영향 화면 보강).
    - Judge가 '같은 문제'라고 지적한 중복 항목은 지목된 대표 항목에 합친다.
    반환: (대표 미해소 항목 목록, {대표 id: [합쳐진 id...]}, {대표 id: [추가 영향 화면...]})"""
    by_id = {r["id"]: r for r in final_records}
    ids = [u["id"] for u in unresolved]
    open_ids = set(ids)
    target = {}
    for u in impact_units(slug, run):
        o = u.get("origin", {})
        if o.get("type") == "fail" and o.get("ref") in open_ids and u.get("id") in open_ids:
            target[u["id"]] = o["ref"]
    for r in final_records:
        j = r.get("judge") or {}
        reason = j.get("objection_reason") or ""
        if not j.get("agree", True) and ("두 번 집계" in reason or "중복" in reason):
            m = re.search(r"((?:CHK-S\d|IMP-S4)-\d+)[과와]\s*같은", reason)
            if m and m.group(1) in open_ids and r["id"] in open_ids and m.group(1) != r["id"]:
                target[r["id"]] = m.group(1)

    for i, keep in display_overrides(slug, run)["duplicates"].items():
        if i in open_ids and keep in open_ids and i != keep:
            target[i] = keep

    def root(i, seen=()):
        t = target.get(i)
        return root(t, seen + (i,)) if t and t not in seen else i
    merged, extra = {}, {}
    for i in ids:
        rt = root(i)
        if rt != i:
            merged.setdefault(rt, []).append(i)
            unit = by_id.get(i, {})
            extra.setdefault(rt, []).extend(unit.get("impact_screens") or [])
    primary = [u for u in unresolved if root(u["id"]) == u["id"]]
    return primary, merged, extra


def focus_config(slug):
    """핵심 검증 관점. project.json report.focus가 있으면 그것, 없으면 공통 기본 관점 (artifacts §10)."""
    cfg = load(proj(slug) / "project.json", {}) or {}
    own = (cfg.get("report") or {}).get("focus")
    if own:
        return own
    try:
        codes = set(allowed_codes(slug))
    except (OSError, KeyError, SystemExit):
        codes = {p["code"] for p in cfg.get("platforms", [])}
    focus = [{"id": "Q1", "label": "수정사항 반영",
              "question": ("관리자웹 수정사항을 제대로 반영했는가" if "WEB" in codes else "수정사항을 제대로 반영했는가")}]
    if {"APP", "WEB"} <= codes:   # 모바일·관리자웹 두 가지가 있을 때만
        focus.append({"id": "Q2", "label": "앱 크로스 체크",
                      "question": "사용자앱(모바일)과 크로스 체크했을 때 연결이 잘 되는가"})
    focus.append({"id": "Q3", "label": "고려 못한 사항", "question": "고려하지 못한 사항이 있는가", "default": True})
    return focus


def record_focus(r, focus):
    ids = {q["id"] for q in focus}
    if r.get("focus") in ids:
        return r["focus"]
    default = [q["id"] for q in focus if q.get("default")]
    return default[0] if default else None


def build_report(slug, run, final, judgement, missing_cov, diff):
    rd = run_dir(slug, run)
    D = Display(slug, run)
    s1 = load(rd / "s1" / "s1-context.json", {}) or {}
    s4 = load(rd / "s4" / "s4-impact.json", {}) or {}
    recs = final["records"]
    by_id = {r["id"]: r for r in recs}
    n_pass = sum(1 for r in recs if r.get("verdict") == "PASS")
    n_type = {k: sum(1 for r in recs if r.get("verdict") == k) for k in ("FAIL", "NEEDS_REVIEW", "INSUFFICIENT_INFO")}
    L = [f"# UX 검증 보고서 — {slug} / {run}", ""]
    L.append(f"- 결과: **{judgement['status'] or '실행 실패'}**")
    L.append(f"- 판정: 승인 {n_pass} · 검토 필요 {sum(n_type.values())} "
             f"(문제 확인 {n_type['FAIL']} · 사람 판단 필요 {n_type['NEEDS_REVIEW']} · 자료 부족 {n_type['INSUFFICIENT_INFO']})")
    L.append(f"- 컨펌으로 해소: {len(judgement['resolved_by_confirm'])}건")
    if s1.get("notion_read") == "failed":
        L.append("- ⚠ Notion 검토 사항을 읽지 못해 이번 실행에서는 수정 완료를 해소로 인정하지 않았다.")
    L.append("")
    focus = focus_config(slug)
    primary, merged, _ = merged_view(slug, run, recs, judgement["unresolved"])
    if focus:
        unresolved_ids = {u["id"] for u in primary}
        hidden = {i for v in merged.values() for i in v}
        L.append("## 한눈에 보기")
        L.append(f"*같은 문제를 합친 고유 항목 기준 · 미해소 {len(primary)}건 (원 집계 {len(judgement['unresolved'])}건)*")
        L.append("")
        for q in focus:
            mine = [r for r in recs if record_focus(r, focus) == q["id"] and r["id"] not in hidden]
            open_ = [r for r in mine if r["id"] in unresolved_ids]
            if not mine:
                head = "판정 항목 없음"
            elif not open_:
                head = f"✅ 문제 없음 ({len(mine)}건 확인)"
            else:
                t = {k: sum(1 for r in open_ if r.get("verdict") == k) for k in ("FAIL", "NEEDS_REVIEW", "INSUFFICIENT_INFO")}
                head = (f"⚠ 검토 필요 {len(open_)}건 / {len(mine)}건 — 문제 확인 {t['FAIL']} · "
                        f"사람 판단 필요 {t['NEEDS_REVIEW']} · 자료 부족 {t['INSUFFICIENT_INFO']}")
            L.append(f"### {q['label']} — {head}")
            L.append(f"*{q['question']}*")
            order = {"FAIL": 0, "NEEDS_REVIEW": 1, "INSUFFICIENT_INFO": 2}
            for r in sorted(open_, key=lambda x: order.get(x.get("verdict"), 9))[:8]:
                L.append(f"- **{D.frame_label(D.frames(r), cap=2)}** — {D.text(r.get('title'))} ({VTYPE_KO[r['verdict']]})")
            if len(open_) > 8:
                L.append(f"- 외 {len(open_) - 8}건 (아래 상세 · 검토 사항 DB)")
            L.append("")
    if judgement["gr_fail"]:
        L.append("## ⛔ 필수 규칙 위반 (컨펌으로 해소 불가)")
        for rid in judgement["gr_fail"]:
            r = by_id[rid]
            L.append(f"- **{D.frame_label(D.frames(r))}** — 규칙 {r['rule_ref']}: {D.text(r.get('reason'))}")
        L.append("")
    fb_units = [u for u in s4.get("units", []) if u.get("origin", {}).get("type") == "feedback"]
    if fb_units:
        L.append("## 피드백 영향 영역")
        fbtext = {f["id"]: f.get("text") for f in s1.get("feedback", [])}
        for u in fb_units:
            ref = u["origin"]["ref"]
            L.append(f"### {fbtext.get(ref, ref)}")
            L.append(f"- 판정: {VERDICT_KO.get(u.get('verdict'))} ({VTYPE_KO.get(u.get('verdict'))}) / 수정 필요 여부: {u.get('needs_fix')}")
            if u.get("consider_areas"):
                L.append(f"- 고려해야 할 영역: {', '.join(u['consider_areas'])}")
            L.append(f"- 예상 문제: {D.text(u.get('expected_problem'))}")
            L.append("")
            L.append("| 프레임 | 카테고리 | 판정 | 사유 |")
            L.append("|---|---|---|---|")
            for s in sorted(u.get("related_screens", []), key=lambda x: DECISION_ORDER.get(x.get("decision"), 9)):
                names = D.screen.get(s.get("screen_id"), [s.get("screen_id")])
                L.append(f"| {D.frame_label(names)} | {', '.join(D.categories(names))} | {s.get('decision')} | {D.text(s.get('reason', ''))} |")
            L.append(f"- 후속 작업: {D.text(u.get('follow_up'))}")
            L.append("")
    if diff and diff.get("changes"):
        L.append("## 이전 실행 대비 변화")
        for c in diff["changes"]:
            r = by_id.get(c["id"], {})
            L.append(f"- {D.frame_label(D.frames(r))} · {D.text(r.get('title'))}: "
                     f"{VERDICT_KO.get(c['before'], '없음')} → {VERDICT_KO.get(c['after'], '없음')}")
        L.append("")
    if judgement["status"] == "검토 필요":
        L.append("## 미승인 사유 (플랫폼 · 카테고리별 검토 필요 항목)")
        groups = {}
        for u in judgement["unresolved"]:
            r = by_id[u["id"]]
            names = D.frames(r)
            pk, pl = D.platform_group(names, r)
            groups.setdefault((pk, pl, D.categories(D.primary_frames(names, r))[0]), []).append((u, r, names))
        for key in sorted(groups, key=lambda k: (k[0], min(D.sort_key(x[2]) for x in groups[k]))):
            L.append(f"### {key[1]} / {key[2]} ({len(groups[key])}건)")
            L.append("| 검토 사항(프레임) | 판정 유형 | 검토 내용 | 왜 | 근거 | 영향 화면 | 후속 조치 |")
            L.append("|---|---|---|---|---|---|---|")
            for u, r, names in sorted(groups[key], key=lambda x: D.sort_key(x[2])):
                ev = "; ".join(D.evidence(e) for e in r.get("evidence") or [])
                imp = D.frame_label([n for s in u["impact_screens"] for n in D.screen.get(s, [s])], cap=6)
                L.append(f"| {D.frame_label(names)} | {VTYPE_KO[u['verdict']]} | {D.text(u['what'])} | {D.text(u['why'])} | {ev} | {imp} | {D.text(u['follow_up'])} |")
            L.append("")
    if s1.get("excluded_requests") or s1.get("excluded_sources"):
        L.append("## 제외된 요청·자료")
        for x in s1.get("excluded_requests", []) + s1.get("excluded_sources", []):
            L.append(f"- {x.get('request') or x.get('source')}: {x.get('reason')}")
        L.append("")
    if missing_cov:
        L.append("## 판정자(Judge)가 지적한 누락")
        for m in missing_cov:
            L.append(f"- {D.text(m)}")
        L.append("")
    L.append("## 실행 완결성 (DONE)")
    for k, (ok, d) in judgement["done"].items():
        L.append(f"- {k}: {'OK' if ok else '미충족 ' + str(d[:5])}")
    L.append("")
    L.append("## 전체 항목 (플랫폼 · 카테고리별)")
    groups = {}
    for r in recs:
        names = D.frames(r)
        pk, pl = D.platform_group(names, r)
        groups.setdefault((pk, pl, D.categories(D.primary_frames(names, r))[0]), []).append((r, names))
    for key in sorted(groups, key=lambda k: (k[0], min(D.sort_key(x[1]) for x in groups[k]))):
        L.append(f"### {key[1]} / {key[2]}")
        L.append("| 검토 사항(프레임) | 판정 | 판정 유형 | 규칙 | 검토 내용 | 근거 |")
        L.append("|---|---|---|---|---|---|")
        for r, names in sorted(groups[key], key=lambda x: D.sort_key(x[1])):
            ev = "; ".join(D.evidence(e) for e in r.get("evidence") or [])
            L.append(f"| {D.frame_label(names)} | {VERDICT_KO.get(r.get('verdict'))} | {VTYPE_KO.get(r.get('verdict'), '')} | {r.get('rule_ref') or ''} | {D.text(r.get('title'))} | {ev} |")
        L.append("")
    return "\n".join(L) + "\n"


def cmd_finalize(a):
    rd = run_dir(a.slug, a.run)
    records, missing_cov = compute_final(a.slug, a.run)
    save(rd / "s5" / "final.json", {"run_id": a.run, "records": records})
    diff = None
    prev = previous_run(a.slug, a.run)
    if prev:
        before = {r["id"]: r.get("verdict") for r in (load(run_dir(a.slug, prev) / "s5" / "final.json", {}) or {}).get("records", [])}
        after = {r["id"]: r.get("verdict") for r in records}
        changes = [{"id": i, "before": before.get(i), "after": after.get(i)}
                   for i in sorted(set(before) | set(after)) if before.get(i) != after.get(i)]
        diff = {"run_id": a.run, "previous": prev, "changes": changes}
        save(rd / "s5" / "diff.json", diff)
    st = compute_status(a.slug, a.run)
    judgement = {"run_id": a.run, "status": st["status"], "gr_fail": st["gr_fail"],
                 "unresolved": st["unresolved"], "resolved_by_confirm": st["resolved_by_confirm"]}
    save(rd / "s5" / "s5-judgement.json", judgement)
    (rd / "s5" / "report.md").write_text("", encoding="utf-8")
    done = done_checks(a.slug, a.run, judgement)
    judgement["done"] = {k: [ok, d] for k, (ok, d) in done.items()}
    if not all(ok for ok, _ in done.values()):
        judgement["status"] = None   # 실행 실패: 상태를 부여하지 않음
    save(rd / "s5" / "s5-judgement.json", judgement)
    report = build_report(a.slug, a.run, {"records": records},
                          {**judgement, "done": done}, missing_cov, diff)
    (rd / "s5" / "report.md").write_text(report, encoding="utf-8")
    print(f"상태: {judgement['status'] or '실행 실패'} / 미해소 {len(st['unresolved'])}건 / 필수 규칙 위반 {len(st['gr_fail'])}건")
    return 0


# ---------- Notion ----------

def _row_props(slug, run, D, cfg, r, verdict, what, why, follow_up, impact_ids, stage_mark, extra_evidence=""):
    """검토 사항 DB 한 행의 하네스 칸 (사용자 칸은 넣지 않는다)."""
    labels = {p["code"]: p["label"] for p in cfg["platforms"]}
    rule_opts = cfg.get("notion", {}).get("rule_options", {})
    rule = rule_opts.get((r.get("rule_ref") or "").split("-")[0], "해당 없음") if r.get("rule_ref") else "해당 없음"
    names = D.frames(r)
    main = D.primary_frames(names, r)   # 대표 플랫폼 프레임: 카테고리·플랫폼·정렬 기준
    impact = [nm for sid in impact_ids for nm in D.screen.get(sid, [sid])]
    case = review_case(r, display_overrides(slug, run))
    props = {
        "검토 사항": f"{case} · {D.page_label(names, r)}", "검토 case": case,
        "화면 프레임": D.frame_label(names, first=D.primary_platform(names, r)),
        "프레임 번호": D.frame_numbers(names, first=D.primary_platform(names, r)), "검토 내용": D.text(what), "항목 ID": r["id"],
        "판정": VERDICT_KO[verdict],
        "카테고리": D.categories(main), "프레임 태그": D.tags(main), "정렬 순서": D.order_value(main),
        "단계": STAGE_LABEL.get(r.get("stage"), "S4 영향 분석"),
        "플랫폼": [labels[x] for x in D.fix_platforms(names, r) if x in labels],
        "영향 화면": D.frame_label(impact, cap=8) if impact else "",
        "필수 규칙": rule, "사유": D.text(why),
        "근거": "; ".join(D.evidence(e) for e in r.get("evidence") or []) + extra_evidence,
        "후속 조치": D.text(follow_up), "최근 실행": run,
    }
    return props


def _focus_lines(D, recs, open_ids, focus, cap=8):
    """관점별 두괄식 요약 줄 (결론 한 줄 → 프레임·한 줄 요약)."""
    L = []
    order = {"FAIL": 0, "NEEDS_REVIEW": 1, "INSUFFICIENT_INFO": 2}
    groups = focus or [{"id": None, "label": "전체", "question": ""}]
    for q in groups:
        mine = [r for r in recs if (record_focus(r, focus) == q["id"] if focus else True)]
        open_ = [r for r in mine if r["id"] in open_ids]
        if not mine:
            head = "판정 항목 없음"
        elif not open_:
            head = f"✅ 문제 없음 ({len(mine)}건 확인)"
        else:
            t = {k: sum(1 for r in open_ if r.get("verdict") == k) for k in order}
            head = (f"⚠ 검토 필요 {len(open_)}건 / {len(mine)}건 — 문제 확인 {t['FAIL']} · "
                    f"사람 판단 필요 {t['NEEDS_REVIEW']} · 자료 부족 {t['INSUFFICIENT_INFO']}")
        L.append(f"### {q['label']} — {head}")
        if q.get("question"):
            L.append(f"*{q['question']}*")
        for r in sorted(open_, key=lambda x: (order.get(x.get("verdict"), 9), D.sort_key(D.frames(x))))[:cap]:
            L.append(f"- **{D.frame_label(D.frames(r), cap=2)}** — {D.text(r.get('title'))} ({VTYPE_KO[r['verdict']]})")
        if len(open_) > cap:
            L.append(f"- 외 {len(open_) - cap}건 (검토 사항 DB)")
        L.append("")
    return L


def _progress_line(stage):
    order = ["S1", "S2", "S3", "S4", "S5"]
    names = {"S1": "맥락", "S2": "요구사항·흐름", "S3": "컴포넌트", "S4": "영향 분석", "S5": "최종 판정"}
    done = order[: order.index(stage) + 1]
    return " → ".join(f"{'✅' if s in done else '⏳'} {names[s]}" for s in order)


def stage_page(slug, run, stage):
    """단계별 결과 페이지 조각. section은 페이지에 추가하고, header는 맨 위(진행 상황/결론)를 교체한다."""
    rd = run_dir(slug, run)
    D = Display(slug, run)
    focus = focus_config(slug)
    s1 = load(rd / "s1" / "s1-context.json", {}) or {}
    header = [f"**진행 상황:** {_progress_line(stage)}", ""]
    sec = []
    if stage == "S1":
        from collections import Counter
        c = Counter(sc.get("platform") for sc in s1.get("screens", []))
        sec.append("## 1. 검증 대상 (S1 맥락)")
        sec.append("- 화면: " + " · ".join(f"{D.plat_label.get(k, k)} {v}개" for k, v in c.items()))
        sec.append(f"- 요구사항 {len(s1.get('requirements', []))}개 · 구역별 피드백 {len(s1.get('feedback', []))}개")
        for f in s1.get("feedback", []):
            first = (f.get("text") or "").split("\n")[0][:60]
            sec.append(f"  - {first} — Figma 반영(1차 관찰): {f.get('figma_reflected', '확인 불가')}")
        for x in s1.get("excluded_requests", []) + s1.get("excluded_sources", []):
            sec.append(f"- 제외: {x.get('request') or x.get('source')} — {x.get('reason')}")
        if s1.get("unverified"):
            sec.append(f"- 미확인: {s1['unverified'] if isinstance(s1['unverified'], str) else len(s1['unverified'])}")
    elif stage in ("S2", "S3"):
        rel = {"S2": "s2/s2-requirements.json", "S3": "s3/s3-components.json"}[stage]
        recs = (load(rd / rel, {}) or {}).get("records", [])
        open_ids = {r["id"] for r in recs if r.get("verdict") in UNRESOLVED}
        title = {"S2": "2. 요구사항·흐름 (S2, 잠정)", "S3": "3. 컴포넌트 (S3, 잠정)"}[stage]
        sec.append(f"## {title}")
        sec += _focus_lines(D, recs, open_ids, focus)
    elif stage == "S4":
        s4 = load(rd / "s4" / "s4-impact.json", {}) or {}
        fbtext = {f["id"]: f.get("text") for f in s1.get("feedback", [])}
        sec.append("## 4. 구역별 영향 영역 (S4, 잠정)")
        for u in s4.get("units", []):
            if u.get("origin", {}).get("type") != "feedback":
                continue
            name = (fbtext.get(u["origin"]["ref"]) or u["origin"]["ref"]).split("\n")[0][:40]
            sec.append(f"<details><summary>{name} — {VERDICT_KO.get(u.get('verdict'))}</summary>")
            sec.append("")
            sec.append(f"- 고려해야 할 영역: {', '.join(u.get('consider_areas') or [])}")
            sec.append(f"- 예상 문제: {D.text(u.get('expected_problem'))}")
            for x in sorted(u.get("related_screens", []), key=lambda x: DECISION_ORDER.get(x.get("decision"), 9)):
                sec.append(f"  - {D.frame_label(D.screen.get(x.get('screen_id'), [x.get('screen_id')]))}: "
                           f"{x.get('decision')} — {D.text(x.get('reason', ''))}")
            sec.append(f"- 후속 작업: {D.text(u.get('follow_up'))}")
            sec.append("</details>")
        edges = (load(rd / "s4" / "impact-map.next.json", {}) or {}).get("edges", [])
        sec.append(f"- 영향 맵 연결 {len(edges)}개")
    elif stage == "S5":
        final = (load(rd / "s5" / "final.json", {}) or {}).get("records", [])
        j = load(rd / "s5" / "s5-judgement.json", {}) or {}
        primary, merged, _ = merged_view(slug, run, final, j.get("unresolved", []))
        hidden = {i for v in merged.values() for i in v}
        by_id = {r["id"]: r for r in final}
        header = [f"**진행 상황:** {_progress_line('S5')}", ""]
        gr = j.get("gr_fail", [])
        header.append(f"> **결과: {j.get('status') or '실행 실패'}** — 미해소 {len(primary)}건(같은 문제 병합)"
                      + (f" · 필수 규칙 위반 {len(gr)}건" if gr else ""))
        header.append("")
        header.append("## 한눈에 보기")
        header += _focus_lines(D, [r for r in final if r["id"] not in hidden], {u["id"] for u in primary}, focus)
        if gr:
            header.append("## ⛔ 필수 규칙 위반 (컨펌으로 해소 불가)")
            seen = set()
            for rid in gr:
                r = by_id[rid]
                key = (r.get("rule_ref"), D.frame_label(D.frames(r), cap=2))
                if key in seen:
                    continue
                seen.add(key)
                header.append(f"- **{key[1]}** — 규칙 {r['rule_ref']}: {D.text(r.get('title'))}")
            header.append("")
        lowered = [r for r in final if r.get("original_verdict")]
        sec.append("## 5. 판정자(Judge) 확인으로 바뀐 판정")
        sec.append(f"- 판정이 낮아진 항목 {len(lowered)}건, 같은 문제로 병합된 항목 {len(hidden)}건")
        for r in lowered[:10]:
            sec.append(f"  - {D.frame_label(D.frames(r), cap=2)} — {D.text(r.get('title'))}: "
                       f"{VERDICT_KO[r['original_verdict']]}({VTYPE_KO[r['original_verdict']] or '승인'}) → 검토 필요(사람 판단 필요)")
    return "\n".join(header) + "\n", "\n".join(sec) + "\n"


def stage_ops(slug, run, stage):
    """단계별 검토 사항 DB upsert 목록 (항목 ID 기준). 실행 주체는 같은 항목 ID 행이 있으면 갱신, 없으면 생성한다."""
    rd = run_dir(slug, run)
    cfg = load(proj(slug) / "project.json")
    D = Display(slug, run)
    ops = []
    if stage in ("S2", "S3"):
        rel = {"S2": "s2/s2-requirements.json", "S3": "s3/s3-components.json"}[stage]
        for r in (load(rd / rel, {}) or {}).get("records", []):
            if r.get("verdict") in UNRESOLVED:
                ops.append({"op": "upsert", "item_id": r["id"], "properties": _row_props(
                    slug, run, D, cfg, r, r["verdict"], r.get("title"), r.get("reason"), r.get("follow_up"),
                    r.get("impact_screens") or r.get("screen_ids") or [], f"잠정 {stage}")})
    elif stage == "S4":
        s4 = load(rd / "s4" / "s4-impact.json", {}) or {}
        for u in s4.get("units", []):
            o = u.get("origin", {})
            ur = unit_as_record(u)
            if o.get("type") == "fail":   # 기점 행의 영향 화면만 보강
                imp = [x.get("screen_id") for x in u.get("related_screens", []) if x.get("decision") != "수정 불필요"]
                ops.append({"op": "update_only", "item_id": o.get("ref"), "properties": {
                    "영향 화면": D.frame_label([n for sid in imp for n in D.screen.get(sid, [sid])], cap=8),
                    "후속 조치": D.text(u.get("follow_up")), "최근 실행": run}})
            elif ur.get("verdict") in UNRESOLVED:
                ur["focus"] = u.get("focus")
                ops.append({"op": "upsert", "item_id": ur["id"], "properties": _row_props(
                    slug, run, D, cfg, ur, ur["verdict"], ur.get("title"), ur.get("reason"), ur.get("follow_up"),
                    ur.get("impact_screens") or [], "잠정 S4")})
        for r in s4.get("records", []):
            if r.get("verdict") in UNRESOLVED:
                ops.append({"op": "upsert", "item_id": r["id"], "properties": _row_props(
                    slug, run, D, cfg, r, r["verdict"], r.get("title"), r.get("reason"), r.get("follow_up"),
                    r.get("impact_screens") or r.get("screen_ids") or [], "잠정 S4")})
    elif stage == "S5":
        final = {r["id"]: r for r in load(rd / "s5" / "final.json")["records"]}
        j = load(rd / "s5" / "s5-judgement.json")
        inputs = notion_inputs(slug, run)
        primary, merged, extra = merged_view(slug, run, list(final.values()), j["unresolved"])
        for u in primary:
            r = final[u["id"]]
            imp = list(dict.fromkeys((u["impact_screens"] or []) + extra.get(u["id"], [])))
            props = _row_props(slug, run, D, cfg, r, u["verdict"], u["what"], u["why"], u["follow_up"], imp, "확정",
                               f" · 같은 문제: {', '.join(merged[u['id']])}" if merged.get(u["id"]) else "")
            n = inputs.get(u["id"])
            props["재검증 결과"] = ("여전히 FAIL" if u["verdict"] == "FAIL" else "미실행") if n and n.get("수정 완료") else "미실행"
            ops.append({"op": "upsert", "item_id": u["id"], "properties": props})
        for rep, ids in merged.items():
            for i in ids:   # 앞 단계에서 만든 중복 행은 병합 표시
                ops.append({"op": "archive", "item_id": i, "properties": {},
                            "note": f"중복 — {rep} 행에 합침 (있는 행만 휴지통으로)"})
        unresolved_ids = {u["id"] for u in j["unresolved"]}
        for item_id in inputs:
            if item_id not in unresolved_ids:
                ops.append({"op": "update_only", "item_id": item_id, "properties": {
                    "판정": "승인", "재검증 결과": "PASS", "최근 실행": run}})
    removed = display_overrides(slug, run)["user_removed"]
    ops = [o for o in ops if o["item_id"] not in removed]   # 사용자가 지운 행은 다시 만들지 않는다
    if stage != "S5":   # 중복으로 합쳐질 항목은 앞 단계에서도 만들지 않는다
        dups = display_overrides(slug, run)["duplicates"]
        ops = [o for o in ops if o["item_id"] not in dups]
    ops.sort(key=lambda o: (o["op"] != "upsert", o["properties"].get("정렬 순서", 999999)))
    for op in ops:
        op["properties"] = {k: v for k, v in op["properties"].items() if v not in ("", [], None)}
        if USER_FIELDS & set(op["properties"]):
            raise SystemExit(f"오류: 사용자 칸 {USER_FIELDS & set(op['properties'])} 쓰기 시도")
    return ops


def cmd_notion_sync(a):
    """단계별 Notion 반영 계획을 results/<run>/notion/에 만든다 (artifacts §11)."""
    rd = run_dir(a.slug, a.run)
    cfg = load(proj(a.slug) / "project.json")
    stage = a.stage or "S5"
    ops = stage_ops(a.slug, a.run, stage)
    header, section = stage_page(a.slug, a.run, stage)
    nd = rd / "notion"
    categories = sorted({c for op in ops for c in op["properties"].get("카테고리", [])})
    plan = {"run_id": a.run, "stage": stage, "data_source": cfg["notion"]["review_data_source"],
            "parent_page_id": cfg["notion"].get("parent_page_id"), "categories": categories, "ops": ops}
    save(nd / f"sync-{stage}.json", plan)
    (nd / f"page-{stage}-header.md").write_text(header, encoding="utf-8")
    (nd / f"page-{stage}-section.md").write_text(section, encoding="utf-8")
    if stage == "S5":
        save(rd / "s5" / "notion-sync.json", plan)
    n = {k: sum(o["op"] == k for o in ops) for k in ("upsert", "update_only", "archive")}
    print(f"Notion {stage} 반영 계획: upsert {n['upsert']} / 기존 행 갱신 {n['update_only']} / 중복 정리 {n['archive']}"
          " · 페이지 맨 위 교체 + 섹션 추가 (사용자 칸 0건)")
    return 0


def cmd_notion_result(a):
    rd = run_dir(a.slug, a.run)
    if a.ok:
        if not a.report_page_url:
            print("오류: --ok에는 실행 결과 페이지 URL(--report-page-url)이 필요")
            return 1
        save(rd / "s5" / "notion-result.json", {"ok": True, "at": now(), "report_page_url": a.report_page_url})
    else:
        pend = load(proj(a.slug) / "notion-pending.json", []) or []
        pend.append({"run_id": a.run, "at": now(), "sync": str(rd / "s5" / "notion-sync.json")})
        save(proj(a.slug) / "notion-pending.json", pend)
        save(rd / "s5" / "notion-result.json", {"ok": False, "at": now()})
    print("기록 완료")
    return 0


def cmd_status(a):
    st = load(proj(a.slug) / "state.json", {}) or {}
    print(json.dumps(st, ensure_ascii=False, indent=2))
    if st.get("run_id"):
        j = load(run_dir(a.slug, st["run_id"]) / "s5" / "s5-judgement.json")
        if j:
            print(f"최근 결과: {j.get('status') or '실행 실패'} / 미해소 {len(j.get('unresolved', []))}건 / 필수 규칙 위반 {len(j.get('gr_fail', []))}건")
    return 0


def main():
    p = argparse.ArgumentParser(description="UX 검증 하네스")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("slug"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("state"); s.add_argument("action", choices=["start", "done", "fail"])
    s.add_argument("--slug", required=True); s.add_argument("--run"); s.add_argument("--stage")
    s.add_argument("--status"); s.add_argument("--reason"); s.set_defaults(fn=cmd_state)
    s = sub.add_parser("promote"); s.add_argument("--slug", required=True); s.add_argument("--run", required=True)
    s.add_argument("--what", choices=["sources", "impact-map"], required=True); s.set_defaults(fn=cmd_promote)
    for name, fn in (("hash", cmd_hash), ("finalize", cmd_finalize)):
        s = sub.add_parser(name); s.add_argument("--slug", required=True); s.add_argument("--run", required=True); s.set_defaults(fn=fn)
    s = sub.add_parser("notion-sync"); s.add_argument("--slug", required=True); s.add_argument("--run", required=True)
    s.add_argument("--stage", choices=["S1", "S2", "S3", "S4", "S5"], default="S5"); s.set_defaults(fn=cmd_notion_sync)
    s = sub.add_parser("gate"); s.add_argument("name", choices=["G0", "G1", "G2", "G3", "G4", "G5", "GR"])
    s.add_argument("--slug", required=True); s.add_argument("--run", default=""); s.set_defaults(fn=cmd_gate)
    s = sub.add_parser("notion-result"); s.add_argument("--slug", required=True); s.add_argument("--run", required=True)
    grp = s.add_mutually_exclusive_group(required=True); grp.add_argument("--ok", action="store_true"); grp.add_argument("--failed", action="store_true")
    s.add_argument("--report-page-url")
    s.set_defaults(fn=cmd_notion_result)
    s = sub.add_parser("status"); s.add_argument("--slug", required=True); s.set_defaults(fn=cmd_status)
    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
