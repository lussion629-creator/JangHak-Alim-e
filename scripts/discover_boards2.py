"""학교 홈페이지에서 장학 공지 게시판 찾기 (2차: 사이트 안을 몇 단계 둘러본다). robots.txt 를 지킨다. 일회성."""
import json, re, sys, concurrent.futures as cf
from urllib.parse import urljoin, urlparse
import requests, urllib3
from bs4 import BeautifulSoup
sys.path.insert(0, ".")
from server.collectors.boards import allowed, UA, KEY, RECRUIT, DROP
urllib3.disable_warnings()
TODO = json.load(open("scripts/univ_todo.json"))
SC = [(re.compile(r"장학\s*(공지|게시판|공지사항|소식|알림)|공지\s*\(?장학"), 10), (re.compile(r"교외\s*장학|외부\s*장학|장학금\s*(안내|공지|정보|신청)"), 8),
      (re.compile(r"장학"), 6), (re.compile(r"학생\s*(지원|생활|복지)|캠퍼스\s*라이프|대학\s*생활|학생\s*서비스"), 4),
      (re.compile(r"공지\s*사항|^공지$|알림\s*마당|소식|NOTICE|게시판|학사\s*공지|학생\s*공지"), 3)]
def get(url):
    r = requests.get(url, timeout=15, headers={"User-Agent": UA, "Accept-Language": "ko"}, verify=False)
    if not r.encoding or r.encoding.lower() == "iso-8859-1": r.encoding = r.apparent_encoding
    return r
def posts(html):
    soup = BeautifulSoup(html, "html.parser"); out = []
    for a in soup.find_all("a"):
        t = " ".join(a.get_text(" ").split())
        if len(t) >= 12 and KEY.search(t) and RECRUIT.search(t) and not DROP.search(t): out.append(t)
    return out
def links(html, base, dom):
    soup = BeautifulSoup(html, "html.parser"); out = []
    for f in soup.find_all(["frame", "iframe"]):
        s = f.get("src")
        if s: out.append((7, "frame", urljoin(base, s)))
    m = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
    if m and "url=" in (m.get("content") or "").lower():
        out.append((9, "refresh", urljoin(base, m["content"].split("=", 1)[1].strip("'\" "))))
    for a in soup.find_all("a"):
        t = " ".join(a.get_text(" ").split()) or (a.get("title") or "") or (a.find("img").get("alt") if a.find("img") else "") or ""
        href = a.get("href") or ""
        if not href or href.startswith(("javascript", "#", "mailto", "tel")) or len(t) > 25: continue
        u = urljoin(base, href); h = urlparse(u).hostname or ""
        if not h.endswith(dom) or re.search(r"\.(pdf|hwp|jpg|png|zip)$", u, re.I): continue
        for rx, sc in SC:
            if rx.search(t): out.append((sc, t, u)); break
    if len(out) < 3 and len(soup.find_all("a")) < 15:  # 첫 화면(인트로)만 있는 경우: 같은 학교 주소 링크를 따라간다
        for a in soup.find_all("a")[:5]:
            u = urljoin(base, a.get("href") or "")
            if (urlparse(u).hostname or "").endswith(dom): out.append((5, "intro", u))
    return out
RENDER = "--render" in sys.argv
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
def one(item):
    name, dom, home = item
    if not allowed(home): return name, {"err": "robots"}
    queue = [(10, "home", home)]; seen = set(); visits = 0
    try:
        while queue and visits < (5 if RENDER else 18):
            queue.sort(key=lambda x: -x[0]); sc, t, u = queue.pop(0)
            k = u.split("#")[0]
            if k in seen or not allowed(u): continue
            seen.add(k); visits += 1
            html, final = "", u
            try:
                r = get(u); html, final = r.text, r.url
            except Exception: pass
            if RENDER and (len(BeautifulSoup(html or "", "html.parser").find_all("a")) < 30 or t != "home"):
                h = render(u)
                if h: html = h
            if not html: continue
            class R: pass
            r = R(); r.text = html; r.url = final
            ps = posts(r.text)
            if len(ps) >= 2 and t != "home": return name, {"url": r.url, "label": t, "n": len(ps), "ex": ps[:2]}
            if len(ps) >= 3 and t == "home" and re.search(r"장학|notice|board|bbs", r.url, re.I): return name, {"url": r.url, "label": t, "n": len(ps), "ex": ps[:2]}
            for x in links(r.text, r.url, dom):
                if x[2].split("#")[0] not in seen: queue.append((x[0] - (0 if t == "home" else 1), x[1], x[2]))
        return name, {"err": "notfound", "visits": visits}
    except Exception as e:
        return name, {"err": repr(e)[:80]}
if RENDER:
    res = {}
    for it in TODO:
        k, v = one(it); res[k] = v
        json.dump(res, open("out/boards.json", "w"), ensure_ascii=False, indent=0)  # 중간에 끊겨도 남도록
else:
    with cf.ThreadPoolExecutor(12) as ex:
        res = dict(ex.map(one, TODO))
json.dump(res, open("out/boards.json", "w"), ensure_ascii=False, indent=0)
