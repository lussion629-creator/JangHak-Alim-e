"""전국 대학 목록과 공식 홈페이지 주소 (위키데이터) — 학교 포털 직접 연결용 목록을 만드는 일회성 도구."""
import json, re, sys, requests
Q = """
SELECT DISTINCT ?u ?name ?site ?type WHERE {
  VALUES ?type { wd:Q3918 wd:Q2418495 wd:Q902104 wd:Q15936437 wd:Q1371037 wd:Q875538 wd:Q189004 wd:Q23002054 wd:Q23002039 wd:Q38723 wd:Q1188663 wd:Q5341295 }
  ?u wdt:P31/wdt:P279* ?type ; wdt:P17 wd:Q884 ; wdt:P856 ?site .
  ?u rdfs:label ?name . FILTER(LANG(?name)="ko")
  FILTER NOT EXISTS { ?u wdt:P576 ?end }
}"""
r = requests.get("https://query.wikidata.org/sparql", params={"query": Q, "format": "json"}, headers={"User-Agent": "JangakAlimi/1.0 (univ list)"}, timeout=120)
rows = r.json()["results"]["bindings"]
out = {}
for b in rows:
    n = b["name"]["value"]; s = b["site"]["value"]
    if not re.search(r"대학|대학교|University|College", n): continue
    out.setdefault(n, set()).add(s)
json.dump({k: sorted(v) for k, v in sorted(out.items())}, sys.stdout, ensure_ascii=False, indent=0)
