"""한양대 HY-in 장학캘린더.

포털은 로그인이 필요하므로 서버가 학생 비밀번호를 갖지 않는다.
대신 로그인한 브라우저에서 web/tools/hyin-sync.js 를 실행하면 캘린더 전체(날짜별 조회 + 모집공지 상세)를
JSON 으로 만들어 /api/import/hyin 으로 올리거나 파일로 저장한다. 이 수집기는 가장 최근 JSON 을 읽는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..model import finalize, make_id, norm_date

ROOT = Path(__file__).resolve().parents[2] / "data"
TERM = {"10": "1학기", "20": "2학기", "15": "여름학기", "25": "겨울학기"}
JAEWON = {"O": "교외", "N": "국가", "I": "교내"}


def latest_file() -> Path | None:
    files = sorted((ROOT / "imports").glob("hyin_*.json")) if (ROOT / "imports").exists() else []
    if files:
        return files[-1]
    seed = ROOT / "seed" / "hyin_calendar_full.json"
    return seed if seed.exists() else None


def public_links() -> dict:
    p = ROOT / "seed" / "recruitment-connections.json"
    if not p.exists():
        return {}
    out = {}
    for r in json.loads(p.read_text())["records"]:
        if r.get("noticeUrls"):
            out[re.sub(r"\s", "", r["title"])] = [{"name": r.get("noticeTitle") or "공개 원문", "url": u} for u in r["noticeUrls"]]
    return out


def amount_from(text: str) -> str:
    for line in (text or "").splitlines():
        if re.search(r"(지원\s*금액|장학\s*금액|지원\s*내용|장학금\s*:|금\s*액)", line) and re.search(r"\d", line):
            return line.strip(" -·")[:200]
    m = re.search(r"[^\n]{0,30}\d[\d,.]*\s*(만|천만|백만)\s*원[^\n]{0,40}", text or "")
    return m.group(0).strip() if m else ""


def collect(online: bool = True):
    f = latest_file()
    if not f:
        return [], [{"source": "hyin", "ok": False, "count": 0, "mode": "none", "note": "HY-in 동기화 파일 없음"}]
    data = json.loads(f.read_text())
    links = public_links()
    out = []
    for x in data["records"]:
        d = x.get("detail") or {}
        text = d.get("text", "")
        kind = JAEWON.get(x.get("jaewon"), "")
        title = x.get("name") or (d.get("text","").split("\n")[0][:60]) or "한양대 장학"
        rec = {
            "id": make_id("hyin", x["year"], x["term"], x["cd"], x["seq"], x.get("campus")),
            "source": "hyin",
            "source_name": "한양대 HY-in 장학캘린더",
            "title": title,
            "org": title if kind == "교외" else "한양대학교",
            "org_type": {"교외": "민간·기업·대학", "국가": "한국장학재단", "교내": "대학(교내)"}.get(kind, "기타"),
            "category": "학자금" if "대출" in title else "장학금",
            "kind": f"{kind}장학 · {x['year']} {TERM.get(x['term'], x['term'])}",
            "level": "대학생",
            "school_types": ["특정대학"],
            "amount": amount_from(text),
            "selection": f"접수처: {d.get('office')}" if d.get("office") else "",
            "documents": "\n".join("○ " + s for s in d.get("docs", [])),
            "url": "https://portal.hanyang.ac.kr/",
            "apply_url": d.get("applyUrl") or "",
            "start": norm_date(x.get("start")),
            "end": norm_date(x.get("end")),
            "summary": text[:3000],
            "images": d.get("imgs", []),
            "files": d.get("files", [])[:1],  # 공지 첨부만. 나머지는 학생 본인 제출 파일
            "links": links.get(re.sub(r"\s", "", title), []),
            "region": "전국" if kind != "교내" else "서울",
            "district": "",
            "residence": "",
            "recommend": "학교 추천(학생지원팀 접수)" if kind == "교외" and d.get("office") and "재단" not in (d.get("office") or "") else "",
            "verified": True,
        }
        if kind == "교외":
            from ..regions import infer_region
            rec["region"], rec["district"] = infer_region(title, text[:400])
        out.append(finalize(rec))
    return out, [{"source": "hyin", "label": "한양대 HY-in 장학캘린더", "ok": True, "count": len(out), "mode": f.name,
                  "collectedAt": data.get("collectedAt")}]
