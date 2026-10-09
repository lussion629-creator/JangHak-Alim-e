"""서강대학교 장학공지 (공개 게시판, 로그인 불필요). robots.txt 는 전체 허용.

목록은 홈페이지가 쓰는 공개 목록 API(BbsData/boardList, 장학공지 141), 본문은 공지 상세 화면(/ko/detail/{번호})에서 읽는다.
서강대 서버는 중간 인증서를 보내지 않아서, 서버 인증서에 적힌 발급기관 주소(AIA)에서 중간 인증서를 받아 검증한다.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import requests

from ..model import finalize, make_id, norm_date
from .period import period_from

SEED = Path(__file__).resolve().parents[2] / "data" / "seed" / "sogang.json"
BASE = "https://www.sogang.ac.kr"
API = BASE + "/api/api/v1/mainKo/BbsData/boardList?pageNum={page}&pageSize=20&bbsConfigFk=141"
VIEW = BASE + "/ko/detail/{pk}"
INTERMEDIATE = "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt"
UA = "Mozilla/5.0 (compatible; JangakAlimiBot/1.0; +https://github.com/lussion629-creator/JangHak-Alim-e)"
WORK = re.compile(r"근로|장학조교|학생\s*조교|도우미|튜터")
INSIDE = re.compile(r"^\s*\[(교내|발전기금|국가|근로|교내근로|등록|학자금)\]|서강|교내|근로장학|국가장학|국가근로")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR"})
    try:
        s.get(BASE + "/robots.txt", timeout=15)
    except requests.exceptions.SSLError:
        import certifi
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding
        der = requests.get(INTERMEDIATE, timeout=15).content
        pem = x509.load_der_x509_certificate(der).public_bytes(Encoding.PEM).decode()
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        f.write(Path(certifi.where()).read_text() + "\n" + pem)
        f.close()
        s.verify = f.name  # 중간 인증서는 신뢰 루트(certifi)로 다시 검증된다
    return s


def parse_detail(html: str) -> dict:
    from bs4 import BeautifulSoup
    from ..model import html_block_text
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    body = soup.select_one(".tiptap")
    if body:
        out["imgs"] = [BASE + i["src"] if i.get("src", "").startswith("/") else i.get("src", "") for i in body.select("img")][:6]
        for t in body(["script", "style"]):
            t.decompose()
        out["text"] = html_block_text(body)[:3000]
    return out


def fetch(known: dict) -> list[dict]:
    from .boards import allowed
    if not allowed(BASE + "/ko/scholarship-notice"):
        raise PermissionError("robots")
    s = _session()
    rows, seen = [], set()
    for p in range(1, 5):
        lst = ((s.get(API.format(page=p), timeout=25).json().get("data") or {}).get("list")) or []
        if not lst:
            break
        for x in lst:
            pk = str(x.get("pkId"))
            if pk in seen:
                continue
            seen.add(pk)
            d = x.get("regDate") or ""
            files = [re.sub(r"^.*[?&]sg=", "", f or "")[:80] for f in (x.get(f"fileValue{i}") for i in range(1, 6)) if f]
            rows.append({"pk": pk, "title": (x.get("title") or "").strip(), "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else "",
                         "dept": x.get("displayName") or x.get("userName") or "", "files": files})
    n = 0
    for r in rows:
        if r["pk"] in known:
            r["detail"] = known[r["pk"]]
        elif n < 30:
            try:
                r["detail"] = parse_detail(s.get(VIEW.format(pk=r["pk"]), timeout=25).text)
            except Exception:  # noqa: BLE001
                pass
            n += 1
    return rows


def collect(online: bool = True):
    from .boards import _org_from_title
    old = json.loads(SEED.read_text())["records"] if SEED.exists() else []
    known = {r["pk"]: r["detail"] for r in old if r.get("detail")}
    rows, mode = None, "seed"
    if online:
        try:
            rows = fetch(known)
            if rows:
                SEED.write_text(json.dumps({"records": rows}, ensure_ascii=False))
                mode = "online"
            else:
                rows = None
        except Exception:  # noqa: BLE001
            rows = None
    if rows is None:
        rows = old
    out = []
    for r in rows:
        t = r["title"]
        det = r.get("detail") or {}
        body = det.get("text", "")
        start, end = period_from(t, body, r.get("date", ""))
        work = bool(WORK.search(t))
        ext = _org_from_title(re.sub(r"^\s*\[[^\]]{1,8}\]\s*", "", t), "서강대학교", body)
        inside = not t.lstrip().startswith("[교외]") and (ext == "서강대학교" or bool(INSIDE.search(t)))
        out.append(finalize({
            "id": make_id("sogang", r["pk"]), "source": "sogang", "source_name": "서강대 장학공지",
            "title": t, "org": "서강대학교" if inside else ext, "org_type": "대학(교내)" if inside else "민간·기업·대학",
            "category": "근로장학" if work else ("학자금" if "대출" in t else "장학금"), "kind": "교내근로" if work else "공고",
            "level": "대학원생" if re.search(r"대학원생|석사|박사", t) and not re.search(r"학부", t) else "대학생",
            "school_types": ["4년제(5~6년제포함)"] if inside else [], "region": "서울" if inside else "", "district": "마포구" if inside else "",
            "url": VIEW.format(pk=r["pk"]), "posted": norm_date(r.get("date")), "start": start, "end": end,
            "summary": body, "files": r.get("files", []), "images": det.get("imgs", []),
            "selection": ("담당: " + r["dept"]) if r.get("dept") else "", "verified": True,
        }))
    return out, [{"source": "sogang", "label": "서강대 장학공지", "ok": bool(out), "count": len(out), "mode": mode}]
