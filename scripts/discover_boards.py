"""학교 홈페이지에서 장학 공지 게시판 주소를 찾는다 (일회성, GitHub Actions 에서 실행). robots.txt 를 지킨다."""
import json, re, sys, concurrent.futures as cf
from urllib.parse import urljoin, urlparse
import requests, urllib3
from bs4 import BeautifulSoup
sys.path.insert(0, ".")
from server.collectors.boards import allowed, UA, KEY
urllib3.disable_warnings()
MISS = json.load(open("scripts/univ_missing.json"))
GOOD = [(re.compile(r"장학\s*(공지|게시판|공지사항|소식)"), 10), (re.compile(r"^\s*장학\s*(안내|정보)?\s*$|^\s*장학금\s*$"), 9),
        (re.compile(r"장학금\s*(안내|공지|정보)|교외\s*장학|외부\s*장학"), 8), (re.compile(r"장학"), 6),
        (re.compile(r"^\s*(학사|학생|학생지원)\s*공지\s*$"), 4), (re.compile(r"^\s*공지\s*사항\s*$|^\s*공지\s*$|^\s*일반\s*공지\s*$|^\s*NOTICE\s*$"), 3)]
from server.collectors.boards import RECRUIT, DROP
_R = None
def render(url):
    global _R
    try:
        if _R is None:
            from server.collectors.boards import Renderer
            _R = Renderer()
        return _R.html(url, 3000)
    except Exception:
        return ""
def get(url):
    r = requests.get(url, timeout=15, headers={"User-Agent": UA, "Accept-Language": "ko"}, verify=False)
    if not r.encoding or r.encoding.lower() == "iso-8859-1": r.encoding = r.apparent_encoding
    return r
def score_links(html, base, dom):
    soup = BeautifulSoup(html, "html.parser"); out = []
    for a in soup.find_all("a"):
        t = " ".join(a.get_text(" ").split()); href = a.get("href") or ""
        if not t or len(t) > 20 or href.startswith(("javascript", "#", "mailto")): continue
        u = urljoin(base, href); h = urlparse(u).hostname or ""
        if not h.endswith(dom): continue
        for rx, sc in GOOD:
            if rx.search(t): out.append((sc, t, u)); break
    return sorted(out, key=lambda x: -x[0])
def posts(html):
    soup = BeautifulSoup(html, "html.parser"); out = []
    for a in soup.find_all("a"):
        t = " ".join(a.get_text(" ").split())
        if len(t) >= 12 and KEY.search(t) and RECRUIT.search(t) and not DROP.search(t): out.append(t)
    return out
RENDER = False
def one(item):
    name, dom, home = item
    try:
        if not allowed(home): return name, {"err": "robots"}
        r = get(home); cands = score_links(r.text, r.url, dom)
        if not cands and RENDER:
            h = render(home)
            if h: cands = score_links(h, home, dom)
        # 한 단계 더: '장학'이 없으면 '학생/학사' 메뉴 페이지에서도 찾는다
        seen = set()
        for sc, t, u in cands[:6]:
            if u in seen or not allowed(u): continue
            seen.add(u)
            try:
                p = get(u); ps = posts(p.text)
                if len(ps) < 2 and RENDER:
                    h = render(u)
                    if h and len(posts(h)) >= 2: return name, {"url": u, "label": t, "n": len(posts(h)), "ex": posts(h)[:2], "render": True}
                if len(ps) >= 2: return name, {"url": p.url, "label": t, "n": len(ps), "ex": ps[:2]}
                if sc >= 8:
                    for sc2, t2, u2 in score_links(p.text, p.url, dom)[:3]:
                        if u2 in seen or not allowed(u2): continue
                        seen.add(u2); p2 = get(u2); ps2 = posts(p2.text)
                        if len(ps2) >= 2: return name, {"url": p2.url, "label": t2, "n": len(ps2), "ex": ps2[:2]}
            except Exception: pass
        return name, {"err": "notfound", "cands": [c[1] for c in cands[:5]]}
    except Exception as e:
        return name, {"err": repr(e)[:80]}
res = {}
with cf.ThreadPoolExecutor(12) as ex:
    res.update(dict(ex.map(one, MISS)))
RENDER = True  # 자바스크립트로 메뉴를 그리는 학교는 헤드리스 브라우저로 한 번 더 (한 줄씩)
for m in MISS:
    if res.get(m[0], {}).get("err") == "notfound":
        res[m[0]] = one(m)[1]
json.dump(res, sys.stdout, ensure_ascii=False, indent=0)
