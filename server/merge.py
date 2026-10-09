"""여러 출처에 같은 장학금이 올라온 경우 하나로 합친다.

같은 공고 판단
  - 운영기관 핵심 이름(예: '고속도로', '송화', '아산사회복지')이 같거나 한쪽 제목에 다른 쪽 기관 이름이 들어 있고
  - 모집 시기가 가깝다 (마감일 10일 이내, 날짜가 하나뿐이면 75일 이내)
  - 한국장학재단 DB끼리, HY-in 끼리는 서로 다른 프로그램이므로 합치지 않는다
  - '한국장학재단', 'OO대학교' 처럼 여러 프로그램을 운영하는 기관은 제목 핵심어까지 같아야 합친다
대표 항목은 정보가 가장 많은 것을 고르고, 비어 있는 칸은 나머지에서 채운다.
"""
from __future__ import annotations

import re
from datetime import date

FAMILY = {"kosaf_univ": "kosaf", "kosaf_high": "kosaf", "kosaf_abroad": "kosaf", "kosaf_creditbank": "kosaf", "hyin": "hyin"}
RANK = {"kosaf_univ": 0, "kosaf_high": 0, "kosaf_abroad": 0, "kosaf_creditbank": 0, "hyin": 1, "legacy": 2, "hanyang": 3, "board": 4}
STOP = r"(20\d\d|\d+학년도|\d+년도?|\d학기|[1-4]학기|상반기|하반기|신규|정기|추가|재공고|연장|모집|선발|공고|안내|신청|접수|계획|장학생|장학금|장학|학생|대학생|대학원생|교외|교내|외부|홍보|기간|의|및|제\d+기|\d+기)"
SUFFIX = r"(사회복지재단|복지재단|문화재단|장학재단|육영재단|교육재단|학술재단|인재육성재단|장학문화재단|장학회|육영회|재단|공제회|협회|센터|진흥원)$"
GENERIC_T = re.compile(r"국가근로|교내근로|근로장학|국가장학금|학자금\s*대출|교내\s*장학|가계곤란|성적우수\s*장학")
GENERIC = re.compile(r"한국장학재단|대학교|대학$|^교육부|^국가")
FILL = ("amount", "target", "income", "gpa", "special", "residence", "selection", "quota", "restriction", "recommend",
        "documents", "summary", "apply_url", "url", "start", "end", "posted")


def _hangul(s: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]", "", s or "")


def org_core(org: str) -> str:
    o = re.sub(r"\(.*?\)|（.*?）|재단법인|사단법인|주식회사|\(재\)|\(사\)", "", org or "")
    o = _hangul(o)
    return re.sub(SUFFIX, "", o)


def title_core(title: str) -> str:
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|（[^）]*）|<[^>]*>|~[^ ]*", " ", title or "")
    t = re.sub(STOP, " ", t)
    return _hangul(t)


def _d(s: str):
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def _near(a: dict, b: dict) -> bool:
    ea, eb = _d(a.get("end")), _d(b.get("end"))
    if ea and eb:
        return abs((ea - eb).days) <= 10
    da = ea or _d(a.get("start")) or _d(a.get("posted"))
    db = eb or _d(b.get("start")) or _d(b.get("posted"))
    if da and db:
        return abs((da - db).days) <= 75
    return True


def _richness(r: dict) -> int:
    return sum(1 for k in FILL if r.get(k)) * 10 - RANK.get(r.get("source"), 5)


