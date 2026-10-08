"""정부24 공공서비스(혜택) 정보 API — 행정안전부, data.go.kr 15113968.

시·군·구 장학회 등 지자체 장학 사업이 구조화되어 들어 있다. 무료 인증키가 필요하다:
data.go.kr 로그인 → '행정안전부_대한민국 공공서비스(혜택) 정보' 활용신청 → 일반 인증키(Decoding)를 GOV24_API_KEY 로 설정.
키가 없으면 건너뛴다.
"""
from __future__ import annotations

import os

import requests

from ..model import finalize, make_id

BASE = "https://api.odcloud.kr/api/gov24/v3"


def collect(online: bool = True):
    key = os.environ.get("GOV24_API_KEY")
    if not (online and key):
        return [], [{"source": "gov24", "label": "정부24 공공서비스 API", "ok": False, "count": 0, "mode": "키 미설정"}]
    out, page = [], 1
    while page < 40:
        r = requests.get(f"{BASE}/serviceList", params={"page": page, "perPage": 500, "serviceKey": key,
                                                         "cond[서비스명::LIKE]": "장학"}, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            break
        for s in data:
            out.append(finalize({
                "id": make_id("gov24", s.get("서비스ID")), "source": "gov24", "source_name": "정부24 공공서비스",
                "title": s.get("서비스명", ""), "org": s.get("소관기관명", ""), "org_type": "지자체" if s.get("소관기관유형") in ("지방자치단체", "시군구", "광역자치단체") else "정부",
                "category": "장학금", "kind": s.get("서비스분야", ""), "level": "대학생",
                "amount": s.get("지원내용", ""), "special": s.get("지원대상", ""), "selection": s.get("선정기준", ""),
                "documents": s.get("구비서류", "") if isinstance(s.get("구비서류"), str) else "",
                "summary": s.get("서비스목적요약", ""), "url": s.get("상세조회URL", ""),
                "apply_url": s.get("온라인신청사이트URL", ""), "end": "", "verified": True,
            }))
        page += 1
    return out, [{"source": "gov24", "label": "정부24 공공서비스 API", "ok": True, "count": len(out), "mode": "online"}]
