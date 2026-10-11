"""건국대학교(서울캠퍼스) 장학 공지 — 공개 게시판 RSS, 로그인 불필요. robots.txt 는 관리자 화면만 막는다.

목록은 RSS(최근 50개)에서, 본문은 공지 상세 화면에서 읽는다. 고정 공지의 게시 기간(topStartDt~topEndDt)은
대개 신청 기간과 같아서, 본문·제목에서 기간을 못 찾으면 그것을 쓴다.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import requests

from ..model import finalize, make_id, norm_date
from .period import period_from

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "konkuk.json"
BASE = "https://www.konkuk.ac.kr"
RSS = BASE + "/bbs/konkuk/235/rssList.do?row=50"
UA = "Mozilla/5.0 (compatible; JangakAlimiBot/1.0; +https://github.com/lussion629-creator/JangHak-Alim-e)"
WORK = re.compile(r"근로|장학조교|학생\s*조교|도우미|튜터")
INSIDE = re.compile(r"^\s*\[(교내|국가|근로|교내근로|국가근로|학자금|등록|발전기금)|건국|KU\s|교내|근로장학|국가장학|국가근로")
GLOCAL = re.compile(r"글로컬|GLOCAL|충주", re.I)


def _tag(it: str, name: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", it, re.S)
    v = (m.group(1) if m else "").strip()
    v = re.sub(r"^<!\[CDATA\[|\]\]>$", "", v)
    return html.unescape(v).strip()


def parse_rss(xml: str) -> list[dict]:
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        link = _tag(it, "link")
        m = re.search(r"/bbs/konkuk/235/(\d+)/artclView\.do", link)
        if not m:
            continue
        out.append({"sn": m.group(1), "title": _tag(it, "title"), "date": norm_date(_tag(it, "pubDate")[:10]),
                    "dept": _tag(it, "author"), "top": _tag(it, "topChk") == "FIXTOP",
                    "top_start": norm_date(_tag(it, "topStartDt")[:10]), "top_end": norm_date(_tag(it, "topEndDt")[:10])})
    return out


def view_url(sn: str) -> str:
    return f"{BASE}/bbs/konkuk/235/{sn}/artclView.do"


def fetch(known: dict) -> list[dict]:
    from .boards import allowed, text_of_html
    if not allowed(RSS):
        raise PermissionError("robots")
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR"})
    rows = parse_rss(s.get(RSS, timeout=25).text)
    n = 0
    for r in rows:
        if r["sn"] in known:
            r["detail"] = known[r["sn"]]
        elif n < 30:
            try:
                r["detail"] = {"text": text_of_html(s.get(view_url(r["sn"]), timeout=25).text)}
            except Exception:  # noqa: BLE001
                pass
            n += 1
    return rows


def collect(online: bool = True):
    from .boards import _org_from_title
    old = json.loads(SEED.read_text())["records"] if SEED.exists() else []
    known = {r["sn"]: r["detail"] for r in old if r.get("detail")}
    rows, mode = None, "seed"
    if online:
        try:
            rows = fetch(known)
            if rows:
                SEED.write_text(json.dumps({"records": rows}, ensure_ascii=False))
                mode = "online"
            else:
                rows = None
        except Exception:  # noqa: BLE001
            rows = None
    if rows is None:
        rows = old
    out = []
    for r in rows:
        t = re.sub(r"\[교외\[", "[교외][", r["title"])
        if GLOCAL.search(t) and not re.search(r"서울", t):
            continue  # 글로컬캠퍼스 공고
        body = (r.get("detail") or {}).get("text", "")
        start, end = period_from(t, body, r.get("date", ""))
        if not end and r.get("top") and r.get("top_end") and r["top_end"] != "9999-12-31":
            start, end = start or r.get("top_start", ""), r["top_end"]
        work = bool(WORK.search(t))
        ext = _org_from_title(re.sub(r"^\s*(\[[^\]]{1,10}\]\s*)+", "", t), "건국대학교", body)
        inside = not re.match(r"^\s*\[교외", t) and (ext == "건국대학교" or bool(INSIDE.search(t)))
        if not inside and ext == "건국대학교":
            ext = ""
        out.append(finalize({
            "id": make_id("konkuk", r["sn"]), "source": "konkuk", "source_name": "건국대 장학공지",
            "title": t, "org": "건국대학교" if inside else ext, "org_type": "대학(교내)" if inside else "민간·기업·대학",
            "category": "근로장학" if work else ("학자금" if "대출" in t else "장학금"), "kind": "교내근로" if work else "공고",
            "level": "대학원생" if re.search(r"대학원생|석사|박사", t) and not re.search(r"학부", t) else "대학생",
            "school_types": ["4년제(5~6년제포함)"] if inside else [], "region": "서울" if inside else "", "district": "광진구" if inside else "",
            "url": view_url(r["sn"]), "posted": r.get("date", ""), "start": start, "end": end,
            "summary": body, "selection": ("담당: " + r["dept"]) if r.get("dept") else "", "verified": True,
        }))
    return out, [{"source": "konkuk", "label": "건국대 장학공지", "ok": bool(out), "count": len(out), "mode": mode}]
