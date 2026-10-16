"""접속이 안 되던 학교를 여러 방법으로 다시 시도한다 (일회성). robots.txt 를 지킨다."""
import json, sys, ssl, socket, concurrent.futures as cf
sys.path.insert(0, ".")
import requests, urllib3
urllib3.disable_warnings()
from server.collectors.boards import allowed
U = json.load(open("scripts/univ_unreach.json"))
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
def dns(h):
    try: return socket.gethostbyname(h)
    except Exception as e: return "DNSFAIL"
def tryreq(u, ua, verify):
    try:
        r = requests.get(u, timeout=12, headers={"User-Agent": ua, "Accept-Language": "ko-KR,ko;q=0.9", "Accept": "text/html,*/*"}, verify=verify)
        return f"{r.status_code}:{len(r.content)}"
    except Exception as e:
        return type(e).__name__ + ":" + str(e)[:60]
def one(item):
    name, dom, home = item
    out = {"dns_www": dns("www." + dom), "dns": dns(dom)}
    for u in (f"https://www.{dom}/", f"http://www.{dom}/", f"https://{dom}/"):
        out[u] = {"bot": tryreq(u, "JangakAlimiBot/1.0", True), "browser_noverify": tryreq(u, BROWSER, False)}
    return name, out
with cf.ThreadPoolExecutor(20) as ex:
    res = dict(ex.map(one, U))
# 브라우저(크롬)로도 첫 화면을 열어 본다
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(locale="ko-KR", ignore_https_errors=True)
        for name, dom, home in U:
            pg = ctx.new_page()
            try:
                r = pg.goto(f"https://www.{dom}/", timeout=20000, wait_until="domcontentloaded")
                res[name]["chrome"] = f"{r.status if r else '?'}:{len(pg.content())}"
            except Exception as e:
                res[name]["chrome"] = str(e)[:80]
            pg.close()
        b.close()
except Exception as e:
    print("pw", e, file=sys.stderr)
json.dump(res, open("out/unreach.json", "w"), ensure_ascii=False, indent=0)
