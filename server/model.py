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
    "links", "verified",
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


def status_of(start: str, end: str, today: str | None = None) -> str:
    today = today or date.today().isoformat()
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


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
