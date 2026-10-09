"""강원대학교 장학공지(삼척캠퍼스 대상) — 공개 게시판, 로그인 불필요.

robots.txt 는 /ko/ 아래 공개 페이지를 허용한다. 장학공지(750)는 전부, 일반공지(504)는 장학·근로 글만 본다.
캠퍼스 칸이 '삼척' 이거나 'ALL'(전 캠퍼스)인 글만 남긴다. 교외 장학을 옮겨 실은 글은 운영기관 이름으로 보여 준다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from ..model import finalize, make_id, norm_date
from .period import period_from

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "kangwon.json"
BASE = "https://www.kangwon.ac.kr"
LIST = BASE + "/ko/bbs/{bbs}/list.do?pageIndex={page}"
VIEW = BASE + "/ko/bbs/{bbs}/detail.do?pstSn={sn}"
BOARDS = [("750", 6, None), ("504", 3, re.compile(r"장학|근로"))]
UA = "Mozilla/5.0 (compatible; JangakAlimiBot/1.0; +https://github.com/lussion629-creator/JangHak-Alim-e)"
WORK = re.compile(r"근로|장학조교|학생\s*조교|도우미|튜터")
INSIDE = re.compile(r"교내|KNU|삼척캠퍼스|우선감면|성적우수|근로|장학사정관|학과\s*장학|총동문회|발전기금|국가장학|국가근로|학자금|등록금|KNU-SOS|생활관")
OTHER_CAMPUS = re.compile(r"^\s*\[(춘천|강릉|원주|춘천캠퍼스|강릉캠퍼스|원주캠퍼스|강릉\.?원주)\]")


def _get(s, url):
    r = s.get(url, timeout=25)
    r.raise_for_status()
    return r.text


def parse_list(html: str) -> list[dict]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for tr in soup.select("table tbody tr"):
        a = tr.select_one("a.detail-button[data-sn]")
        tds = tr.find_all("td", recursive=False)
        if not a or len(tds) < 5:
            continue
        sn = a["data-sn"]
        if sn in seen:
            continue  # 고정 공지가 아래 일반 목록에 한 번 더 나온다
        seen.add(sn)
        campus = " ".join(x.get_text(" ", strip=True) for x in tds[1].select(".photo-chip")) or tds[1].get_text(" ", strip=True)
        out.append({"sn": sn, "title": a.get_text(" ", strip=True), "campus": campus,
                    "dept": tds[3].get_text(" ", strip=True), "date": norm_date(tds[4].get_text(" ", strip=True).replace(".", "-"))})
    return out


def parse_detail(html: str) -> dict:
    from bs4 import BeautifulSoup
    from ..model import html_block_text
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    body = soup.select_one(".info-editor-area .editor-wrap")
    if body:
        for t in body(["script", "style"]):
            t.decompose()
        out["text"] = html_block_text(body)[:3000]
    for tr in soup.select(".card.detail table tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td and "문의" in th.get_text():
            out["tel"] = td.get_text(" ", strip=True)[:40]
    out["files"] = [x.get_text(" ", strip=True)[:80] for x in soup.select(".view-file-name")][:3]
    return out


def fetch(known: dict) -> list[dict]:
    from .boards import allowed
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR"})
    rows = []
    for bbs, pages, kw in BOARDS:
        if not allowed(LIST.format(bbs=bbs, page=1)):
            raise PermissionError("robots")
        for p in range(1, pages + 1):
            items = parse_list(_get(s, LIST.format(bbs=bbs, page=p)))
            if not items:
                break
            for it in items:
                if kw and not kw.search(it["title"]):
                    continue
                it["bbs"] = bbs
                rows.append(it)
    n = 0
    for r in rows:
        k = r["bbs"] + ":" + r["sn"]
        if k in known:
            r["detail"] = known[k]
        elif _keep(r) and n < 40:
            try:
                r["detail"] = parse_detail(_get(s, VIEW.format(bbs=r["bbs"], sn=r["sn"])))
            except Exception:  # noqa: BLE001
                pass
            n += 1
    return rows


def _keep(r) -> bool:
    c = r.get("campus", "")
    if not re.search(r"삼척|ALL|전체", c):
        return False  # 춘천·강릉·원주 캠퍼스만 대상인 글
    return not OTHER_CAMPUS.search(r["title"])


def collect(online: bool = True):
    from .boards import _org_from_title
    old = json.loads(SEED.read_text())["records"] if SEED.exists() else []
    known = {r["bbs"] + ":" + r["sn"]: r["detail"] for r in old if r.get("detail")}
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
        if not _keep(r):
            continue
        t = re.sub(r"^\s*\[(삼척|삼척캠퍼스|ALL|전체)\]\s*", "", r["title"])
        det = r.get("detail") or {}
        body = det.get("text", "")
        start, end = period_from(t, body, r.get("date", ""))
        work = bool(WORK.search(t))
        ext = _org_from_title(t, "강원대학교", body)
        relay = bool(re.search(r"구민|시민|군민|도민|재단|장학회|육영회|협회|진흥원|공사|공단|은행|그룹|교육청|시청|군청|구청|도청|신문|방송|[A-Za-z]{2,}", t))
        inside = bool(INSIDE.search(t)) and not re.search(r"재단|장학회|진흥원", t) or (ext == "강원대학교" and not relay)
        if not inside and ext == "강원대학교":
            ext = ""  # 운영기관 이름을 찾지 못한 교외 장학
        dogye = "도계" in t
        out.append(finalize({
            "id": make_id("kangwon", r["bbs"], r["sn"]), "source": "kangwon", "source_name": "강원대 장학공지",
            "title": t, "org": "강원대학교 " + ("도계캠퍼스" if dogye else "삼척캠퍼스") if inside else ext,
            "org_type": "대학(교내)" if inside else "민간·기업·대학",
            "category": "근로장학" if work else ("학자금" if "대출" in t else "장학금"),
            "kind": ("교내근로" if work else "공고"), "level": "대학원생" if re.search(r"대학원생|석사|박사", t) and not re.search(r"학부", t) else "대학생",
            "school_types": ["4년제(5~6년제포함)"] if inside else [],
            "region": "강원" if inside else "", "district": "삼척" if inside else "",
            "url": VIEW.format(bbs=r["bbs"], sn=r["sn"]), "posted": r.get("date", ""), "start": start, "end": end,
            "summary": body, "files": det.get("files", []),
            "selection": ("담당: " + r["dept"]) if r.get("dept") else "", "verified": True,
        }))
    return out, [{"source": "kangwon", "label": "강원대 장학공지(삼척)", "ok": bool(out), "count": len(out), "mode": mode}]
