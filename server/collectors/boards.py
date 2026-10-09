"""대학·재단·지자체 장학 공지 게시판 범용 수집기.

data/registry/sources.json 의 각 기관에 대해
  1) RSS (등록된 rss → K2Web rssList.do → WordPress /feed 순서) 를 먼저 시도하고
  2) 실패하면 목록 HTML 에서 '장학' 키워드가 있는 글 링크를 뽑는다.
robots.txt 를 지키고, 기관별 수집 상태(성공/실패/건수/마지막 성공)를 남긴다.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from ..model import extract_target, finalize, make_id, norm_date

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2] / "data"
UA = "Mozilla/5.0 (compatible; JangakAlimiBot/1.0; +https://github.com/lussion629-creator/JangHak-Alim-e)"
KEY = re.compile(r"장학|학자금|장학생|인재육성")
DROP = re.compile(r"(합격자|선발\s*결과|선정\s*결과|결과\s*발표|최종\s*선발자|선발자|수혜자\s*명단|명단|지급\s*(일정|안내|예정)|근로장학생\s*근무|캠페인|부정수급|포기|반환|기부|수여식|직인|날인|설문|만족도|이수\s*안내|운영\s*안내|유의\s*사항|증명서\s*발급|서류\s*제출\s*안내|박람회|설명회|특강|캠프|워크숍|간담회|세미나|일자리)")
RECRUIT = re.compile(r"모집|선발|신청|추천|접수|공모|지원\s*사업|장학생")
DATE = re.compile(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})")
DEADLINE = re.compile(r"[~∼〜]\s*(?:(20\d{2})[.\-/])?\s*(\d{1,2})\s*[./월]\s*(\d{1,2})|(\d{1,2})\s*[./]\s*(\d{1,2})\s*\.?\s*\(?[월화수목금토일]?\)?\s*까지")

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def allowed(url: str) -> bool:
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers={"User-Agent": UA}, timeout=10)
            if r.status_code >= 400 or "<html" in r.text[:200].lower():
                rp = None
            else:
                rp.parse(r.text.splitlines())
        except Exception:  # noqa: BLE001
            rp = None
        _robots[host] = rp
    rp = _robots[host]
    return True if rp is None else rp.can_fetch(UA, url)


def get(url: str, timeout=20) -> requests.Response:
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "ko"}, timeout=timeout)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    return r


def rss_candidates(src: dict) -> list[str]:
    c = [src["rss"]] if src.get("rss") else []
    u = src.get("notice_url") or ""
    m = re.search(r"(https?://[^/]+)/bbs/([^/]+)/(\d+)/", u)
    if m:
        c.append(f"{m.group(1)}/bbs/{m.group(2)}/{m.group(3)}/rssList.do?row=50")
    if "/category/" in u:
        c.append(u.rstrip("/") + "/feed")
    return c


def parse_rss(text: str):
    import feedparser
    feed = feedparser.parse(text)
    items = []
    for e in feed.entries:
        title = (e.get("title") or "").strip()
        if not title or "NOT SUPPORT" in title.upper():
            continue
        posted = ""
        if e.get("published_parsed"):
            posted = date(*e.published_parsed[:3]).isoformat()
        items.append({"title": title, "url": e.get("link", ""), "posted": posted, "summary": re.sub(r"<[^>]+>", " ", e.get("summary", ""))[:600]})
    return items


def parse_html(text: str, base: str):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")
    items, seen = [], set()
    for a in soup.find_all("a"):
        title = " ".join(a.get_text(" ").split())
        if len(title) < 6 or not KEY.search(title):
            continue
        href = a.get("href") or ""
        if href.startswith("javascript") and not re.search(r"\d{3,}", href):
            continue
        url = urljoin(base, href) if not href.startswith("javascript") else base
        k = (title, url)
        if k in seen:
            continue
        seen.add(k)
        row = a.find_parent(["tr", "li", "div"])
        rowtext = " ".join(row.get_text(" ").split()) if row else ""
        m = DATE.search(rowtext.replace(title, ""))
        items.append({"title": title, "url": url, "posted": norm_date("-".join(m.groups())) if m else "", "summary": ""})
    return items


def deadline_from(title: str, posted: str) -> str:
    m = DEADLINE.search(title)
    if not m:
        return ""
    if m.group(2):
        y, mo, d = m.group(1), m.group(2), m.group(3)
    else:
        y, mo, d = None, m.group(4), m.group(5)
    y = int(y) if y else int((posted or date.today().isoformat())[:4])
    try:
        dl = date(y, int(mo), int(d))
    except ValueError:
        return ""
    if posted and dl.isoformat() < posted:
        try:
            dl = date(y + 1, int(mo), int(d))
        except ValueError:
            return ""
    return dl.isoformat()


BODY_SEL = (".view-con, .view_con, .artclView, .bbs_view, .board-view, .view-content, .view_content, .bv_content, "
            ".content-view, .board_view, .viewContent, .txt, .cont, article, #content, .content, td.content, .fr-view")


def text_of_html(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "noscript", "form"]):
        t.decompose()
    cands = soup.select(BODY_SEL)
    best = max(cands or [soup.body or soup], key=lambda e: len(e.get_text(" ", strip=True)))
    return re.sub(r"\n{2,}", "\n", best.get_text("\n", strip=True))[:3000]


def fetch_detail(url: str) -> str:
    """공고 본문 텍스트(최대 3000자). 본문 영역 후보 중 글자가 가장 많은 블록을 쓴다."""
    if not url or not allowed(url):
        return ""
    try:
        return text_of_html(get(url, timeout=15).text)
    except Exception:  # noqa: BLE001
        return ""


class Renderer:
    """자바스크립트로 그려지는 게시판용 헤드리스 브라우저 (GitHub Actions 에서 playwright 로 실행).
    playwright 가 없으면 아무것도 하지 않는다."""

    def __init__(self):
        self.pw = self.browser = None
        try:
            from playwright.sync_api import sync_playwright
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch()
            self.ctx = self.browser.new_context(user_agent=UA, locale="ko-KR")
        except Exception as e:  # noqa: BLE001
            log.info("renderer unavailable: %s", e)
            self.close()

    def html(self, url: str, wait_ms: int = 2500) -> str:
        if not self.browser or not allowed(url):
            return ""
        page = self.ctx.new_page()
        try:
            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)
            return page.content()
        except Exception:  # noqa: BLE001
            return ""
        finally:
            page.close()

    def close(self):
        try:
            if self.browser:
                self.browser.close()
            if self.pw:
                self.pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self.browser = self.pw = None


ORG_TYPE = {"university": "대학 게시판", "local": "지자체", "corporate": "민간·기업·대학", "welfare": "민간·기업·대학",
            "private": "민간·기업·대학", "public": "공공기관", "religious": "민간·기업·대학", "alumni": "민간·기업·대학"}


def list_items(src: dict, status: dict):
    for u in rss_candidates(src):
        if not allowed(u):
            continue
        try:
            items = parse_rss(get(u).text)
            if items:
                status["method"] = "rss"
                return items
        except Exception:  # noqa: BLE001
            continue
    u = src["notice_url"]
    if not allowed(u):
        status["error"] = "robots.txt 비허용"
        return None
    status["method"] = "html"
    return parse_html(get(u).text, u)


def build_recs(src: dict, items: list, since: str, body_fn=fetch_detail):
    recs = []
    for it in items:
        if not KEY.search(it["title"]) or DROP.search(it["title"]) or not RECRUIT.search(it["title"]):
            continue
        dl = deadline_from(it["title"], it["posted"])
        if not it["posted"] and not dl:
            continue  # 날짜 없는 링크는 대부분 메뉴(‘신입생장학금’, ‘맞춤형 장학검색’ 등)
        if (it["posted"] or dl) < since:
            continue
        body = it["summary"] or (body_fn(it["url"]) if it["url"] and it["url"] != src.get("notice_url") and len(recs) < 25 else "")
        rec = {
            "id": make_id("board", src["id"], it["url"] or it["title"]),
            "source": "board",
            "source_name": src["name"],
            "title": it["title"],
            "org": src["name"] if src["type"] != "university" else _org_from_title(it["title"], src["name"], body),
            "org_type": ORG_TYPE.get(src["type"], "기타"),
            "category": "장학금",
            "kind": "공고",
            "level": "대학생",
            "url": it["url"],
            "posted": it["posted"],
            "end": dl or _deadline_in_body(body, it["posted"]),
            "summary": body,
            "target": extract_target(body),
            "region": src.get("region") or "",
            "district": src.get("district") or "",
            "links": [{"name": src["name"] + " 게시판", "url": src["notice_url"]}],
        }
        if src["type"] == "university":
            rec["school_types"] = ["특정대학"]
            rec["region"] = ""
        recs.append(finalize(rec))
    return recs


def collect_one(src: dict, since: str):
    t0 = time.time()
    status = {"id": src["id"], "name": src["name"], "url": src.get("notice_url"), "ok": False, "count": 0, "method": "", "error": ""}
    try:
        items = list_items(src, status)
        if items is None:
            return [], status
        status["ok"] = True
    except Exception as e:  # noqa: BLE001
        status["error"] = str(e)[:160]
        return [], status
    if not items:
        status["needs_render"] = True
    recs = build_recs(src, items, since)
    status["count"] = len(recs)
    status["seconds"] = round(time.time() - t0, 1)
    return recs, status


def _deadline_in_body(text: str, posted: str) -> str:
    m = re.search(r"(신청|접수|모집)\s*(기간|기한|마감)[^\n]{0,40}?[~∼〜-]\s*(20\d{2}[.\-/년]\s*)?(\d{1,2})\s*[./월]\s*(\d{1,2})", text or "")
    if not m:
        return ""
    return deadline_from("~" + (m.group(3) or "") + m.group(4) + "/" + m.group(5), posted)


def _org_from_title(title: str, school: str, body: str = "") -> str:
    m = re.search(r"[\[(]([^\])]{2,30}(재단|장학회|장학재단|진흥원|공단|공사|은행|그룹|협회|센터))[\])]", title)
    if m:
        return m.group(1)
    m = re.search(r"([가-힣A-Za-z0-9]{2,20}(장학재단|복지재단|문화재단|재단|장학회|인재육성재단|진흥원))", title)
    if m:
        return m.group(1)
    # 제목에 없으면 본문 앞부분에서 운영기관 이름을 찾는다 (예: '재단법인 대산농촌재단에서 …')
    m = re.search(r"(?:재단법인|사단법인|\(재\)|\(사\))?\s*([가-힣A-Za-z0-9]{2,20}(장학재단|복지재단|문화재단|농촌재단|학술재단|교육재단|재단|장학회|육영회|진흥원))", (body or "")[:800])
    return m.group(1) if m and school.replace("학교", "") not in m.group(1) else school


def load_sources() -> list[dict]:
    p = ROOT / "registry" / "sources.json"
    return json.loads(p.read_text()) if p.exists() else []


def collect(online: bool = True, since: str | None = None, workers: int = 8):
    if not online:
        return [], [{"source": "board", "ok": False, "count": 0, "mode": "offline"}]
    since = since or (date.today() - timedelta(days=120)).isoformat()
    srcs = [s for s in load_sources() if s.get("enabled") and s.get("notice_url")]
    out, statuses = [], []
    with ThreadPoolExecutor(workers) as ex:
        for recs, st in ex.map(lambda s: collect_one(s, since), srcs):
            out.extend(recs)
            statuses.append(st)
    # 2단계: 자바스크립트로 그려지는 목록·본문은 헤드리스 브라우저로 다시 읽는다
    need_list = [s for s, st in zip(srcs, statuses) if st.get("needs_render")]
    need_body = [r for r in out if len(r.get("summary") or "") < 80 and r.get("url")]
    if need_list or need_body:
        rd = Renderer()
        if rd.browser:
            rendered = 0
            for s_, st in zip(srcs, statuses):
                if not st.get("needs_render"):
                    continue
                html = rd.html(s_["notice_url"])
                items = parse_html(html, s_["notice_url"]) if html else []
                recs = build_recs(s_, items, since, body_fn=lambda u: text_of_html(rd.html(u)) if u else "")
                out.extend(recs)
                st.update(count=len(recs), method="render")
                rendered += 1
            for r in need_body[:150]:
                html = rd.html(r["url"])
                body = text_of_html(html) if html else ""
                if len(body) >= 80:
                    r["summary"] = body
                    r["target"] = extract_target(body)
                    r["end"] = r.get("end") or _deadline_in_body(body, r.get("posted", ""))
                    if r.get("org") == r.get("source_name"):
                        r["org"] = _org_from_title(r["title"], r["source_name"], body)
            rd.close()
            log.info("rendered lists=%d bodies=%d", rendered, min(len(need_body), 150))
    (ROOT / "registry" / "status.json").write_text(json.dumps(statuses, ensure_ascii=False, indent=1))
    ok = sum(1 for s in statuses if s["ok"])
    return out, [{"source": "board", "label": f"대학·재단·지자체 게시판 {len(srcs)}곳", "ok": ok > 0, "count": len(out),
                  "mode": f"성공 {ok} / 실패 {len(srcs) - ok}"}]
