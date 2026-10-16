import json, sys
sys.path.insert(0, ".")
import requests, urllib3
from bs4 import BeautifulSoup
from server.collectors.boards import allowed, UA, KEY, RECRUIT, DROP, parse_html, DATE
urllib3.disable_warnings()
out = {}
for name, u in json.load(open("scripts/univ_cand.json")):
    try:
        if not allowed(u): out[name] = {"err": "robots"}; continue
        r = requests.get(u, timeout=20, headers={"User-Agent": UA}, verify=False)
        if not r.encoding or r.encoding.lower() == "iso-8859-1": r.encoding = r.apparent_encoding
        its = [i for i in parse_html(r.text, r.url) if RECRUIT.search(i["title"]) and not DROP.search(i["title"])]
        out[name] = {"url": u, "n": len(its), "dated": sum(1 for i in its if i["posted"]), "ex": [i["title"][:50] for i in its[:3]]}
    except Exception as e:
        out[name] = {"err": repr(e)[:80]}
json.dump(out, open("out/cand.json", "w"), ensure_ascii=False, indent=0)
