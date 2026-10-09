"""한국장학재단 학자금지원정보(대학생) 지난 기준일(2026-04-24) 목록에만 있던 장학금.

최신 공공데이터(9월 기준)에서 빠진 정기 장학금의 지난 회차 일정만 담는다.
기관명·상품명·모집기간·유형만 쓰고, 자격·금액 같은 설명은 옮기지 않는다(운영기관 공고로 연결).
같은 기관에 이름이 비슷한 최신 상품이 있으면 건너뛴다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..model import finalize, make_id
from . import kosaf
from .dreamspon import _homepages, _norm

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "kosaf_hist_202604.json"
REGION = {"보령화력": ("충남", "보령"), "당진화력": ("충남", "당진")}
SKIP = re.compile(r"외국인|교회|관악회|지곡|아경장학|배재장학")


def _toks(s: str) -> set[str]:
    s = re.sub(r"장학(금|생|사업)?|지원|사업|\s|[()·/]", " ", s)
    return {t for t in s.split() if len(t) >= 2}


def _current() -> dict[str, list[set[str]]]:
    cur: dict[str, list[set[str]]] = {}
    f = kosaf.SEED / kosaf.DATASETS["kosaf_univ"][2]
    if f.exists():
        for r in kosaf.decode(f.read_bytes()):
            cur.setdefault(_norm(kosaf.g(r, "운영기관명")), []).append(_toks(kosaf.g(r, "상품명")))
    return cur


def collect(online: bool = True):
    if not SEED.exists():
        return [], [{"source": "kosaf_hist", "ok": False, "count": 0, "mode": "none"}]
    rows = json.loads(SEED.read_text(encoding="utf-8"))["records"]
    cur, homes = _current(), _homepages()
    out = []
    for r in rows:
        org, title = r["org"], r["title"]
        if SKIP.search(org + " " + title) or (r.get("end") or "") < "2025-01-01":
            continue
        t = _toks(title)
        if any(t and (t <= c or c <= t or len(t & c) >= max(1, min(len(t), len(c)) - 0)) for c in cur.get(_norm(org), []) if c):
            continue  # 최신 데이터에 같은 장학이 이름만 바뀌어 있음
        local = r.get("kind") == "지역연고"
        reg = next((v for k, v in REGION.items() if k in org), ("", ""))
        out.append(finalize({
            "id": make_id("kosaf_hist", org, title), "source": "kosaf_hist",
            "source_name": "한국장학재단 학자금지원정보(대학생, 지난 회차)",
            "title": title if org[:4] in title else f"{org} {title}", "org": org,
            "org_type": "지자체" if re.search(r"(시|군|구|도)청$|시청|군청|구청|도청|인재|평생교육|장학회$", org) and local else "민간·기업·대학",
            "region": reg[0], "district": reg[1], "category": "장학금", "kind": r.get("kind", ""), "level": "대학생",
            "residence": "거주 지역 조건 있음 — 운영기관 공고 확인" if local else "",
            "summary": "지난 회차 모집 일정만 확인된 정기 장학금입니다. 올해 자격·금액은 운영기관 공고에서 확인하세요.",
            "url": homes.get(_norm(org), ""), "start": r["start"], "end": r["end"], "verified": False,
        }))
    return out, [{"source": "kosaf_hist", "label": "한국장학재단 지난 회차(2026-04 기준)", "ok": True, "count": len(out), "mode": "seed"}]
