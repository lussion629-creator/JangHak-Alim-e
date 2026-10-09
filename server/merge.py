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

    def union(i, j):
        pi, pj = find(i), find(j)
        if pi != pj:
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
        hay = _hangul(rows[i].get("title", ""))
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

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    out = []
    for ids in groups.values():
        members = [rows[i] for i in ids]
        rep = dict(max(members, key=_richness))
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
    return out
