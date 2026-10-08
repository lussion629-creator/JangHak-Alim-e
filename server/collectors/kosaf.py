"""한국장학재단 학자금지원정보 (공공데이터포털, 이용허락 제한 없음, 월간 갱신).

data.go.kr 파일데이터는 로그인 없이 받을 수 있다. 페이지 → 다운로드 정보 요청 → 파일 순서로 받는다.
네트워크가 막혀 있으면 data/seed 의 마지막 사본을 쓴다.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path

import requests

from ..model import clean, finalize, make_id, norm_date, split_tokens, SCHOOL_TOKENS, GRADE_TOKENS, MAJOR_TOKENS

log = logging.getLogger(__name__)
SEED = Path(__file__).resolve().parents[2] / "data" / "seed"
UA = {"User-Agent": "Mozilla/5.0 (scholarship-aggregator; +https://www.data.go.kr)"}

DATASETS = {
    "kosaf_univ": ("15028252", "대학생", "kosaf_univ_20260910.csv"),
    "kosaf_high": ("15116988", "고등학생", "kosaf_highschool.csv"),
    "kosaf_abroad": ("15145372", "해외유학", "kosaf_abroad.csv"),
    "kosaf_creditbank": ("15145370", "학점은행제", "kosaf_creditbank.csv"),
}

ORG_TYPE = {"지자체(출자출연기관)": "지자체", "기타": "민간·기업·대학", "한국장학재단": "한국장학재단", "공공기관": "공공기관", "정부": "정부"}


def download(pk: str, timeout=60) -> bytes:
    s = requests.Session()
    s.headers.update(UA)
    page = s.get(f"https://www.data.go.kr/data/{pk}/fileData.do", timeout=timeout).text
    m = re.search(r"fn_fileDataDown\('(\d+)',\s*'([^']+)'", page)
    if not m:
        raise RuntimeError("download button not found")
    info = s.post("https://www.data.go.kr/tcs/dss/selectFileDataDownload.do", data={
        "publicDataDetailPk": m.group(2), "publicDataPk": pk, "atchFileId": "", "fileDetailSn": "1", "publicDataTyCode": "PR0051",
    }, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=timeout).json()
    if not info.get("status"):
        raise RuntimeError("download info refused")
    name = info["dataSetFileDetailInfo"]["dataNm"]
    r = s.get("https://www.data.go.kr/cmm/cmm/fileDownload.do", params={
        "atchFileId": info["atchFileId"], "fileDetailSn": info["fileDetailSn"], "dataNm": name}, timeout=timeout)
    r.raise_for_status()
    return r.content


def decode(raw: bytes) -> list[dict]:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]


def g(r, *keys):
    for k in keys:
        if k in r and r[k]:
            return r[k]
    return ""


def _core(org: str) -> str:
    return re.sub(r"^\s*(\(재\)|\(사\)|재단법인|사단법인)\s*", "", org)[:4]


def to_record(key: str, r: dict) -> dict:
    level = DATASETS[key][1]
    org = g(r, "운영기관명", "해외유학설계지원기관명", "학점은행제지원기관명")
    title = g(r, "상품명", "해외유학설계상품명", "학점은행설계명칭")
    amount = clean(g(r, "지원내역 상세내용", "최대지원내용"))
    rec = {
        "id": make_id(key, org, title),
        "source": key,
        "source_name": f"한국장학재단 학자금지원정보({level})",
        "title": (title if (not org or _core(org) in title) else f"{org} {title}") if title else org,
        "org": org,
        "org_type": ORG_TYPE.get(g(r, "운영기관구분"), g(r, "운영기관구분") or "기타"),
        "category": g(r, "상품구분", "학점은행설계상품구분명") or "장학금",
        "kind": g(r, "학자금유형구분"),
        "level": level,
        "school_types": split_tokens(g(r, "대학구분", "학교구분", "해외유학학교구분"), SCHOOL_TOKENS + ["고등학교", "특성화고", "일반고"]),
        "grades": split_tokens(g(r, "학년구분", "해외유학학년구분"), GRADE_TOKENS),
        "majors": split_tokens(g(r, "학과구분", "해외유학설계학과구분", "학점은행설계학과구분"), MAJOR_TOKENS),
        "amount": amount,
        "income": clean(g(r, "소득기준 상세내용", "소득제한내용")),
        "gpa": clean(g(r, "성적기준 상세내용", "성적기준내용")),
        "special": clean(g(r, "특정자격 상세내용", "특정자격내용")),
        "residence": clean(g(r, "지역거주여부 상세내용")),
        "selection": clean(g(r, "선발방법 상세내용", "선발방법내용")),
        "quota": clean(g(r, "선발인원 상세내용")),
        "restriction": clean(g(r, "자격제한 상세내용", "자격제한내용")),
        "recommend": clean(g(r, "추천필요여부 상세내용", "추천필요내용")),
        "documents": clean(g(r, "제출서류 상세내용")),
        "url": g(r, "홈페이지 주소", "홈페이지주소"),
        "start": norm_date(g(r, "모집시작일")),
        "end": norm_date(g(r, "모집종료일")),
        "verified": True,
    }
    if level == "해외유학":
        rec["summary"] = clean(g(r, "언어기준내용"))
    return finalize(rec)


def collect(online: bool = True):
    """(records, report) 반환."""
    out, report = [], []
    for key, (pk, label, seed_name) in DATASETS.items():
        raw, mode = None, "seed"
        if online:
            try:
                raw = download(pk)
                (SEED / seed_name).write_bytes(raw)
                mode = "online"
            except Exception as e:  # noqa: BLE001
                log.warning("kosaf %s online failed: %s", key, e)
        if raw is None and (SEED / seed_name).exists():
            raw = (SEED / seed_name).read_bytes()
        if raw is None:
            report.append({"source": key, "ok": False, "count": 0, "mode": "none"})
            continue
        rows = decode(raw)
        recs = [to_record(key, r) for r in rows if g(r, "상품명", "해외유학설계상품명", "학점은행설계명칭")]
        out.extend(recs)
        report.append({"source": key, "label": f"한국장학재단 {label}", "ok": True, "count": len(recs), "mode": mode})
    return out, report
