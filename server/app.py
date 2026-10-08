"""장학알리미 서버: 웹앱 + API + 자동 갱신 스케줄러.

  uvicorn server.app:app --host 0.0.0.0 --port 8000

환경 변수
  REFRESH_HOURS   자동 수집 주기(시간, 기본 6)
  ADMIN_TOKEN     /api/refresh, /api/import/hyin 호출용 비밀 토큰
  GOV24_API_KEY   (선택) 정부24 공공서비스 API 키
"""
from __future__ import annotations

import hmac
import json
import os
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import refresh

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
HOURS = float(os.environ.get("REFRESH_HOURS", "6"))
TOKEN = os.environ.get("ADMIN_TOKEN", "")
_lock = threading.Lock()
_cache: dict = {"mtime": 0, "items": [], "meta": {}}

app = FastAPI(title="장학알리미 API", version="1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=[], allow_credentials=False)

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https:; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method == "POST" and int(request.headers.get("content-length") or 0) > 15_000_000:
        return JSONResponse({"detail": "요청이 너무 큽니다"}, status_code=413)
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    if request.url.scheme == "https":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp

HEAD = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https:; base-uri 'none'; form-action 'none'; object-src 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d5c6e"><link rel="icon" href="icon.svg"></head><body>"""


def run_refresh(online=True):
    if not _lock.acquire(blocking=False):
        return None
    try:
        return refresh.run(online=online)
    finally:
        _lock.release()


def load():
    p = WEB / "data" / "scholarships.json"
    if not p.exists():
        run_refresh(online=False)
    m = p.stat().st_mtime
    if m != _cache["mtime"]:
        _cache["items"] = json.loads(p.read_text())["items"]
        mp = WEB / "data" / "meta.json"
        _cache["meta"] = json.loads(mp.read_text()) if mp.exists() else {}
        _cache["mtime"] = m
    return _cache


@app.on_event("startup")
def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    sch = BackgroundScheduler(timezone="Asia/Seoul")
    sch.add_job(run_refresh, "interval", hours=HOURS, next_run_time=datetime.now(), id="refresh", max_instances=1, coalesce=True)
    sch.start()
    app.state.scheduler = sch


@app.get("/", response_class=HTMLResponse)
def index():
    return HEAD + (WEB / "index.html").read_text() + "</body></html>"


@app.get("/api/scholarships")
def scholarships(q: str = "", status: str = "", region: str = "", level: str = "", source: str = "",
                 limit: int = Query(100, le=5000), offset: int = 0):
    items = load()["items"]
    terms = q.lower().split()
    out = []
    for r in items:
        if status and r.get("status") not in status.split(","):
            continue
        if region and r.get("region") not in region.split(","):
            continue
        if level and r.get("level") not in level.split(","):
            continue
        if source and not r.get("source", "").startswith(source):
            continue
        if terms:
            blob = " ".join(str(r.get(k, "")) for k in ("title", "org", "region", "district", "amount", "special", "residence")).lower()
            if not all(t in blob for t in terms):
                continue
        out.append(r)
    return {"total": len(out), "items": out[offset: offset + limit]}


@app.get("/api/scholarships/{sid}")
def scholarship(sid: str):
    for r in load()["items"]:
        if r["id"] == sid:
            return r
    raise HTTPException(404, "장학금을 찾을 수 없습니다")


@app.get("/api/meta")
def meta():
    return load()["meta"]


@app.get("/api/calendar.ics")
def ics(ids: str = ""):
    """관심 장학금 마감일을 휴대폰 달력에 구독할 수 있는 ICS (ids=쉼표 구분, 비우면 모집중 전체)."""
    want = set(ids.split(",")) if ids else None
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//jangak-alimi//KO", "X-WR-CALNAME:장학 마감"]
    for r in load()["items"]:
        if (want and r["id"] not in want) or (not want and r.get("status") != "모집중") or not r.get("end"):
            continue
        d = r["end"].replace("-", "")
        lines += ["BEGIN:VEVENT", f"UID:{r['id']}@jangak", f"DTSTART;VALUE=DATE:{d}", f"SUMMARY:[마감] {r['title'][:60]}",
                  f"DESCRIPTION:{(r.get('org') or '')} {r.get('url') or ''}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return HTMLResponse("\r\n".join(lines), media_type="text/calendar; charset=utf-8")


def _auth(tok: str | None):
    # 토큰이 없거나 짧으면 관리 기능 자체를 끈다. 비교는 시간차 공격을 막는 상수 시간 비교.
    if len(TOKEN) < 24:
        raise HTTPException(403, "서버에 ADMIN_TOKEN(24자 이상)이 설정되지 않아 관리 기능이 꺼져 있습니다")
    if not tok or not hmac.compare_digest(tok.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "인증 실패")


@app.post("/api/refresh")
def manual_refresh(authorization: str | None = Header(None)):
    _auth(authorization)
    s = run_refresh(online=True)
    if s is None:
        return JSONResponse({"detail": "이미 수집 중입니다"}, status_code=409)
    return {k: v for k, v in s.items()}


@app.post("/api/import/hyin")
async def import_hyin(request: Request, authorization: str | None = Header(None)):
    """web/tools/hyin-sync.js 가 로그인한 브라우저에서 보낸 HY-in 장학캘린더 JSON 저장."""
    _auth(authorization)
    body = await request.json()
    recs = body.get("records") if isinstance(body, dict) else None
    if not isinstance(recs, list) or not 0 < len(recs) <= 3000:
        raise HTTPException(400, "records 형식이 올바르지 않습니다")
    keep = {"campus", "name", "start", "end", "jaewon", "year", "term", "cd", "seq"}
    dkeep = {"office", "text", "imgs", "docs", "files", "applyUrl", "period"}
    clean = []
    for r in recs:
        if not isinstance(r, dict) or not isinstance(r.get("name"), str):
            continue
        x = {k: r[k] for k in keep if k in r}
        d = r.get("detail") if isinstance(r.get("detail"), dict) else {}
        x["detail"] = {k: d[k] for k in dkeep if k in d}
        x["detail"]["files"] = list(x["detail"].get("files") or [])[:1]  # 학생 본인 제출 파일명 차단
        clean.append(x)
    body = {"collectedAt": str(body.get("collectedAt", ""))[:40], "records": clean}
    d = ROOT / "data" / "imports"
    d.mkdir(parents=True, exist_ok=True)
    name = d / f"hyin_{datetime.now():%Y%m%d_%H%M%S}.json"
    name.write_text(json.dumps(body, ensure_ascii=False))
    threading.Thread(target=run_refresh, kwargs={"online": False}, daemon=True).start()
    return {"saved": name.name, "count": len(body["records"])}


app.mount("/", StaticFiles(directory=WEB), name="web")
