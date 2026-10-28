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
USER_FIELDS = {"수정 완료", "컨펌 완료", "결정 메모"}
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
        if (v == "NEEDS_REVIEW" and not r.get("rule_ref") and n.get("컨펌 완료")
                and (n.get("결정 메모") or "").strip()):
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
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', line))
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
    def __init__(self, slug, run):
        s1 = load(run_dir(slug, run) / "s1" / "s1-context.json", {}) or {}
        self.node, self.screen, self.plat = {}, {}, {}
        for s in s1.get("screens", []):
            names = [f["name"] for f in s.get("frames", [])] or [s.get("name")]
            self.screen[s["id"]] = names
            for f in s.get("frames", []):
                self.node[f["node_id"]] = f["name"]
                self.plat[f["name"]] = s.get("platform")
        self.src = {x["id"]: x.get("title", x["id"]) for x in source_index(slug, run).get("sources", [])}
        tops, tags, self.owner = _figma_layout(slug)
        self.tops = tops
        self.category, self.frame_tag = self._tags(tops, tags)

    def _tags(self, tops, tags):
        cat, ftag = {}, {}
        frames = [(nid, tops[nid]) for nid in self.node if nid in tops]
        def covering(t):
            return [g for g in tags if g["h"] < 1000 and g["text"] and g["y"] < t["y"]
                    and g["x"] < t["x"] + t["w"] and g["x"] + g["w"] > t["x"]]
        base = {}
        for nid, t in frames:
            near = [g for g in covering(t) if t["y"] - g["y"] < 400]
            if near:
                base.setdefault(self.plat.get(self.node[nid]), []).append(min(g["h"] for g in near))
        med = {p: sorted(v)[len(v) // 2] for p, v in base.items()}
        for nid, t in frames:
            name = self.node[nid]
            h0 = med.get(self.plat.get(name), 0) or 0
            cands = covering(t)
            secs = [g for g in cands if h0 and g["h"] >= 1.4 * h0]
            own = [g for g in cands if not (h0 and g["h"] >= 1.4 * h0) and t["y"] - g["y"] < 400]
            if secs:
                cat[name] = max(secs, key=lambda g: g["y"])["text"]
            if own:
                ftag[name] = max(own, key=lambda g: g["y"])["text"]
        return cat, ftag

    def frames(self, r):
        names = [self.node.get(n) or self.node.get(self.owner.get(n, ""), None) for n in r.get("figma_node_ids") or []]
        names = [n for n in names if n]
        if not names:
            for sid in r.get("screen_ids") or []:
                names += self.screen.get(sid, [])
        seen = []
        for n in names:
            if n not in seen:
                seen.append(n)
        return seen

    def frame_label(self, names, cap=4):
        names = list(dict.fromkeys(names))
        if not names:
            return "(특정 프레임 없음 · 전체 화면)"
        return ", ".join(names[:cap]) + (f" 외 {len(names) - cap}개" if len(names) > cap else "")

    def text(self, s):
        if not s:
            return s
        s = str(s)

        def node_sub(m):
            nid = m.group(0)
            name = self.node.get(nid) or self.node.get(self.owner.get(nid, ""))
            if not name and nid in self.tops and self.tops[nid]["name"] not in ("TAG",):
                name = self.tops[nid]["name"]
            return f"「{name}」" if name else nid
        s = re.sub(r"(?<![\d:])\d+:\d+(?![\d:])", node_sub, s)
        s = re.sub(r"(?<![A-Za-z])(APP|WEB)-(\d+)(?!\d)",
                   lambda m: f"「{self.screen[m.group(0)][0]}」" if m.group(0) in self.screen else m.group(0), s)
        s = re.sub(r"「([^」]+)」\s*\(\s*\1\s*\)", r"「\1」", s)   # 「이름」 (이름) 중복 제거
        return s

    def evidence(self, e):
        sid, loc = e.get("source_id"), e.get("locator") or ""
        m = re.search(r"\b\d+:\d+\b", loc)
        if m and (m.group(0) in self.node or self.owner.get(m.group(0)) in self.node or m.group(0) in self.tops):
            return f"Figma {self.text(m.group(0))}"
        return f"{self.src.get(sid, sid)} {self.text(loc)}".strip()

    def categories(self, names):
        out = []
        for n in names:
            c = self.category.get(n)
            if c and c not in out:
                out.append(c)
        return out or ["분류 없음"]

    def tags(self, names):
        out = []
        for n in names:
            t = self.frame_tag.get(n)
            if t and t not in out:
                out.append(t)
        return ", ".join(out)


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
        L.append("- ⚠ Notion 검토 사항을 읽지 못해 이번 실행에서는 수정 완료·컨펌 완료를 해소로 인정하지 않았다.")
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
        L.append("## 미승인 사유 (카테고리별 검토 필요 항목)")
        groups = {}
        for u in judgement["unresolved"]:
            r = by_id[u["id"]]
            names = D.frames(r)
            groups.setdefault(D.categories(names)[0], []).append((u, r, names))
        for cat in sorted(groups):
            L.append(f"### {cat} ({len(groups[cat])}건)")
            L.append("| 검토 사항(프레임) | 판정 유형 | 검토 내용 | 왜 | 근거 | 영향 화면 | 후속 조치 |")
            L.append("|---|---|---|---|---|---|---|")
            for u, r, names in groups[cat]:
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
    L.append("## 전체 항목 (카테고리별)")
    groups = {}
    for r in recs:
        names = D.frames(r)
        groups.setdefault(D.categories(names)[0], []).append((r, names))
    for cat in sorted(groups):
        L.append(f"### {cat}")
        L.append("| 검토 사항(프레임) | 판정 | 판정 유형 | 규칙 | 검토 내용 | 근거 |")
        L.append("|---|---|---|---|---|---|")
        for r, names in groups[cat]:
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

def cmd_notion_sync(a):
    rd = run_dir(a.slug, a.run)
    cfg = load(proj(a.slug) / "project.json")
    labels = {p["code"]: p["label"] for p in cfg["platforms"]}
    rule_opts = cfg.get("notion", {}).get("rule_options", {})
    final = {r["id"]: r for r in load(rd / "s5" / "final.json")["records"]}
    j = load(rd / "s5" / "s5-judgement.json")
    inputs = notion_inputs(a.slug, a.run)
    D = Display(a.slug, a.run)
    ops = []
    for u in j["unresolved"]:
        r = final[u["id"]]
        rule = rule_opts.get((r.get("rule_ref") or "").split("-")[0], "해당 없음") if r.get("rule_ref") else "해당 없음"
        n = inputs.get(u["id"])
        recheck = "미실행"
        if n and n.get("수정 완료"):
            recheck = "여전히 FAIL" if u["verdict"] == "FAIL" else "미실행"
        names = D.frames(r)
        impact = [nm for s in u["impact_screens"] for nm in D.screen.get(s, [s])]
        props = {
            "검토 사항": D.frame_label(names), "검토 내용": D.text(u["what"]), "항목 ID": u["id"],
            "판정": VERDICT_KO[u["verdict"]], "판정 유형": VTYPE_KO[u["verdict"]],
            "카테고리": D.categories(names), "프레임 태그": D.tags(names),
            "단계": STAGE_LABEL.get(r.get("stage"), "S4 영향 분석"),
            "플랫폼": [labels[p] for p in r.get("platform") or [] if p in labels],
            "영향 화면": D.frame_label(impact, cap=8) if impact else "",
            "필수 규칙": rule, "사유": D.text(u["why"]),
            "근거": "; ".join(D.evidence(e) for e in r.get("evidence") or []),
            "후속 조치": D.text(u["follow_up"]), "재검증 결과": recheck, "최근 실행": a.run,
        }
        ops.append({"op": "update" if n else "create", "page_url": n.get("page_url") if n else None,
                    "item_id": u["id"], "properties": props})
    unresolved_ids = {u["id"] for u in j["unresolved"]}
    for item_id, n in inputs.items():
        if item_id not in unresolved_ids:
            ops.append({"op": "update", "page_url": n.get("page_url"), "item_id": item_id,
                        "properties": {"판정": "승인", "판정 유형": "", "재검증 결과": "PASS", "최근 실행": a.run}})
    categories = sorted({c for op in ops for c in op["properties"].get("카테고리", [])})
    for op in ops:
        bad = USER_FIELDS & set(op["properties"])
        if bad:
            print(f"오류: 사용자 칸 {bad} 쓰기 시도")
            return 1
    save(rd / "s5" / "notion-sync.json", {"run_id": a.run, "data_source": cfg["notion"]["review_data_source"],
                                          "categories": categories, "ops": ops})
    print(f"Notion 반영 계획: 생성 {sum(o['op'] == 'create' for o in ops)} / 갱신 {sum(o['op'] == 'update' for o in ops)} (사용자 칸 0건)")
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
    for name, fn in (("hash", cmd_hash), ("finalize", cmd_finalize), ("notion-sync", cmd_notion_sync)):
        s = sub.add_parser(name); s.add_argument("--slug", required=True); s.add_argument("--run", required=True); s.set_defaults(fn=fn)
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
