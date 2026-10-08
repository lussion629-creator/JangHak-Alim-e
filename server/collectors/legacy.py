"""기존 '한양&한여 IVF 장학알리미'(ChatGPT/Codex 버전)가 33개 기관에서 수집해 둔 공고 + 관리자 등록 자료."""
from __future__ import annotations

import json
from pathlib import Path

from ..model import extract_target, finalize, make_id, norm_date

SEED = Path(__file__).resolve().parents[2] / "data" / "seed"


def _rec(x: dict, src: str) -> dict:
    facts = x.get("facts") or {}
    return finalize({
        "id": make_id("legacy", x["id"]),
        "source": "legacy",
        "source_name": "기존 장학알리미 수집본 (" + (x.get("checkedAt") or "")[:10] + ")",
        "title": x["title"],
        "org": (x.get("institution") or "").split("·")[0].strip(),
        "org_type": "민간·기업·대학",
        "category": "장학금",
        "kind": x.get("kind") if x.get("kind") not in (None, "확인 필요") else "공고",
        "level": "대학생",
        "amount": x.get("amount") or "",
        "summary": (x.get("eligibility") or "") + ("\n" if x.get("eligibility") else "") + (x.get("summary") or ""),
        "documents": "\n".join("○ " + d for d in (x.get("documents") or []) if isinstance(d, str)),
        "url": x.get("url") or "",
        "start": norm_date(x.get("start")),
        "end": norm_date(x.get("end")),
        "posted": norm_date(x.get("foundAt")),
        "images": x.get("noticeImages") or [],
        "files": [a.get("name") for a in (x.get("attachments") or []) if isinstance(a, dict)],
        "links": [s for s in (x.get("sources") or []) if isinstance(s, dict)][:3],
        "region": x.get("region") if x.get("region") not in (None, "", "확인 필요") else "",
        "residence": facts.get("지역 조건", ""),
        "target": x.get("eligibility") or extract_target(x.get("summary") or ""),
        "verified": bool(x.get("verified")),
    })


def collect(online: bool = True):
    out = []
    p = SEED / "institution-production-results.json"
    if p.exists():
        for x in json.loads(p.read_text())["records"]:
            if (x.get("year") or "2026") >= "2025" and not x.get("cancelled"):
                out.append(_rec(x, "institution"))
    p = SEED / "bootstrap.json"
    if p.exists():
        for x in json.loads(p.read_text())["records"]:
            if not x.get("cancelled"):
                out.append(_rec(x, "bootstrap"))
    return out, [{"source": "legacy", "label": "기존 앱 수집본", "ok": True, "count": len(out), "mode": "seed"}]
