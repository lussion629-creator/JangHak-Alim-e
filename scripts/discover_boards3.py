"""학교 장학 게시판 찾기 3차 (일회성): 사이트맵 화면 + 브라우저로 그린 전체 메뉴 + 인증서 보완 + 바뀐 주소 후보.
robots.txt 를 지킨다. 결과: out/boards.json"""
import json, re, sys
from urllib.parse import urljoin, urlparse
sys.path.insert(0, ".")
import urllib3
from bs4 import BeautifulSoup
from server.collectors.boards import allowed, get, parse_html, KEY, RECRUIT, DROP, Renderer
urllib3.disable_warnings()
SH, NSH = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (0, 1)
TODO = json.load(open("scripts/univ_todo.json"))[SH::NSH]
ALT = json.load(open("scripts/univ_alt.json"))  # 이름 → 다른 주소 후보 (학교 이름이 바뀌었거나 목록 주소가 틀린 곳)
SC = [(re.compile(r"장학\s*(공지|게시판|공지사항|소식|알림|정보)|공지\s*\(?장학|장학\s*/\s*학자금"), 10),
      (re.compile(r"교외\s*장학|외부\s*장학|장학금\s*(안내|공지|정보|신청)"), 8), (re.compile(r"장학"), 6),
      (re.compile(r"사이트\s*맵|SITEMAP|전체\s*메뉴", re.I), 7),
      (re.compile(r"학생\s*(지원|생활|복지)|캠퍼스\s*라이프|대학\s*생활|학생\s*서비스"), 3),
      (re.compile(r"공지\s*사항|^공지$|알림\s*마당|NOTICE|학사\s*공지|학생\s*공지"), 3)]
HREF = re.compile(r"scholar|janghak|jangHak|sch_|/scho", re.I)
RD = Renderer()


def fetch(u, render=False):
    if not allowed(u):
        return "", u
    html, final = "", u
    if not render:
        try:
            r = get(u, timeout=15); html, final = r.text, r.url
        except Exception:
            pass
    if render or len(html) < 3000 or html.count("<a") < 25:
        h = RD.html(u, 3500) if RD.browser else ""
        if len(h) > len(html):
            html = h
    return html, final


def good_posts(html, base):
    n = 0
    for it in parse_html(html, base):
        t = it["title"]
        if KEY.search(t) and RECRUIT.search(t) and not DROP.search(t) and len(t) >= 10:
            n += 1
    return n


def cands(html, base, doms):
    soup = BeautifulSoup(html, "html.parser"); out = []
    for f in soup.find_all(["frame", "iframe"]):
        if f.get("src"): out.append((6, "frame", urljoin(base, f["src"])))
    for a in soup.find_all("a"):
        t = " ".join(a.get_text(" ").split()) or a.get("title") or ""
        href = a.get("href") or ""
        if not href or href.startswith(("javascript", "#", "mailto", "tel")) or len(t) > 30: continue
        u = urljoin(base, href); h = urlparse(u).hostname or ""
        if not any(h.endswith(d) for d in doms) or re.search(r"\.(pdf|hwp|hwpx|jpg|png|zip|xlsx?)$", u, re.I): continue
        sc = next((s for rx, s in SC if rx.search(t)), 0)
        if HREF.search(u): sc = max(sc, 7)
        if sc: out.append((sc, t, u))
    return out


def home_of(name, dom):
    for d in [dom] + ALT.get(name, []):
        for u in (f"https://www.{d}/", f"https://{d}/", f"http://www.{d}/"):
            h, f = fetch(u)
            if len(h) > 500:
                return d, f, h
    return None, None, None


def one(name, dom):
    d, home, html = home_of(name, dom)
    if not d:
        return {"err": "unreachable"}
    if not allowed(home):
        return {"err": "robots", "home": home}
    doms = {d, urlparse(home).hostname.replace("www.", "")}
    rh = RD.html(home, 4000) if RD.browser else ""  # 메뉴를 자바스크립트로 그리는 학교가 많아 첫 화면은 늘 브라우저로도 연다
    queue = cands(html, home, doms) + (cands(rh, home, doms) if rh else [])
    if len(queue) < 3:  # 인트로·게이트 화면: 같은 학교 주소의 첫 링크들을 따라간다
        for src in (html, rh):
            for a in BeautifulSoup(src or "", "html.parser").find_all("a")[:8]:
                u = urljoin(home, a.get("href") or "")
                if any((urlparse(u).hostname or "").endswith(x) for x in doms) and not (a.get("href") or "").startswith(("javascript", "#")):
                    queue.append((5, "intro", u))
    diag = {"len": len(html), "rlen": len(rh), "a": html.count("<a"), "ra": rh.count("<a"), "q": len(queue), "render": bool(RD.browser)} seen = {home.split("#")[0]}; best = None; visits = 0
    while queue and visits < 24:
        queue.sort(key=lambda x: -x[0]); sc, t, u = queue.pop(0)
        k = u.split("#")[0]
        if k in seen: continue
        seen.add(k); visits += 1
        h, f = fetch(u)
        if not h: continue
        n = good_posts(h, f)
        if n >= 2 and (not best or n > best["n"] or (n == best["n"] and "장학" in t and "장학" not in best["label"])):
            best = {"url": f, "label": t, "n": n, "home": home, "dom": d}
            if n >= 5 and "장학" in t: break
        if sc >= 5 or re.search(r"사이트\s*맵|sitemap|전체\s*메뉴", t, re.I):  # 장학 메뉴·사이트맵 아래 하위 메뉴까지
            for x in cands(h, f, doms):
                if x[2].split("#")[0] not in seen: queue.append((x[0] - 1, x[1], x[2]))
    return best or {"err": "notfound", "home": home, "visits": visits, **diag}


res = {}
for name, dom, _ in TODO:
    try:
        res[name] = one(name, dom)
    except Exception as e:
        res[name] = {"err": repr(e)[:80]}
    json.dump(res, open(f"out/boards{SH}.json", "w"), ensure_ascii=False, indent=0)
RD.close()
print(sum(1 for v in res.values() if "url" in v), "found of", len(res))
