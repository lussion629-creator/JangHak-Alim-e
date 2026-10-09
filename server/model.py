"""공통 장학금 레코드 형식과 정규화 도우미."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime

from .regions import infer_region

FIELDS = [
    "id", "source", "source_name", "title", "org", "org_type", "category", "kind", "level",
    "school_types", "grades", "majors", "region", "district", "amount", "amount_won",
    "income", "gpa", "special", "residence", "selection", "quota", "restriction", "recommend",
    "documents", "url", "apply_url", "start", "end", "posted", "summary", "images", "files",
    "links", "verified", "target",
]

NA = {"", "해당없음", "-", "없음", "※ 기관확인필요", "기관확인필요"}


def clean(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\r", "").strip()
    s = re.sub(r"\s*○\s*", "\n○ ", s)
    s = re.sub(r"\s*※", "\n※", s)
    s = re.sub(r"\n{2,}", "\n", s).strip()
    return "" if s in NA else s


def make_id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def norm_date(v) -> str:
    if not v:
        return ""
    s = str(v).strip()
    m = re.match(r"(\d{4})[-./]?\s*(\d{1,2})[-./]?\s*(\d{1,2})", s)
    if not m:
        return ""
    y, mo, d = map(int, m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


_MAN = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만)\s*원?")


def parse_amount(text: str) -> int:
    """지원 금액 문장에서 1인당 최대 금액(원)을 추정. 못 찾으면 0."""
    if not text:
        return 0
    best = 0
    for num, unit in _MAN.findall(text):
        n = float(num.replace(",", ""))
        mult = {"억": 1e8, "천만": 1e7, "백만": 1e6, "만": 1e4}[unit]
        best = max(best, int(n * mult))
    if not best:
        for num in re.findall(r"(\d{1,3}(?:,\d{3}){2,})\s*원", text):
            best = max(best, int(num.replace(",", "")))
    if "등록금" in text and ("전액" in text or "실납입" in text) and best == 0:
        best = -1  # 등록금 전액 (금액 미표기)
    return best if best < 5e9 else 0


SCHOOL_TOKENS = ["4년제(5~6년제포함)", "전문대(2~3년제)", "기술대학", "원격대학", "일반대학원", "전문대학원", "특수대학원", "학점은행제 대학", "해외대학", "특정대학", "제한없음"]
GRADE_TOKENS = ["대학신입생", "대학2학기", "대학3학기", "대학4학기", "대학5학기", "대학6학기", "대학7학기", "대학8학기이상",
                "전문대신입생", "전문대2학기", "전문대3학기", "전문대4학기이상", "석사신입생(1학기)", "석사2학기이상", "박사과정", "제한없음",
                "고1", "고2", "고3", "1학년", "2학년", "3학년"]
MAJOR_TOKENS = ["공학계열", "교육계열", "사회계열", "예체능계열", "의약계열", "인문계열", "자연계열", "특정학과", "제한없음"]


def split_tokens(text: str, tokens) -> list[str]:
    text = text or ""
    if not text or text == "해당없음":
        return []
    out = [t for t in tokens if t in text]
    return out


def status_of(start: str, end: str, today: str | None = None, posted: str = "") -> str:
    today = today or date.today().isoformat()
    if not start and not end and posted:
        from datetime import timedelta
        return "모집중" if posted >= (date.fromisoformat(today) - timedelta(days=30)).isoformat() else "마감"
    if end and end < today:
        return "마감"
    if start and start > today:
        return "예정"
    if start or end:
        return "모집중"
    return "상시/미정"


def expected_next(start: str, end: str, today: str | None = None) -> str:
    """마감된 정기 장학금의 다음 모집 예상 시기(작년과 같은 달 기준)."""
    today = today or date.today().isoformat()
    base = start or end
    if not base or (end and end >= today):
        return ""
    y, m = int(base[:4]), int(base[5:7])
    ty, tm = int(today[:4]), int(today[5:7])
    while (y, m) < (ty, tm):
        y += 1
    return f"{y}-{m:02d}"


_RRN = re.compile(r"\b(\d{6})-?([1-4])\d{6}\b")


def safe_url(u) -> str:
    u = (u or "").strip().split()[0] if (u or "").strip() else ""
    if re.match(r"^(www\.|[a-z0-9-]+\.(go|or|co|ac|re|ne)\.kr|[a-z0-9-]+\.(kr|com|org|net))", u, re.I):
        u = "http://" + u
    return u if re.match(r"^https?://[^\s<>\"']+$", u, re.I) else ""


def scrub(text: str) -> str:
    """주민등록번호처럼 보이는 숫자는 가린다 (공고문에 예시로 들어간 경우 대비)."""
    return _RRN.sub(r"\1-\2******", text) if isinstance(text, str) else text


def finalize(rec: dict) -> dict:
    rec["url"] = safe_url(rec.get("url"))
    rec["apply_url"] = safe_url(rec.get("apply_url"))
    rec["images"] = [u for u in (rec.get("images") or []) if safe_url(u)]
    rec["links"] = [{"name": str(l.get("name", ""))[:120], "url": safe_url(l.get("url"))} for l in (rec.get("links") or []) if isinstance(l, dict) and safe_url(l.get("url"))]
    for k, v in list(rec.items()):
        if isinstance(v, str):
            rec[k] = scrub(v)
    out = {k: rec.get(k, "" if k not in ("school_types", "grades", "majors", "images", "files", "links") else []) for k in FIELDS}
    if not out.get("region"):
        out["region"], out["district"] = infer_region(out.get("org", ""), out.get("residence", ""), out.get("title", ""))
    if not out.get("amount_won"):
        out["amount_won"] = parse_amount(out.get("amount", "") + " " + out.get("summary", "")[:400])
    out["verified"] = bool(out.get("verified"))
    payload = {k: v for k, v in out.items() if k not in ("id",)}
    out["hash"] = hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    return out


_PFX = r"^\s*(?:[0-9]+[.)]|[가-하][.)]|[■□○●▶▷◆◇※\-·•<\[])?\s*"
_HEADS = [r"(자격\s*요건|신청\s*자격|지원\s*자격|선발\s*자격|자\s*격)", r"(지원\s*대상|선발\s*대상|모집\s*대상|신청\s*대상)", r"(대\s*상)"]
_NEXT = re.compile(r"^\s*(?:[0-9]+[.)]|[가-하][.)]|[■□▶◆]|\[)\s*(지원\s*(금액|내용|내역|규모)|장학\s*금액|선발\s*(인원|방법|절차|일정)|제출\s*(서류|방법)|신청\s*(방법|기간)|접수|일정|문의|기타|유의|중요)")


def extract_target(text: str) -> str:
    """공고 본문에서 '자격 요건/지원 대상' 부분만 뽑는다. 인원만 적힌 '대상: 총 2명'은 건너뛴다."""
    if not text:
        return ""
    lines = [l.rstrip() for l in text.splitlines()]
    for head in _HEADS:
        rx = re.compile(_PFX + head + r"\s*[\]>:)]?\s*:?")
        for i, l in enumerate(lines):
            m = rx.match(l)
            if not m:
                continue
            out = []
            rest = l[m.end():].strip(" :-")
            if rest:
                out.append(rest)
            for l2 in lines[i + 1:]:
                if _NEXT.match(l2) or (not l2.strip() and len(out) >= 2):
                    break
                if l2.strip():
                    out.append(l2.strip())
                if len(out) >= 12:
                    break
            block = "\n".join(out).strip()
            if block and not re.fullmatch(r"(총\s*)?\d+\s*명.*", block.split("\n")[0]) or len(out) > 1:
                return block[:700]
    return ""


def lines_with(text: str, rx: str) -> str:
    return "\n".join(l.strip() for l in (text or "").splitlines() if re.search(rx, l))[:400]


SUPPORT = [
    ("dorm", r"기숙사|생활관|학사관|주거|숙소|입주|월세|임대주택|공공학사|행복기숙사"),
    ("tuition", r"등록금|수업료|학비|납입금|입학금|실납입"),
    ("living", r"생활비|생활\s*지원|생활장학|학업\s*장려|면학|생계|교통비|식비|도서구입"),
    ("loan", r"대출|이자\s*지원|이자지원|상환"),
    ("work", r"근로장학|국가근로|교내근로|교외근로|근로학생|장학조교|생활도우미|학생\s*도우미"),
]


def support_of(r: dict) -> list:
    text = " ".join([r.get("title", ""), r.get("amount", ""), r.get("kind", ""), (r.get("summary") or "")[:500]])
    tags = [k for k, rx in SUPPORT if re.search(rx, text)]
    if "work" in tags or r.get("kind") in ("교내근로", "교외근로"):
        return ["work"]  # 근로장학은 근로 칸에만 둔다
    if "loan" in tags and len(tags) > 1 and not re.search(r"대출|이자", r.get("title", "")):
        tags.remove("loan")
    return tags


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------- 공고 본문 정리 ----------------
_END = re.compile(r"^(이전글|다음글|이전 글|다음 글|목록|목록으로|저작권\s*등|개인정보\s*처리방침|Copyright|COPYRIGHT|ⓒ|©|인쇄|글쓰기|수정|삭제|답글|공유하기|SNS 공유)")
_JUNK = re.compile(r"(File size|Times have been downloaded|KByte|다운로드\s*:?\s*\d+\s*회|미리보기\s*:?\s*\d|\.(pdf|hwpx?|docx?|xlsx?|pptx?|jpe?g|png|gif|zip)\b|조회수?\s*\d|^\d{1,6}$|\*{3,}|^작성자|^등록일|^조회|^첨부파일$|바로가기|오늘 하루 보지|popup|로그인|통합검색|페이스북|트위터|블로그|북마크|^\(?\d+(\.\d+)?\s*[KM]B\)?$|^\s*\(\s*$|^\s*\)\s*$|^[a-z0-9_]{3,20}$)", re.I)
_PRE_JUNK = re.compile(r"(File size|Times have been downloaded|KByte|다운로드\s*:?\s*\d+\s*회|미리보기\s*:?\s*\d|\.(pdf|hwpx?|docx?|xlsx?|pptx?|jpe?g|png|gif|zip)\b|\*{3,}|바로가기|오늘 하루 보지|popup|로그인|통합검색|페이스북|트위터|블로그|북마크|^\(?\d+(\.\d+)?\s*[KM]B\)?$)", re.I)
_LABELS = [
    ("대상", r"(선발|지원|모집|신청)\s*대상(자)?|지원\s*자격|신청\s*자격|자격\s*요건|대\s*상(자)?|자\s*격"),
    ("지원 내용", r"지원\s*(금액|내용|내역|규모)|장학\s*(금액|혜택)|장학금(?=\s*[:：]|\s*$)|혜\s*택|지급\s*(금액|액)"),
    ("선발 인원", r"선발\s*(인원|규모)|모집\s*인원|인\s*원"),
    ("신청 기간", r"(신청|접수|모집|지원)\s*(기간|기한|일정)|기\s*간"),
    ("신청 방법", r"(신청|접수|지원)\s*(방법|처)|접\s*수\s*처|제출\s*방법"),
    ("제출 서류", r"(제출|구비)\s*서류"),
    ("선발 방법", r"선발\s*(방법|과정|절차|일정)|심사\s*방법"),
    ("하는 일", r"주요\s*업무|업무\s*내용|담당\s*업무|근로\s*내용"),
    ("근무 조건", r"근무\s*(조건|장소|시간|일시|기간|요일)|급\s*여|시\s*급"),
    ("문의", r"문\s*의\s*(처|사항)?|담\s*당\s*자?"),
]
_LAB_RX = re.compile(r"^\s*(?:[0-9]{1,2}\s*[.)]|[가-하]\s*[.)]|[■□○●▶▷◆◇❍•·\-]|\[)?\s*(" + "|".join(f"(?P<g{i}>{rx})" for i, (_, rx) in enumerate(_LABELS)) + r")(?![가-힣])\s*[\]:：]?\s*[:：]?\s*(?P<rest>.*)$")


BLOCK_TAGS = ["p", "div", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "ul", "ol", "section", "article", "blockquote", "pre"]


def html_block_text(el) -> str:
    """블록 태그에서만 줄을 바꾸고, span·strong 같은 글자 꾸밈은 한 줄로 이어 붙인다."""
    for br in el.find_all("br"):
        br.replace_with("\n")
    for tag in el.find_all(["td", "th"]):
        tag.append(" ")
    for tag in el.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.append("\n")
    t = el.get_text("")
    lines = [re.sub(r"[ \t\u00a0\u200b]+", " ", l).strip() for l in t.splitlines()]
    return "\n".join(l for l in lines if l)


def _html_to_text(t: str) -> str:
    if re.search(r"<(span|br|p|div|table|td|strong|b|font)\b", t or "", re.I):
        from bs4 import BeautifulSoup
        t = html_block_text(BeautifulSoup(t, "html.parser"))
    return t


_MARK = re.compile(r"^(?:[0-9]{1,2}\s*[.)]|[가-하]\s*[.)]|[①-⑳❶-❿➊-➓]|\d\ufe0f?\u20e3|[■□○●▶▷►◆◇❍•·\-※*✅➡ㅇ❑◦▪]|\(\d+\)|\[|<)")
_TERM = re.compile(r"([.!?。]|다|요|음|함|임|됨|것|[)\]]|까지|바랍니다|니다)\s*$")
_PART = re.compile(r"^(을|를|은|는|에|의|와|과|로|으로|및|부터|까지|에서|하여|하고|하는|한\s|\)|,|~|：|:)")


def _join_fragments(lines: list[str]) -> list[str]:
    """글자 꾸밈 때문에 잘게 쪼개진 줄을 문장 단위로 다시 붙인다."""
    out: list[str] = []
    for l in lines:
        if out and re.fullmatch(r"\s*(\d{1,2}|[가-하]|[IVX]{1,4})\s*[.)]\s*", out[-1]):
            out[-1] = out[-1] + " " + l  # 번호만 있는 줄은 다음 줄 제목과 합친다
            continue
        if out and re.search(r"\d$", out[-1]) and re.match(r"(년|개월|월|일|세|명|만\s*원|원|학기|회|%|인|순위|시)", l):
            out[-1] = out[-1] + l  # 숫자와 단위가 갈라진 경우
            continue
        if out and not _MARK.match(l) and not _LAB_RX.match(l) and not _TERM.search(out[-1]) and \
                (_PART.match(l) or len(out[-1]) <= 12 or len(l) <= 8):
            out[-1] = out[-1] + ("" if _PART.match(l) and not l.startswith(("및", "하여", "하고")) else " ") + l
        else:
            out.append(l)
    return out


def summarize_body(text: str, title: str = "") -> dict:
    """게시판 본문에서 메뉴·꼬리말을 걷어내고 필요한 항목만 정리한다.
    반환: {"text": 정리된 본문, "fields": {라벨: 값}}"""
    if not text:
        return {"text": "", "fields": {}}
    t = _html_to_text(text)
    lines = [re.sub(r"\s+", " ", l).strip() for l in t.splitlines()]
    lines = [l for l in lines if l and not _PRE_JUNK.search(l)]
    lines = _join_fragments(lines)
    # 학과·전공 이름만 줄줄이 나열된 메뉴 줄은 버린다
    lines = [l for l in lines if not (len(re.findall(r"(전공|학과|학부)", l)) >= 2 and not re.search(r"(재학생|이상|지원|신청|선발|대상|우대|제외|하는 자)", l))]
    core0 = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", title or "").strip()[:8]
    # 같은 게시판의 다른 글 제목(이전·다음 글, 관련 글 목록)은 버린다
    lines = [l for l in lines if not (re.search(r"(선발|모집|신청|지원)?\s*(안내|공고)\s*(\(~?[\d.\s~]+\))?$", l) and len(l) > 15 and (not core0 or core0 not in l) and (l.startswith("[") or re.match(r"^20\d\d", l)))]
    # 시작점: 제목이 나오는 곳 다음 / 없으면 처음 나오는 항목 라벨
    core = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", title or "").strip()[:14]
    start = 0
    for i, l in enumerate(lines):
        if core and core[:10] and core[:10] in l and i < len(lines) - 2:
            start = i + 1
    if start == 0:
        for i, l in enumerate(lines):
            if _LAB_RX.match(l):
                start = max(0, i - 2)
                break
    body = []
    for l in lines[start:]:
        if _END.match(l):
            if len(body) >= 4:
                break
            continue
        if _JUNK.search(l) or (len(l) <= 4 and not re.search(r"\d", l)):
            continue
        body.append(l)
    # 항목별로 묶기
    fields: dict[str, list[str]] = {}
    cur = None
    for l in body:
        m = _LAB_RX.match(l)
        if m:
            lab = next(_LABELS[i][0] for i in range(len(_LABELS)) if m.group(f"g{i}"))
            cur = lab
            rest = m.group("rest").strip(" :：-")
            if lab == "근무 조건" and rest:
                said = re.sub(r"\s+", " ", m.group(f"g{[x[0] for x in _LABELS].index(lab)}"))
                if not re.search(r"조건", said):
                    rest = f"{said}: {rest}"
            fields.setdefault(cur, [])
            if rest:
                fields[cur].append(rest)
            continue
        if re.match(r"^(붙임|※\s*자세한|끝\.?$|20\d\d\s*\.\s*\d{1,2}\s*\.\s*\d{1,2})", l) or re.search(r"(처|과|팀|센터|본부)\s*$", l) and len(l) < 16:
            cur = None
            continue
        limit = 2 if cur == "문의" else 8
        if cur and len(fields.get(cur, [])) < limit and not re.match(r"^\s*[0-9]{1,2}\s*[.)]\s", l):
            fields[cur].append(l)
        elif re.match(r"^\s*[0-9]{1,2}\s*[.)]\s", l):
            cur = None
    fields = {k: "\n".join(v)[:500] for k, v in fields.items() if v}
    if len(fields) >= 2:
        out = "\n".join(f"■ {k}: {v}" if "\n" not in v else f"■ {k}\n{v}" for k, v in fields.items())
    else:
        keep = [l for l in body if len(l) >= 15 or re.search(r"\d.*(원|명|일|월)|[:：]", l)]
        out = "\n".join(keep) if len(keep) >= 2 else ""
    out = re.sub(r"\(\s+", "(", out)
    out = re.sub(r"\s+\)", ")", out)
    out = re.sub(r"(\d)\s+(년|개월|월|일|세|명|만\s*원|원|학기|순위|인당)", r"\1\2", out)
    out = re.sub(r"(※\s*)?자세한 사항은.{0,30}(참고|참조)[^\n]*", "", out).strip()
    return {"text": out[:1800], "fields": fields}
