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
        rep["_srcs"] = sorted({m.get("source") for m in members})
        rep["_st_all"] = sorted({t for m in members for t in (m.get("school_types") or [])})
        rep["_alltext"] = " ".join(" ".join(str(m.get(k) or "") for k in ("title", "org", "target", "special", "restriction", "residence", "recommend", "selection"))
                                   + " " + (m.get("summary") or "")[:2500] for m in members)
        rep["dupes"] = len(members) - 1
        out.append(rep)
    return out


UNIV_NAME = re.compile(r"([가-힣]{2,10}(?:대학교|대학원대학교|교육대학교|과학기술원))")
OK_SCHOOL = {"4년제(5~6년제포함)", "전문대(2~3년제)", "일반대학원", "전문대학원", "특수대학원", "제한없음", "특정대학"}


NEG = re.compile(r"(지정|추천|협약|선정|대상|참여|해당|소속|배정)\s*대학(교)?(?!\s*(제한\s*)?(없|무관))|(지정|선정|선발|협약)(한|된|을\s*맺은)\s*(\d+\s*개\s*)?대학|본교|학교별\s*(추천|배정)|대학별\s*(추천|배정|인원)|(추천|배정)\s*인원|우리\s*대학|재단\s*지정|협력\s*대학|장학\s*협약|대학의?\s*추천을\s*받|소속\s*대학\s*(장|총장)\s*추천")
OPEN = re.compile(r"전국\s*(?:의과|한의과|치의과|약학|의학)?\s*(?:대학|의대|한의대|치대|약대)|전국\s*(의\s*)?(4년제\s*|소재\s*)?(대학|대학생)|국내\s*(소재\s*)?(4년제\s*|정규\s*)*(대학|대학교)\s*(\(원\)\s*)?(에\s*)?재(학|적)|대학\s*(제한|구분)\s*(없|무관)|모든\s*대학|(학교|대학|소속\s*대학)\s*(제한\s*)?무관|대학교?\s*구분\s*없이")
RES = re.compile(r"주민등록|거주|구민|시민|군민|도민|출신|연고|전입|주소를?\s*두")
PROV = r"서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|충청|전북|전남|전라|경북|경남|경상|제주|부울경|대경|영남|호남|호서"
LOCW = (r"(?:(?:[가-힣]{1,8}(?:특별시|광역시|특별자치도|특별자치시|시|도|군|구)|(?:" + PROV + r")|[가-힣]{2,6}\s*지역)\s*(?:지역\s*)?(?:내\s*)?(?:에\s*)?(?:소재|위치|있는|관내|내)(?:하는|한|의)?"
        r"|도내|관내|시내|군내|구내|지역\s*내|비수도권|지방\s*소재|지방대)")
SCHOOL_LOC = re.compile(r"(?:" + LOCW + r"|(?:[가-힣]{1,8}(?:특별시|광역시|특별자치도|시|도|군)|(?:" + PROV + r"))\s*지역)(?:\s*지역)?\s*(?:소재\s*|에\s*소재한\s*)?(?:\*\s*)?(?:4년제\s*|전문\s*)?(?:대학|대학교|학\s*(?:재학|학생))")
GENERIC_UNIV = re.compile(r"(정규|국내|사이버|방송통신|한국방송통신|전문|일반|대학원|관내|명문|우수|외국|지역|해외|4년제|각|해당|소속|타|원격|기술)")
HOME_OK = re.compile(r"서울|경기|수도권|전국|국내|한국|대한민국|도외|관외|안산|성동")
ALT_OK = re.compile(r"(?:시|도|군|구|지역)\s*외\s*(?:소재\s*)?대학|도외\s*(?:소재\s*)?대학|관외\s*(?:소재\s*)?대학|타\s*지역\s*(?:소재\s*)?대학|타\s*시[·ㆍ]?도\s*(?:소재\s*)?대학|대학\s*소재지\s*(?:무관|제한\s*없)|조건\s*중\s*(?:하나|1개|한\s*가지)|(?:요건|조건|자격)\s*중\s*어느\s*하나(?:를|에)?\s*(?:만족|충족)")
BOTH = re.compile(r"(?:본인|학생|시민|도민|군민|구민|주민)\s*(?:또는|이나|혹은)\s*(?:그\s*)?(?:[가-힣]{0,4}\s*)?(?:부모|보호자|자녀|가족|세대주)")
OTHER_UNIV = re.compile(r"([가-힣]{2,12}(?:대학교|대학원대학교|교육대학교|과학기술원))(?:\s*[가-힣A-Za-z]{0,8}캠퍼스)?")
OWN = re.compile(r"교내|\[교내|본교|근로장학|국가근로|학과\s*장학|학부\s*장학|대학원\s*(우수|연구)|가족\s*장학|형제자매|동문(회)?\s*장학|발전기금|면학장학|가계곤란|어학우수|성적우수\s*장학|사정관")
ABROAD_NO = re.compile(r"고등학교|고교|외국인\s*유학생|해외대학\s*입학|입학지원금|교원연수|교수|전문가\s*장학|포스트닥|Postdoc|저널리스트|영어교사|사비\s*외국인")
HOME_REGIONS = {"서울", "경기"}  # 한양대(서울)·ERICA(경기 안산)·한양여대(서울)


