"""드림스폰 공개 장학 목록에서 새 장학금을 찾아내고, 원본(운영기관) 링크로 연결한다.

- 로그인 없이 보이는 목록(장학명·기관명·모집 상태)과 상세의 신청기간만 읽는다.
- 드림스폰이 쓴 소개글이나 요약은 복제하지 않는다. 앱에는 운영기관 원본 링크만 둔다.
- robots.txt 를 지키고, 요청 사이에 쉬어 간다.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from ..model import finalize, make_id, norm_date
from .boards import UA, allowed

BASE = "https://www.dreamspon.com"
ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "data" / "seed" / "dreamspon.json"
SCHOOL_TAGS = {"#대학생": "4년제(5~6년제포함)", "#4년제": "4년제(5~6년제포함)", "#전문대": "전문대(2~3년제)", "#전문대생": "전문대(2~3년제)",
               "#대학원생": "일반대학원", "#석사": "일반대학원", "#박사과정": "일반대학원"}
SUPPORT_TAG = {"#주거지원": "주거비 지원", "#대출지원": "학자금 대출·이자 지원", "#생활비": "생활비 지원", "#근로장학": "근로장학"}
COND_TAG = {"#지역기준": "거주 지역 조건 있음", "#전공기준": "전공 조건 있음", "#성적기준": "성적 조건 있음",
            "#소득기준": "소득 조건 있음", "#특수계층": "특정 계층 대상", "#추천서": "추천서 필요", "#산학장학": "산학 협약 장학"}


def _get(url: str) -> str:
    if not allowed(url):
        return ""
    r = requests.get(url, timeout=20, headers={"User-Agent": UA})
    r.raise_for_status()
    return r.text


def fetch(max_pages: int = 15) -> list[dict]:
    from bs4 import BeautifulSoup
    rows = []
    for p in range(1, max_pages + 1):
        soup = BeautifulSoup(_get(f"{BASE}/scholarship/list.html?page={p}"), "html.parser")
        trs = [td.find_parent("tr") for td in soup.select("td.td_subject")]
        if not trs:
            break
        active = 0
        for tr in trs:
            a = tr.select_one(".title a")
            if not a:
                continue
            m = re.search(r"idx=(\d+)", a.get("href", ""))
            tds = tr.find_all("td")
            state = (tr.select_one(".state").get_text(strip=True) if tr.select_one(".state") else "")
            day = (tr.select_one(".count").get_text(strip=True) if tr.select_one(".count") else "")
            if state != "모집마감":
                active += 1
            rows.append({"idx": m.group(1) if m else "", "title": a.get_text(" ", strip=True),
                         "org": tds[1].get_text(" ", strip=True) if len(tds) > 1 else "",
                         "state": state, "day": day, "tags": [s.get_text(strip=True) for s in tr.select(".hashtag span")]})
        if not active:
            break  # 이 쪽부터는 모두 마감된 장학
        time.sleep(0.5)
    # 모집 중인 장학만 상세의 신청기간을 읽는다 (공개된 부분만)
    for r in rows:
        if r["state"] == "모집마감" or not r["idx"]:
            continue
        try:
            text = re.sub(r"\s+", " ", BeautifulSoup(_get(f"{BASE}/scholarship/view.html?idx={r['idx']}"), "html.parser").get_text(" "))
        except Exception:  # noqa: BLE001
            continue
        m = re.search(r"신청기간\s*(20\d\d)\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*~\s*(20\d\d)\.\s*(\d{1,2})\.\s*(\d{1,2})", text)
        if m:
            r["start"] = norm_date("-".join(m.groups()[:3]))
            r["end"] = norm_date("-".join(m.groups()[3:]))
        time.sleep(0.5)
    return rows


def _homepages() -> dict[str, str]:
    """운영기관 이름 → 원본(공지 게시판 또는 홈페이지) 주소."""
    out: dict[str, str] = {}
    db = ROOT / "data" / "scholarships.db"
    if db.exists():
        con = sqlite3.connect(db)
        for (d,) in con.execute("select data from scholarships where source like 'kosaf%'"):
            r = json.loads(d)
            if r.get("org") and r.get("url"):
                out.setdefault(_norm(r["org"]), r["url"])
        con.close()
    reg = ROOT / "data" / "registry" / "sources.json"
    if reg.exists():
        for s in json.loads(reg.read_text()):
            u = s.get("notice_url") or s.get("homepage")
            if u:
                out[_norm(s["name"])] = u
    return out


def _norm(name: str) -> str:
    return re.sub(r"\(.*?\)|재단법인|사단법인|\s", "", name or "")


def _end_from_day(day: str) -> str:
    m = re.match(r"D-(\d+)", day or "")
    return (date.today() + timedelta(days=int(m.group(1)))).isoformat() if m else ""


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
    homes = _homepages()
    out = []
    for r in rows:
        if re.search(r"꿀팁|MOU|이벤트|후기|웨비나|설명회|서포터즈", r.get("title", "")) or "드림스폰" in (r.get("org") or ""):
            continue  # 장학 공고가 아닌 사이트 자체 글
        tags = r.get("tags") or []
        st = sorted({SCHOOL_TAGS[t] for t in tags if t in SCHOOL_TAGS})
        if not st and re.search(r"#(일반인|신혼부부|예술인|창업기업|취업지원|청년|학교밖청소년)", " ".join(tags)):
            continue  # 학생이 아닌 사람 대상 지원
        # 목록에는 태그가 3개까지만 보여서 대상 학년을 다 알 수 없다. 대학 태그가 없으면 다른 공고와 합쳐질 때만 쓴다.
        end = r.get("end") or _end_from_day(r.get("day", ""))
        if r.get("state") == "모집마감" and not r.get("end"):
            continue  # 날짜를 모르는 마감 공고는 넣지 않는다
        home = homes.get(_norm(r.get("org")), "")
        notes = [COND_TAG[t] for t in tags if t in COND_TAG]
        out.append(finalize({
            "id": make_id("dreamspon", r["idx"]), "source": "dreamspon", "source_name": "드림스폰",
            "title": r["title"], "org": r.get("org", ""), "org_type": "민간·기업·대학",
            "category": "근로장학" if "#근로장학" in tags else "장학금",
            "kind": "근로장학" if "#근로장학" in tags else ("대출" if "#대출지원" in tags else "장학"),
            "level": ("대학원생" if st == ["일반대학원"] else "대학생") if st else "", "school_types": st,
            "amount": ", ".join(SUPPORT_TAG[t] for t in tags if t in SUPPORT_TAG),
            "residence": "거주 지역 조건 있음 — 공고 원문 확인" if "#지역기준" in tags else "",
            "special": " · ".join(n for n in notes if n != "거주 지역 조건 있음"),
            "recommend": "추천서 필요" if "#추천서" in tags else "",
            "url": home, "start": r.get("start", ""), "end": end, "verified": False,
        }))
    return out, [{"source": "dreamspon", "label": "드림스폰 공개 목록(원본 링크로 연결)", "ok": mode == "online" or bool(rows),
                  "count": len(out), "mode": mode}]