def merge(rows: list[dict]) -> list[dict]:
    n = len(rows)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    info = []
    for r in rows:
        oc = org_core(r.get("org", ""))
        tc = title_core(r.get("title", ""))
        generic = bool(GENERIC.search(r.get("org", ""))) or len(oc) < 2
        info.append((oc, tc, generic))

    def can(i, j):
        a, b = rows[i], rows[j]
        fa, fb = FAMILY.get(a["source"]), FAMILY.get(b["source"])
        if fa and fa == fb:
            return False
        if a.get("level") and b.get("level") and a["level"] != b["level"] and "고등학생" in (a["level"], b["level"]):
            return False
        return _near(a, b)

    by_org: dict[str, list[int]] = {}
    for i, (oc, tc, generic) in enumerate(info):
        if not generic:
            by_org.setdefault(oc, []).append(i)
    by_title: dict[str, list[int]] = {}
    for i, (oc, tc, generic) in enumerate(info):
        if len(tc) >= 4:
            by_title.setdefault(tc, []).append(i)

    # 묶음(그룹)마다 출처 계열·운영기관·날짜 범위를 기억해 두고, 서로 충돌하면 합치지 않는다.
    # (한 공고가 두 기관을 동시에 가리켜 엉뚱한 공고끼리 연쇄로 묶이는 것을 막는다)
    def _key_date(r):
        return _d(r.get("end")) or _d(r.get("start")) or _d(r.get("posted"))
    meta = {}
    for i, r in enumerate(rows):
        oc = info[i][0]
        org_is_title = _hangul(r.get("org", "")) == _hangul(r.get("title", ""))  # HY-in 처럼 제목을 기관명으로 쓴 경우
        anchor = oc if (len(oc) >= 2 and not info[i][2] and not org_is_title and not re.search(r"대학교?$|대$", r.get("org", ""))) else ""
        d = _key_date(r)
        meta[i] = {"fam": {FAMILY.get(r["source"])} - {None}, "orgs": {anchor} - {""}, "lo": d, "hi": d}

    def compatible(a, b):
        if a["fam"] & b["fam"]:
            return False
        for x in a["orgs"]:
            for y in b["orgs"]:
                if not (x in y or y in x):
                    return False
        lo = min([d for d in (a["lo"], b["lo"]) if d] or [None]) if (a["lo"] or b["lo"]) else None
        hi = max([d for d in (a["hi"], b["hi"]) if d] or [None]) if (a["hi"] or b["hi"]) else None
        return not (lo and hi and (hi - lo).days > 120)

    def union(i, j):
        pi, pj = find(i), find(j)
        if pi == pj or not compatible(meta[pi], meta[pj]):
            return
        a, b = meta[pi], meta[pj]
        ds = [d for d in (a["lo"], a["hi"], b["lo"], b["hi"]) if d]
        meta[pi] = {"fam": a["fam"] | b["fam"], "orgs": a["orgs"] | b["orgs"], "lo": min(ds) if ds else None, "hi": max(ds) if ds else None}
        parent[pj] = pi

    # 1) 같은 기관 핵심 이름
    for ids in by_org.values():
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                if can(ids[x], ids[y]):
                    union(ids[x], ids[y])
    # 2) 같은 제목 핵심어
    for ids in by_title.values():
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                if can(ids[x], ids[y]):
                    union(ids[x], ids[y])
    # 3) 기관 이름이 비어 있거나 대학 이름인 공고: 제목 안에 다른 항목의 기관 핵심 이름이 있으면 같은 공고
    orgs = sorted((oc for oc in by_org if len(oc) >= 3), key=len, reverse=True)
    for i, (oc, tc, generic) in enumerate(info):
        if not generic and rows[i]["source"] not in ("board", "legacy", "hanyang"):
            continue
        hay = _hangul(rows[i].get("title", "") + " " + (rows[i].get("target") or "")[:200])
        for o in orgs:
            if o in hay:
                for j in by_org[o]:
                    if j != i and can(i, j):
                        union(i, j)
                break

    # 4) HY-in·공지처럼 제목이 짧은 항목: 그 핵심어가 다른 항목의 제목·기관에 들어 있으면 같은 공고
    cores = [(_hangul(r.get("title", "")) + org_core(r.get("org", ""))) for r in rows]
    for i, (oc, tc, generic) in enumerate(info):
        if rows[i]["source"] not in ("hyin", "hanyang") or len(tc) < 3:
            continue
        for j in range(n):
            if j != i and rows[j]["source"] != rows[i]["source"] and tc in cores[j] and can(i, j):
                union(i, j)

    # 5) 제목이 다르게 적힌 같은 공고: 핵심어 글자쌍(bigram) 유사도 0.55 이상 + 시기 가까움
    def grams(t):
        return {t[k:k + 2] for k in range(len(t) - 1)}
    G = [grams(i[1]) for i in info]
    def month(r):
        d = (r.get("end") or r.get("start") or r.get("posted") or "")[:7]
        return d
    buckets: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        if len(info[i][1]) >= 4 and month(r):
            buckets.setdefault(month(r), []).append(i)
    keys = sorted(buckets)
    for bi, k in enumerate(keys):
        pool = buckets[k] + (buckets[keys[bi + 1]] if bi + 1 < len(keys) else [])
        for x in range(len(buckets[k])):
            i = buckets[k][x]
            for j in pool:
                if j <= i or find(i) == find(j):
                    continue
                if FAMILY.get(rows[i]["source"]) and FAMILY.get(rows[i]["source"]) == FAMILY.get(rows[j]["source"]):
                    continue
                a, b = G[i], G[j]
                if not a or not b:
                    continue
                if GENERIC_T.search(rows[i].get("title", "")) or GENERIC_T.search(rows[j].get("title", "")):
                    continue
                sim = len(a & b) / len(a | b)
                small = min(len(a), len(b))
                contain = len(a & b) / small if small >= 8 else 0
                if (sim >= 0.55 or (contain >= 0.85 and sim >= 0.4)) and can(i, j):
                    union(i, j)

    # 6) 드문 고유 단어(예: '토박이', '김정옥', '봄내')를 함께 쓰는 공고는 같은 공고로 본다
    COMMON = re.compile(r"^(장학|장학생|장학금|선발|모집|안내|공고|신청|지원|재단|학년도|하반기|상반기|대학생|학기|신규|추가|연장|기간|사업|프로그램|우수|특별|일반|재학생)$")
    def toks(t):
        t = re.sub(r"\[[^\]]*\]", " ", t or "")
        out = set()
        for w in re.findall(r"[가-힣]{2,}", t):
            w = re.sub(STOP, "", w)
            if len(w) >= 3 and not COMMON.match(w):
                out.add(w)
        return out
    T = [toks(r.get("title", "")) | ({org_core(r.get("org", ""))} if len(org_core(r.get("org", ""))) >= 3 and not info[i][2] else set()) for i, r in enumerate(rows)]
    df: dict[str, list[int]] = {}
    for i, ts in enumerate(T):
        for w in ts:
            df.setdefault(w, []).append(i)
    for w, ids in df.items():
        if 2 <= len(ids) <= 6:
            for x in range(len(ids)):
                for y in range(x + 1, len(ids)):
                    i, j = ids[x], ids[y]
                    if find(i) != find(j) and not (GENERIC_T.search(rows[i].get("title", "")) or GENERIC_T.search(rows[j].get("title", ""))) and can(i, j):
                        union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for ids in groups.values():
        members = [rows[i] for i in ids]
        today = date.today().isoformat()
        rep = dict(max(members, key=lambda m: ((m.get("end") or "") >= today or (m.get("start") or "") >= today, _richness(m))))
        for m in members:
            if m is rep:
                continue
            for k in FILL:
                if not rep.get(k) and m.get(k):
                    rep[k] = m[k]
            if not rep.get("support") and m.get("support"):
                rep["support"] = m["support"]
        links = []
        for m in members:
            for l in [{"name": "공고 원문", "url": m.get("url")}] + list(m.get("links") or []):
                if l.get("url") and l["url"] not in [x["url"] for x in links]:
                    links.append({"name": "공고 원문", "url": l["url"]})
        rep["links"] = links[:8]
        if rep.get("source") == "board" and rep.get("org_type") == "대학 게시판" and any(m.get("_relay_ok") for m in members):
            other = [m.get("org") for m in members if m.get("org") and m.get("org_type") != "대학 게시판"]
            rep["org"] = other[0] if other else ("" if re.search(r"대학교|대학$", rep.get("org") or "") else rep.get("org", ""))
        relay = [m.get("source") == "board" and m.get("org_type") == "대학 게시판" and not m.get("_hy") for m in members]
        # 다른 대학 게시판에만 있고 운영기관이 그 대학 자신인 공고(교내 장학)는 그 학교 학생 전용
        rep["_univ_only"] = all(relay) and not any(m.get("_relay_ok") for m in members)
        rep["school_check"] = all(relay)
        schools = {m.get("_relay_school") for m in members if m.get("_relay_school")}
        rep["_relay_schools"] = sorted(schools)
        rep["_relay_text"] = " ".join(((m.get("target") or "") + " " + (m.get("summary") or "")[:1500]) for m in members if m.get("_relay_school"))
        rep["dupes"] = len(members) - 1
        out.append(rep)
    return out


