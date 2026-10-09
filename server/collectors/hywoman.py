"""한양여자대학교 장학공지 (공개 게시판, 로그인 불필요).

게시판 화면이 부르는 목록 API(/ajaxf/FrBoardSvc/bbsViewList.do)를 그대로 쓴다. 본문(CONTENTS)도 함께 온다.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import requests

from ..model import finalize, make_id, norm_date

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "hywoman.json"
BASE = "https://www.hywoman.ac.kr"
MENU = BASE + "/ko/cms/FrCon/index.do?MENU_ID=3530"
API = BASE + "/ajaxf/FrBoardSvc/bbsViewList.do"
VIEW = BASE + "/ko/cms/CmnCommonCon/mainLink.do?GBN=BA&TEMP_CODE=KOR_B&BASE_SITE_NO=2&CONFIG_CD=M0107&CONFIG_SEQ=2&SUB_SEQ=2&SITE_NO=2&BOARD_SEQ=8&BBS_SEQ={seq}"
UA = "Mozilla/5.0 (compatible; JangakAlimiBot/1.0; +https://github.com/lussion629-creator/JangHak-Alim-e)"


def fetch(pages: int = 4) -> list[dict]:
    from .boards import allowed
    if not allowed(MENU):
        raise PermissionError("robots")
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR"})
    s.get(MENU, timeout=20)
    rows = []
    for p in range(1, pages + 1):
        data = {"pageNo": p, "pagePerCnt": 15, "MENU_ID": 3530, "CONTENTS_NO": "", "SITE_NO": 2, "BOARD_SEQ": 8, "BBS_SEQ": "",
                "P_BBS_SEQ": "", "PWD": "", "CATE_SEQ": "", "SEARCH_FLD": "", "SHOWTYPE": "B0304", "SEARCH": ""}
        r = s.post(API, data=data, timeout=20, headers={"X-Requested-With": "XMLHttpRequest", "Referer": MENU})
        lst = (r.json().get("data") or {}).get("list") or []
        if not lst:
            break
        for x in lst:
            rows.append({"seq": x.get("BBS_SEQ"), "title": (x.get("SUBJECT") or "").strip(), "date": (x.get("WRITE_DT") or "")[:10],
                         "dept": x.get("DEPT_NM") or x.get("WRITER") or x.get("REG_NM") or "", "contents": text_of(x.get("CONTENTS") or "")[:3000]})
    return rows


def text_of(escaped: str) -> str:
    from bs4 import BeautifulSoup
    from ..model import html_block_text
    return html_block_text(BeautifulSoup(html.unescape(escaped), "html.parser"))


def _range(title: str, posted: str):
    """제목의 '(~9.9까지)', '(~25. 1. 13.)', '(25. 12. 22.~26. 1. 8.)' 에서 마감일을 읽는다."""
    m = re.search(r"~\s*(?:(\d{2,4})\s*[./-]\s*)?(\d{1,2})\s*[./]\s*(\d{1,2})", title)
    if not m or not posted:
        return ""
    mo, d = int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    if m.group(1):
        y = int(m.group(1)); y = y + 2000 if y < 100 else y
    else:
        y = int(posted[:4])
        if mo < int(posted[5:7]) - 6:
            y += 1
    return f"{y}-{mo:02d}-{d:02d}"


def collect(online: bool = True):
    rows, mode = None, "seed"
    if online:
        try:
            rows = fetch()
            if rows:
                SEED.write_text(json.dumps({"records": rows}, ensure_ascii=False))
                mode = "online"
            else:
                rows = None
        except Exception:  # noqa: BLE001
            rows = None
    if rows is None:
        rows = json.loads(SEED.read_text())["records"] if SEED.exists() else []
    out = []
    for r in rows:
        t = r["title"]
        work = bool(re.search(r"근로", t))
        out.append(finalize({
            "id": make_id("hywoman", r["seq"]), "source": "hywoman", "source_name": "한양여자대학교 장학공지",
            "title": t, "org": "한양여자대학교", "org_type": "대학(교내)",
            "category": "근로장학" if work else ("학자금" if "대출" in t else "장학금"),
            "kind": "교내근로" if work else "공고", "level": "대학생", "school_types": ["전문대(2~3년제)"],
            "region": "서울", "district": "성동구", "url": VIEW.format(seq=r["seq"]), "posted": norm_date(r.get("date")),
            "end": _range(t, r.get("date", "")), "summary": r.get("contents", ""),
            "selection": "담당: " + r["dept"] if r.get("dept") else "", "verified": True,
        }))
    return out, [{"source": "hywoman", "label": "한양여대 장학공지", "ok": bool(out), "count": len(out), "mode": mode}]
