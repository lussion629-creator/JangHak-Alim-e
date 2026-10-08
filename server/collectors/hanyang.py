"""한양대학교 공개 공지사항 '장학/등록' 분류 (로그인 불필요)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from ..model import finalize, make_id, norm_date

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "hanyang_public.json"
PID = "kr_ac_hanyang_noticeBoard_web_portlet_NoticeBoardPortlet"
LIST = ("https://www.hanyang.ac.kr/notice_all?p_p_id={p}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        "&_{p}_action=view&_{p}_sCategoryId=224311300&_{p}_cur={page}")
VIEW = ("https://www.hanyang.ac.kr/notice_all?p_p_id={p}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        "&_{p}_action=view_message&_{p}_sCategoryId=224311300&_{p}_entryId={id}")
SKIP = re.compile(r"(등록안내|증명발급|서비스 오픈|우편물실|근로장학생)")


def fetch(pages=8):
    from bs4 import BeautifulSoup
    rows = []
    for page in range(1, pages + 1):
        html = requests.get(LIST.format(p=PID, page=page), timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".hyu-list-body-item")
        if not items:
            break
        for it in items:
            a = it.select_one("h4 a")
            if not a:
                continue
            m = re.search(r"entryId=(\d+)", a.get("href", ""))
            badges = [b.get("data-itemvalue") for b in it.select("[data-itemvalue]")]
            spans = [s.get_text(strip=True) for s in it.select("p > span:not(.hyu-badge)")]
            dt = it.select_one(".date")
            rows.append({"id": m.group(1) if m else a.get_text(strip=True), "title": a.get_text(strip=True),
                         "campus": badges[0] if badges else "", "dept": spans[0] if spans else "",
                         "date": norm_date(dt.get_text() if dt else "")})
    return rows


def collect(online: bool = True):
    rows, mode = None, "seed"
    if online:
        try:
            rows = fetch()
            SEED.write_text(json.dumps({"records": rows}, ensure_ascii=False))
            mode = "online"
        except Exception:  # noqa: BLE001
            rows = None
    if rows is None:
        rows = json.loads(SEED.read_text())["records"] if SEED.exists() else []
    out = []
    seen = set()
    for r in rows:
        if r["id"] in seen or SKIP.search(r["title"]):
            continue
        seen.add(r["id"])
        m = re.search(r"\(?(20\d{2})\.\s?(\d{1,2})\.\s?(\d{1,2})\.?[^~]*~\s*(20\d{2})\.\s?(\d{1,2})\.\s?(\d{1,2})", r["title"])
        start = end = ""
        if m:
            start = norm_date("-".join(m.groups()[:3]))
            end = norm_date("-".join(m.groups()[3:]))
        out.append(finalize({
            "id": make_id("hanyang", r["id"]), "source": "hanyang", "source_name": "한양대 공지사항(장학/등록)",
            "title": r["title"], "org": "한양대학교" + (" " + r["campus"] if r.get("campus") in ("서울", "ERICA") else ""),
            "org_type": "대학(교내)", "category": "학자금" if "대출" in r["title"] else "장학금", "kind": "공고",
            "level": "대학생", "school_types": ["특정대학"], "region": "서울" if r.get("campus") != "ERICA" else "경기",
            "selection": "담당: " + r.get("dept", ""), "url": VIEW.format(p=PID, id=r["id"]), "posted": r["date"],
            "start": start, "end": end, "files": r.get("files", []), "verified": True,
        }))
    return out, [{"source": "hanyang", "label": "한양대 공개 공지(장학/등록)", "ok": True, "count": len(out), "mode": mode}]
