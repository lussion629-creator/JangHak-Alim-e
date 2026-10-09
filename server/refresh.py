"""전체 수집 → 병합 → DB 저장 → 웹용 JSON 내보내기.

  python -m server.refresh            # 온라인 수집 (기본)
  python -m server.refresh --offline  # 저장된 사본만으로 DB/JSON 재생성
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import logging
import re
import sqlite3
from datetime import date
from pathlib import Path

from .collectors import boards, dreamspon, gov24, hanyang, hywoman, hyin, kangwon, kosaf, kosaf_hist, legacy, sogang
from .merge import for_schools, merge
from .model import summarize_body, expected_next, now_iso, status_of, support_of

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "scholarships.db"
WEB_DATA = ROOT / "web" / "data"
COLLECTORS = [("kosaf", kosaf), ("kosaf_hist", kosaf_hist), ("hyin", hyin), ("hanyang", hanyang), ("hywoman", hywoman), ("kangwon", kangwon), ("sogang", sogang), ("board", boards), ("gov24", gov24), ("legacy", legacy), ("dreamspon", dreamspon)]
log = logging.getLogger("refresh")


def connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript("""
    create table if not exists scholarships(
      id text primary key, source text, data text not null, hash text,
      first_seen text, last_seen text, changed_at text, active integer default 1);
    create index if not exists sch_source on scholarships(source);
    create table if not exists runs(id integer primary key autoincrement, at text, report text);
    create table if not exists changes(id integer primary key autoincrement, at text, sid text, kind text, title text);
    """)
    return con


def _key(title: str) -> str:
    return re.sub(r"[\s\[\]()<>·ㆍ,._\-~!?\"'「」『』]|20\d\d(년|학년도)?|\d학기|모집|선발|안내|공고|신규|장학생|장학금", "", title or "")


def dedupe(recs: list[dict]) -> list[dict]:
    """같은 공고가 여러 대학 게시판에 올라온 경우 하나로 합치고 출처 링크만 모은다."""
    by_id, by_key = {}, {}
    for r in recs:
        if r["id"] in by_id:
            continue
        if r["source"] in ("board", "legacy"):
            k = _key(r["title"])
            if len(k) >= 4 and k in by_key:
                keep = by_key[k]
                link = {"name": r["source_name"], "url": r["url"]}
                if r["url"] and all(l.get("url") != r["url"] for l in keep["links"]) and len(keep["links"]) < 12:
                    keep["links"].append(link)
                if not keep.get("end") and r.get("end"):
                    keep["end"] = r["end"]
                continue
            by_key[k] = r
        by_id[r["id"]] = r
    return list(by_id.values())


def run(online: bool = True) -> dict:
    started = now_iso()
    allrecs, report = [], []
    for name, mod in COLLECTORS:
        try:
            recs, rep = mod.collect(online=online)
        except Exception as e:  # noqa: BLE001
            log.exception("collector %s failed", name)
            recs, rep = [], [{"source": name, "ok": False, "count": 0, "error": str(e)[:200]}]
        allrecs.extend(recs)
        report.extend(rep)
    recs = dedupe(allrecs)
    con = connect()
    now = now_iso()
    existing = {row[0]: (row[1], row[2]) for row in con.execute("select id, hash, first_seen from scholarships")}
    new = changed = 0
    seen_ids = set()
    for r in recs:
        seen_ids.add(r["id"])
        old = existing.get(r["id"])
        if old is None:
            new += 1
            r["first_seen"] = now
            con.execute("insert into scholarships values(?,?,?,?,?,?,?,1)", (r["id"], r["source"], json.dumps(r, ensure_ascii=False), r["hash"], now, now, now))
            if existing:
                con.execute("insert into changes(at,sid,kind,title) values(?,?,?,?)", (now, r["id"], "new", r["title"]))
        else:
            r["first_seen"] = old[1]
            if old[0] != r["hash"]:
                changed += 1
                con.execute("update scholarships set data=?, hash=?, last_seen=?, changed_at=?, active=1 where id=?", (json.dumps(r, ensure_ascii=False), r["hash"], now, now, r["id"]))
                con.execute("insert into changes(at,sid,kind,title) values(?,?,?,?)", (now, r["id"], "updated", r["title"]))
            else:
                con.execute("update scholarships set last_seen=?, active=1 where id=?", (now, r["id"]))
    # 이번 수집에서 사라진 항목: 해당 수집기가 성공했을 때만 비활성화
    ok_sources = {x["source"] for x in report if x.get("ok")}
    for sid, src in con.execute("select id, source from scholarships where active=1").fetchall():
        if sid not in seen_ids and (src in ok_sources or src.startswith("kosaf") and "kosaf_univ" in ok_sources):
            con.execute("update scholarships set active=0 where id=?", (sid,))
    summary = {"startedAt": started, "finishedAt": now_iso(), "online": online, "total": len(recs), "new": new,
               "changed": changed, "sources": report}
    con.execute("insert into runs(at, report) values(?,?)", (now, json.dumps(summary, ensure_ascii=False)))
    con.commit()
    export(con, summary)
    con.close()
    return summary


def export(con: sqlite3.Connection, summary: dict):
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    rows = []
    hy_titles = {json.loads(d).get("title") for (d,) in con.execute("select data from scholarships where active=1 and source='hanyang'")}
    for data, first_seen, changed_at in con.execute("select data, first_seen, changed_at from scholarships where active=1"):
        r = json.loads(data)
        r.pop("hash", None)
        if r.get("source") in ("hyin", "hanyang", "legacy", "board") and re.search(r"ERICA|에리카", (r.get("title") or "") + " " + (r.get("org") or "")):
            continue  # ERICA 캠퍼스 공고는 넣지 않는다
        if r.get("source") == "legacy":
            if r.get("title") in hy_titles:
                continue  # 한양대 공지에서 직접 가져온 같은 글이 있다
            r["posted"] = ""  # 기존 수집본의 '등록일'은 실제 공고일이 아니라 옮겨 담은 날짜
        if r.get("source") == "board":
            t = re.sub(r"\s*(Attachment|첨부파일|새글|NEW|N)\s*$|[}\]]+$|\.hwpx?\"\s*/?>.*$", "", r.get("title", ""))
            t = re.sub(r"\s+(학생지원팀|장학팀|학생복지팀|장학복지팀)\s+20\d\d-\d\d-\d\d\s+\d+$", "", t).strip()
            t = re.sub(r"^((공지|NOTICE|필독|중요)\s*)+", "", t)
            t = re.sub(r"\s+20\d\d([.\-]\d{1,2}){0,2}\.?$|\s+\d{1,4}$", "", t).strip()
            if len(t) > 40:  # 제목 뒤에 본문 첫 줄이 붙어 온 경우 잘라낸다
                t = re.split(r"\s+(?:가\.|1\.|□|○|■|❍)\s", t)[0]
                m = re.match(r"^(.{8,90}?(?:안내|공고)(?:\s*\([^)]{0,20}\))?)(?=\s|$)", t)
                t = m.group(1).strip() if m else t[:60]
            r["title"] = t
        if r.get("source") == "board" and r.get("org_type") == "대학 게시판":
            ext = re.search(r"재단|장학회|육영회|협회|구민|시민|군민|도민|공사|공단|진흥원|은행|정부초청|교육청|시청|군청|구청|도청|특별자치|\[교외|교외\]|\[외부|홍보", t) \
                and not re.search(r"교내|근로|본교|동문|발전기금|면학|가계곤란|신입생|사정관|가족|학과|학부|대학원|어학우수|우수연구|자체선발", t)
            r["_relay_ok"] = bool(ext)
            r["_relay_school"] = r.get("source_name") or ""
            if ext and r.get("org") == r.get("source_name"):
                r["org"] = ""  # 공고를 옮겨 실은 대학 이름은 운영기관이 아니므로 숨긴다
        r["_hy"] = "한양대" in (r.get("source_name") or "") or r.get("source") in ("hyin", "hanyang")
        r.pop("source_name", None)  # 화면에 출처 이름을 노출하지 않는다
        r["links"] = [{"name": "공고 원문", "url": l["url"]} for l in r.get("links", []) if l.get("url")]
        r["first_seen"], r["changed_at"] = first_seen, changed_at
        r["status"] = status_of(r.get("start"), r.get("end"), today, r.get("posted", ""))
        r["support"] = support_of(r)
        r["next"] = expected_next(r.get("start"), r.get("end"), today) if r["status"] == "마감" and r["source"].startswith(("kosaf", "hyin")) else ""
        rows.append(r)
    # 게시판 본문: 메뉴·꼬리말을 걷어내고 필요한 항목만 남긴다
    for r in rows:
        if r.get("source") in ("board", "legacy", "hanyang", "hywoman", "kangwon", "sogang") and r.get("summary"):
            sm = summarize_body(r["summary"], r.get("title", ""))
            r["summary"] = sm["text"]
            f = sm["fields"]
            if f.get("대상") and (not r.get("target") or len(r.get("target", "")) > 700):
                r["target"] = f["대상"]
            if f.get("지원 내용") and not r.get("amount"):
                r["amount"] = f["지원 내용"]
            if f.get("선발 인원") and not r.get("quota"):
                r["quota"] = f["선발 인원"]
            if f.get("제출 서류") and not r.get("documents"):
                r["documents"] = f["제출 서류"]
            if f.get("선발 방법") and not r.get("selection"):
                r["selection"] = f["선발 방법"]
            if r.get("target") and not sm["text"]:
                r["target"] = ""  # 메뉴 글자만 있던 본문에서 뽑은 대상은 버린다
            if not r.get("amount_won") and r.get("amount"):
                from .model import parse_amount
                r["amount_won"] = parse_amount(r["amount"])
    ap = ROOT / "data" / "registry" / "aliases.json"
    aliases = {k: v for k, v in (json.loads(ap.read_text()) if ap.exists() else {}).items() if not k.startswith("_")}
    for r in rows:
        if r.get("source") in ("board", "legacy", "hanyang"):
            for word, org in aliases.items():
                if word in r.get("title", ""):
                    r["org"] = org
                    break
    rows = merge(rows)  # 같은 장학금이 여러 곳에 올라온 경우 하나만 남긴다
    # 최근 7일 안에 새로 들어오거나 바뀐 장학금 표시 (합쳐진 공고 중 하나라도 해당하면)
    from datetime import timedelta
    since = (date.today() - timedelta(days=7)).isoformat()
    recent = {}
    for at, sid, kind in con.execute("select at, sid, kind from changes where at >= ? order by id", (since,)):
        if kind == "new" or sid not in recent:
            recent[sid] = (kind, at[:10])
    for r in rows:
        hy = r.pop("_hyids", None)
        if hy:
            r["hy"] = hy  # 휴대폰 앱이 직접 불러온 포털 캘린더와 같은 공고인지 맞춰 보는 번호
        hits = [recent[i] for i in r.pop("_ids", []) if i in recent]
        if hits:
            kind = "new" if any(k == "new" for k, _ in hits) else "updated"
            r["fresh"] = {"kind": kind, "at": max(a for _, a in hits)}
    rows = for_schools(rows)  # 앱이 지원하는 학교(한양대·한양여대·강원대 삼척·서강대) 학생 누구도 지원할 수 없는 장학금 제외
    for r in rows:
        r["status"] = status_of(r.get("start"), r.get("end"), today, r.get("posted", ""))
        r["support"] = support_of(r)
        r["next"] = expected_next(r.get("start"), r.get("end"), today) if r["status"] == "마감" and r["source"].startswith(("kosaf", "hyin")) else ""
    rows.sort(key=lambda r: ({"모집중": 0, "예정": 1, "상시/미정": 2, "마감": 3}[r["status"]], r.get("end") or "9999"))
    payload = json.dumps({"generatedAt": summary["finishedAt"], "count": len(rows), "items": rows}, ensure_ascii=False, separators=(",", ":"))
    (WEB_DATA / "scholarships.json").write_text(payload)
    (WEB_DATA / "scholarships.json.gz").write_bytes(gzip.compress(payload.encode()))
    changes = [dict(zip(("at", "id", "kind", "title"), c)) for c in con.execute("select at,sid,kind,title from changes order by id desc limit 200")]
    meta = {k: summary[k] for k in ("finishedAt", "total", "new", "changed")}
    # 휴대폰 앱의 알림 작업용: 지금 모집 중·예정인 장학의 짧은 목록
    meta["open"] = [{"id": r["id"], "t": r["title"][:80], "o": (r.get("org") or "")[:40], "s": r.get("support") or [], "e": r.get("end") or "", "f": r.get("for") or []}
                    for r in rows if r.get("status") in ("모집중", "예정")][:400]
    meta["changes"] = changes
    (ROOT / "data" / "registry" / "last_run.json").write_text(json.dumps({**summary, "registry": _registry_summary()}, ensure_ascii=False, indent=1))
    (WEB_DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))


def _registry_summary():
    p = ROOT / "data" / "registry" / "sources.json"
    st = ROOT / "data" / "registry" / "status.json"
    if not p.exists():
        return {}
    srcs = json.loads(p.read_text())
    status = {s["id"]: s for s in json.loads(st.read_text())} if st.exists() else {}
    return {"total": len(srcs), "enabled": sum(1 for s in srcs if s.get("enabled")),
            "sources": [{"name": s["name"], "type": s["type"], "region": s.get("region", ""), "url": s.get("notice_url") or s.get("homepage"),
                         "enabled": s.get("enabled"), "verified": s.get("verified"), "ok": status.get(s["id"], {}).get("ok"),
                         "count": status.get(s["id"], {}).get("count")} for s in srcs]}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    s = run(online=not a.offline)
    print(json.dumps({k: v for k, v in s.items() if k != "sources"}, ensure_ascii=False))
    for x in s["sources"]:
        print(" ", x)
