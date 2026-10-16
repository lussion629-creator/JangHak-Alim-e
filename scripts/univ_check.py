"""후보 대학 홈페이지가 실제로 열리는지 확인 (일회성)."""
import json, re, sys, concurrent.futures as cf, requests, urllib3
urllib3.disable_warnings()
U = json.load(open("scripts/univ_candidates.json"))
def check(item):
    name, doms = item
    for d in doms:
        for url in (f"https://www.{d}/", f"https://{d}/", f"http://www.{d}/", f"http://{d}/"):
            try:
                r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, verify=False, allow_redirects=True)
                html = r.content[:200000].decode(r.apparent_encoding or "utf-8", "ignore")
                t = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
                return name, {"dom": d, "url": url, "final": r.url, "code": r.status_code, "title": re.sub(r"\s+", " ", t.group(1)).strip()[:80] if t else ""}
            except Exception as e:
                last = repr(e)[:80]
    return name, {"dom": doms[0], "err": last}
with cf.ThreadPoolExecutor(24) as ex:
    res = dict(ex.map(check, U.items()))
json.dump(res, sys.stdout, ensure_ascii=False, indent=0)