UNIV_NAME = re.compile(r"([가-힣]{2,10}(?:대학교|대학원대학교|교육대학교|과학기술원))")
OK_SCHOOL = {"4년제(5~6년제포함)", "전문대(2~3년제)", "일반대학원", "전문대학원", "특수대학원", "제한없음", "특정대학"}


def for_school(rows: list[dict], school: str = "한양대학교,한양여자대학교") -> list[dict]:
    """그 학교 학생이 지원할 수 없는 장학금을 뺀다.

    - 고등학생 대상, 학점은행제 대상, 전문대·원격대 등 다른 학교 유형만 대상인 장학금
    - 다른 대학 게시판에만 올라온 그 대학 학생 전용 공고 (다른 출처에서도 확인된 공고는 남김)
    - '특정대학' 대상인데 공고에 다른 대학 이름만 있고 우리 학교가 없는 장학금
    """
    keys = [x.strip().replace("학교", "").replace("여자대학", "여대").replace("대학", "")[:2] for x in school.split(",") if x.strip()]
    key = keys[0] if keys else "한양"  # '한양' — 한양대·한양여대 모두 포함
    out = []
    for r in rows:
        if r.get("level") in ("고등학생", "학점은행제"):
            continue
        st = set(r.get("school_types") or [])
        if st and not (st & OK_SCHOOL):
            continue
        if r.pop("_univ_only", False):
            continue
        # 한 대학 게시판에만 올라온 외부 장학: 본문에 그 대학 학생만 대상이라고 적혀 있으면 제외
        rs = r.get("_relay_schools") or []
        if r.get("school_check") and len(rs) == 1:
            short = re.sub(r"\s.*$|학교$", "", rs[0]).replace("대학", "대")  # '건국대학교 서울' → '건국대'
            body = r.get("_relay_text", "")
            names = {short, re.sub(r"\s.*$", "", rs[0])}
            if body and any(n and n in body for n in names) and key not in body:
                continue
            if body and re.search(r"본교\s*(재학|학부|소속)|본교생|우리\s*대학\s*재학", body) and key not in body:
                continue
        if r.get("school_check") and len(rs) >= 2:
            r["school_check"] = False  # 여러 대학에 공통으로 온 공고는 학교 제한이 없을 가능성이 높다
        if "특정대학" in st and r.get("source", "").startswith("kosaf"):
            text = " ".join(str(r.get(k, "")) for k in ("title", "org", "special", "restriction", "target", "residence", "summary"))
            names = set(UNIV_NAME.findall(text))
            if names and not any(key in n for n in names) and key not in text:
                continue
        out.append(r)
    for r in out:
        r.pop("_univ_only", None)
        r.pop("_hy", None)
        r.pop("_relay_ok", None)
        r.pop("_relay_school", None)
        r.pop("_relay_schools", None)
        r.pop("_relay_text", None)
    return out
