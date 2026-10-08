"""전체 수집 → 병합 → DB 저장 → 웹용 JSON 내보내기.

  python -m server.refresh            # 온라인 수집 (기본)
  python -m server.refresh --offline  # 저장된 사본만으로 DB/JSON 재생성
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import sqlite3
from datetime import date
from pathlib import Path

from .collectors import boards, gov24, hanyang, hyin, kosaf, legacy
from .model import expected_next, now_iso, status_of

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "scholarships.db"
WEB_DATA = ROOT / "web" / "data"
COLLECTORS = [("kosaf", kosaf), ("hyin", hyin), ("hanyang", hanyang), ("board", boards), ("gov24", gov24), ("legacy", legacy)]
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
    for data, first_seen, changed_at in con.execute("select data, first_seen, changed_at from scholarships where active=1"):
        r = json.loads(data)
        r.pop("hash", None)
        r.pop("source_name", None)  # 화면에 출처 이름을 노출하지 않는다
        r["links"] = [{"name": "공고 원문", "url": l["url"]} for l in r.get("links", []) if l.get("url")]
        r["first_seen"], r["changed_at"] = first_seen, changed_at
        r["status"] = status_of(r.get("start"), r.get("end"), today)
        r["next"] = expected_next(r.get("start"), r.get("end"), today) if r["status"] == "마감" and r["source"].startswith(("kosaf", "hyin")) else ""
        rows.append(r)
    rows.sort(key=lambda r: ({"모집중": 0, "예정": 1, "상시/미정": 2, "마감": 3}[r["status"]], r.get("end") or "9999"))
    payload = json.dumps({"generatedAt": summary["finishedAt"], "count": len(rows), "items": rows}, ensure_ascii=False, separators=(",", ":"))
    (WEB_DATA / "scholarships.json").write_text(payload)
    (WEB_DATA / "scholarships.json.gz").write_bytes(gzip.compress(payload.encode()))
    changes = [dict(zip(("at", "id", "kind", "title"), c)) for c in con.execute("select at,sid,kind,title from changes order by id desc limit 200")]
    meta = {k: summary[k] for k in ("finishedAt", "total", "new", "changed")}
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
