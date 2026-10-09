"""한양대학교 공개 공지사항 '장학/등록'·'모집/채용' 분류 (로그인 불필요).

'모집/채용'에서는 교내·교외 근로장학생, 장학조교, 학생 도우미 모집 글만 가져온다."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from ..model import finalize, make_id, norm_date

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "hanyang_public.json"
WORK_SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "hanyang_work.json"
CAT_SCH, CAT_JOB = "224311300", "224311302"
WORK = re.compile(r"근로|장학조교|학생\s*조교|도우미|튜터|Tutor", re.I)
NOT_WORK = re.compile(r"계약직|직원\s*(채용|모집)|강사|교수|초빙|연구원|연구조교|연구병|인력풀")


def detail(url: str) -> dict:
    """공지 본문(.entry-content)과 '공지기간', 첨부파일 이름을 읽는다."""
    from bs4 import BeautifulSoup
    from ..model import html_block_text
    try:
        html = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
    except Exception:  # noqa: BLE001
        return {}
    return parse_detail(html)


def parse_detail(html: str) -> dict:
    from bs4 import BeautifulSoup
    from ..model import html_block_text
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    body = soup.select_one(".entry-content")
    if body:
        for t in body(["script", "style"]):
            t.decompose()
        out["text"] = html_block_text(body)[:3000]
    for it in soup.select(".hyu-meta-item"):
        sp = [x.get_text(" ", strip=True) for x in it.find_all("span", recursive=False)]
        if len(sp) >= 2 and sp[0] == "공지기간":
            m = re.findall(r"(20\d\d)\.\s*(\d{1,2})\.\s*(\d{1,2})", sp[1])
            if len(m) == 2:
                out["start"], out["end"] = (norm_date("-".join(x)) for x in m)
    out["files"] = [a.get_text(" ", strip=True)[:80] for a in soup.select(".file-download a")][:3]
    return out
PID = "kr_ac_hanyang_noticeBoard_web_portlet_NoticeBoardPortlet"
LIST = ("https://www.hanyang.ac.kr/notice_all?p_p_id={p}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        "&_{p}_action=view&_{p}_sCategoryId={cat}&_{p}_cur={page}")
VIEW = ("https://www.hanyang.ac.kr/notice_all?p_p_id={p}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        "&_{p}_action=view_message&_{p}_sCategoryId={cat}&_{p}_entryId={id}")
SKIP = re.compile(r"(등록안내|증명발급|서비스 오픈)")


def fetch(pages=8, cat=CAT_SCH):
    from bs4 import BeautifulSoup
    rows = []
    for page in range(1, pages + 1):
        html = requests.get(LIST.format(p=PID, page=page, cat=cat), timeout=20, headers={"User-Agent": "Mozilla/5.0"}).text
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
                         "date": norm_date(dt.get_text() if dt else ""), "cat": cat})
    return rows


def _due(title: str, posted: str) -> str:
    """제목의 '(~08.18)', '(~8/23)', '~9. 18.(금)' 같은 마감일을 날짜로 바꾼다."""
    m = re.search(r"~\s*(?:(20\d\d)\s*[./-]\s*)?(\d{1,2})\s*[./월]\s*(\d{1,2})", title)
    if not m:
        return ""
    y = int(m.group(1) or (posted[:4] if posted else 0) or 0)
    if not y:
        return ""
    mo, d = int(m.group(2)), int(m.group(3))
    if posted and not m.group(1) and mo < int(posted[5:7]) - 6:
        y += 1
    try:
        return norm_date(f"{y}-{mo:02d}-{d:02d}")
    except Exception:  # noqa: BLE001
        return ""


def _load(online, cat, seed, pages):
    from .boards import allowed
    if online and allowed(LIST.format(p=PID, page=1, cat=cat)):  # robots.txt 가 막으면 저장된 목록만 쓴다
        try:
            rows = fetch(pages, cat)
            seed.write_text(json.dumps({"records": rows}, ensure_ascii=False))
            return rows, "online"
        except Exception:  # noqa: BLE001
            pass
    return (json.loads(seed.read_text())["records"] if seed.exists() else []), "seed"


def collect(online: bool = True):
    rows, mode = _load(online, CAT_SCH, SEED, 8)
    jobs, mode2 = _load(online, CAT_JOB, WORK_SEED, 6)
    ids = {r["id"] for r in rows}
    rows += [r for r in jobs if r.get("cat") == CAT_SCH and r["id"] not in ids]
    jobs = [r for r in jobs if r.get("cat", CAT_JOB) == CAT_JOB]
    jobs = [r for r in jobs if WORK.search(r["title"]) and not NOT_WORK.search(r["title"])]
    bodies = {}
    if mode2 == "online":
        for r in jobs[:30]:
            bodies[r["id"]] = detail(VIEW.format(p=PID, id=r["id"], cat=CAT_JOB))
    for r in jobs:
        if r.get("detail") and r["id"] not in bodies:
            bodies[r["id"]] = r["detail"]  # 브라우저로 모은 목록에 들어 있는 본문 정보
    out = []
    seen = set()
    for r in rows + jobs:
        if r["id"] in seen or SKIP.search(r["title"]):
            continue
        seen.add(r["id"])
        cat = r.get("cat", CAT_SCH)
        work = bool(WORK.search(r["title"]) and re.search(r"근로|장학조교|도우미|튜터|Tutor", r["title"], re.I))
        m = re.search(r"\(?(20\d{2})\.\s?(\d{1,2})\.\s?(\d{1,2})\.?[^~]*~\s*(20\d{2})\.\s?(\d{1,2})\.\s?(\d{1,2})", r["title"])
        start = end = ""
        if m:
            start = norm_date("-".join(m.groups()[:3]))
            end = norm_date("-".join(m.groups()[3:]))
        elif work:
            end = _due(r["title"], r.get("date", ""))
        det = bodies.get(r["id"]) or {}
        if work and det.get("end") and not end:
            start, end = det.get("start", ""), det["end"]  # 공지기간
        if work and re.search(r"\((완료|마감|모집\s*완료)\)|조기\s*마감", r["title"]):
            end = r.get("date", "") or end  # 이미 마감된 모집
        kind = "교외근로" if "교외" in r["title"] else ("교내근로" if work else "공고")
        pay = re.search(r"시\s*급\s*[:：]?\s*([\d,]{4,})\s*원", det.get("text", ""))
        out.append(finalize({
            "id": make_id("hanyang", r["id"]), "source": "hanyang",
            "source_name": "한양대 공지사항(" + ("모집/채용" if cat == CAT_JOB else "장학/등록") + ")",
            "title": r["title"], "org": "한양대학교" + (" " + r["campus"] if r.get("campus") in ("서울", "ERICA") else ""),
            "org_type": "대학(교내)", "category": "근로장학" if work else ("학자금" if "대출" in r["title"] else "장학금"), "kind": kind,
            "level": "대학원생" if work and "대학원" in r["title"] else "대학생",
            "region": "서울" if r.get("campus") != "ERICA" else "경기",
            "selection": "담당: " + r.get("dept", ""), "url": VIEW.format(p=PID, id=r["id"], cat=cat), "posted": r["date"],
            "start": start, "end": end, "files": det.get("files") or r.get("files", []), "verified": True,
            "summary": det.get("text", ""), "amount": f"시급 {pay.group(1)}원" if pay else "",
        }))
    nwork = sum(1 for x in out if x["kind"] in ("교내근로", "교외근로"))
    return out, [{"source": "hanyang", "label": "한양대 공개 공지(장학/등록·근로 모집)", "ok": True, "count": len(out), "work": nwork, "mode": mode + "/" + mode2}]
