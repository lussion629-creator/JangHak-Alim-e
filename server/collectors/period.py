"""공고 제목·본문에서 신청 기간(시작~마감)을 읽는 도우미. 여러 학교 게시판 수집기가 함께 쓴다."""
from __future__ import annotations

import re
from datetime import date

_D = r"(?:(20\d{2}|['’]?\d{2})\s*[.년/-]\s*)?(\d{1,2})\s*[./월]\s*(\d{1,2})\s*일?\.?"
_DAY = r"(?:\s*\(\s*[월화수목금토일](?:요일)?\s*\))?(?:\s*\d{1,2}\s*:\s*\d{2})?(?:\s*(?:까지|오전|오후)[^~∼〜\n]{0,8})?"
RANGE = re.compile(_D + _DAY + r"\s*[~∼〜-]\s*" + _D + _DAY)
DUE = re.compile(r"(?:~|∼|〜)\s*" + _D + r"|" + _D + _DAY + r"\s*(?:까지|마감)")
KEY = re.compile(r"신청|접수|모집|제출|지원\s*기간|응모")


def _mk(y, mo, d, base: str) -> str:
    try:
        mo, d = int(mo), int(d)
        if y:
            y = int(str(y).lstrip("'’"))
            y = y + 2000 if y < 100 else y
        else:
            y = int(base[:4])
            if mo < int(base[5:7]) - 6:
                y += 1  # 연말 공고의 1~2월 마감
        return date(y, mo, d).isoformat()
    except (ValueError, TypeError):
        return ""


def period_from(title: str, body: str, posted: str) -> tuple[str, str]:
    """(start, end). 못 찾으면 빈 문자열."""
    base = posted or date.today().isoformat()
    # 1) 본문에서 '신청/접수 …' 이 들어간 줄의 기간
    lines = (body or "").splitlines()
    for i, ln in enumerate(lines):
        if not KEY.search(ln):
            continue
        seg = " ".join(lines[i:i + 2])
        m = RANGE.search(seg)
        if m:
            s = _mk(m.group(1), m.group(2), m.group(3), base)
            e = _mk(m.group(4) or m.group(1), m.group(5), m.group(6), s or base)
            if s and e and s <= e:
                return s, e
    # 2) 제목의 기간 '(10.1.~10.14.)' 또는 마감 '(~10/26)', '(10/30 마감'
    m = RANGE.search(title or "")
    if m:
        s = _mk(m.group(1), m.group(2), m.group(3), base)
        e = _mk(m.group(4) or m.group(1), m.group(5), m.group(6), s or base)
        if s and e and s <= e:
            return s, e
    m = DUE.search(title or "")
    if m:
        g = m.groups()
        e = _mk(g[0], g[1], g[2], base) if g[1] else _mk(g[3], g[4], g[5], base)
        if e and (not posted or e >= posted):
            return "", e
    # 3) 본문 어디든 '~ 10. 14.' 같은 마감
    for ln in lines:
        if KEY.search(ln):
            m = DUE.search(ln)
            if m:
                g = m.groups()
                e = _mk(g[0], g[1], g[2], base) if g[1] else _mk(g[3], g[4], g[5], base)
                if e and (not posted or e >= posted):
                    return "", e
    return "", ""