def for_school(rows: list[dict], school: str = "한양대학교,한양여자대학교") -> list[dict]:
    """한양대·한양여대 학생이 실제로 지원할 수 있는 장학금만 남긴다.

    남기는 근거가 있어야만 남긴다.
      - 한양대 자체 출처(HY-in 장학캘린더, 한양대 공지)에 있는 장학금
      - 공고에 '한양'이 대상으로 나오는 장학금
      - 한국장학재단 DB에서 대학 유형이 일반(4년제·전문대·대학원)인 장학금
      - 다른 곳에서 온 공고는 '전국 대학', '대학 제한 없음' 같은 개방 근거나 거주지 기준(주민등록·구민 등)이 있을 때만
    빼는 경우
      - 고등학생·학점은행제 대상, 학교 유형이 맞지 않는 장학금
      - 지정·추천·협약·참여 대학, '본교', 대학별 추천 인원처럼 특정 대학 학생만 받는 공고 (한양 언급이 없으면)
      - '도내·관내·OO 소재 대학 재학생'처럼 학교 위치가 서울·경기가 아닌 지역으로 묶인 공고
      - 근거를 찾을 수 없는 다른 대학 게시판 공고
    """
    key = "한양"
    out = []
    for r in rows:
        if r.get("level") in ("고등학생", "학점은행제"):
            continue
        st = set(r.get("_st_all") or r.get("school_types") or [])
        st.discard("특정대학") if r.get("source") in ("board",) else None
        if st and not (st & OK_SCHOOL):
            continue
        srcs = set(r.get("_srcs") or [r.get("source")])
        text = r.get("_alltext") or ""
        hy_named = bool(re.search(r"한양대|한양여대|한양여자대|한양\s*대학교|HYU", text.replace("한양·한여", "")))
        if r.get("level") == "해외유학" and ABROAD_NO.search(r.get("title", "") + " " + (r.get("target") or "")):
            continue
        if srcs <= {"board", "legacy"} and OWN.search(r.get("title", "")) and not hy_named:
            continue  # 다른 대학의 교내·근로·학과 장학
        elig = " ".join(str(r.get(k) or "") for k in ("title", "target", "special", "residence", "restriction"))
        drop = False
        src = elig + " " + text
        alt = bool(ALT_OK.search(src) or OPEN.search(src))
        for m in SCHOOL_LOC.finditer(src):
            g = m.group(0)
            if hy_named:
                break
            if re.search(r"비수도권|지방", g):
                drop = True
                break
            if HOME_OK.search(src[max(0, m.start() - 15): m.end()]) or alt:
                continue
            line = re.split(r"[○□◦•\n]", src[max(0, m.start() - 150): m.start()])[-1] + src[m.start(): m.end() + 80].split("\n")[0].split("○")[0]
            line = BOTH.sub("", line)
            either = re.search(r"(거주|주소|주민등록|시민|도민|군민|구민)[^○□\n]{0,40}(또는|이거나|혹은|아니더라도)[^○□\n]{0,60}대학", line) or \
                     re.search(r"대학[^○□\n]{0,30}(또는|이거나|혹은)[^○□\n]{0,60}(거주|주소|주민등록|시민|도민|군민|구민)", line) or \
                     re.search(r"대학[^○□\n]{0,40}(자를|학생을|학생도|자도)\s*포함", line)
            if either:
                continue  # 거주지 또는 학교 위치 중 하나만 맞으면 되는 경우
            drop = True
            break
        if drop:
            continue  # 학교 위치가 서울·경기 밖으로 묶인 장학
        if srcs & {"hyin", "hanyang"}:
            out.append(r)  # 한양대가 직접 안내한 장학
            continue
        if re.search(r"외국인\s*(유학생|학생)", r.get("title", "") + " " + (r.get("target") or "")[:200]):
            continue
        pos = " ".join(str(r.get(k) or "") for k in ("target", "special", "title"))
        names = {n for n in OTHER_UNIV.findall(pos) if not GENERIC_UNIV.match(n)}
        if names and not hy_named and not OPEN.search(pos):
            continue  # 공고에 다른 대학 이름만 대상으로 적힌 장학
        neg = NEG.search(text)
        if neg and not hy_named:
            continue
        kosaf = any(x.startswith("kosaf") for x in srcs)
        if kosaf:
            kst = set(r.get("_st_all") or [])
            home_loc = any(HOME_OK.search(src[max(0, m.start() - 15): m.end()]) for m in SCHOOL_LOC.finditer(src))
            if kst and kst <= {"특정대학"} and not (hy_named or OPEN.search(src) or home_loc):
                continue  # 한국장학재단 DB에 '특정대학'으로만 등록된 장학
            out.append(r)
            continue
        # 대학 게시판·기존 수집본에서만 온 공고: 열려 있다는 근거가 있어야 남긴다
        if hy_named or OPEN.search(text) or (RES.search(text) and r.get("region") not in ("",)) or RES.search(text):
            r["school_check"] = False
            out.append(r)
            continue
    for r in out:
        r.pop("_univ_only", None)
        r.pop("_hy", None)
        r.pop("_relay_ok", None)
        r.pop("_relay_school", None)
        r.pop("_relay_schools", None)
        r.pop("_relay_text", None)
        for k in ("_srcs", "_st_all", "_alltext"):
            r.pop(k, None)
    return out
