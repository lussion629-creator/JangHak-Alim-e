"""배포 전 보안 점검. 하나라도 걸리면 종료 코드 1 → GitHub Actions 가 커밋·배포를 멈춘다.

1) 비밀 값: API 키·토큰·개인키 패턴, 비밀 파일(.env, *.jks, 서비스 계정 JSON)이 git 추적 대상인지
2) 개인정보: 주민등록번호 패턴, PII_DENYLIST(이름·학번 등, GitHub Secret) 문자열, HY-in 학생 제출 파일명 흔적
3) 데이터 안전: javascript:/data: 등 http(s) 가 아닌 링크
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_RX = {
    "OpenAI/Anthropic 키": r"\bsk-(ant-)?[A-Za-z0-9_-]{20,}",
    "GitHub 토큰": r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}",
    "AWS 키": r"\bAKIA[0-9A-Z]{16}\b",
    "Google API 키": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "Slack 토큰": r"\bxox[abpr]-[A-Za-z0-9-]{10,}",
    "개인키": r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----",
    "서비스 계정": r'"type"\s*:\s*"service_account"',
    "공공데이터 인증키": r"serviceKey=[A-Za-z0-9%+/=]{30,}",
}
BAD_FILES = re.compile(r"(^|/)(\.env(\..+)?|.*\.(jks|keystore|p12|pem|key)|google-services\.json|.*service-account.*\.json|extractor-secrets\.json)$")
RRN = re.compile(r"\b\d{6}-[1-4]\d{6}\b")
SKIP_DIRS = {".git", "node_modules", ".venv", "site", "__pycache__"}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        return [ROOT / f for f in out]
    except Exception:  # noqa: BLE001 — git 없는 환경
        return [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]


def main() -> int:
    problems = []
    deny = [w.strip() for w in os.environ.get("PII_DENYLIST", "").split(",") if len(w.strip()) >= 2]
    files = tracked_files() + [ROOT / "web" / "data" / "scholarships.json"]
    for f in files:
        rel = str(f.relative_to(ROOT))
        if rel.endswith(".example"):
            continue
        if BAD_FILES.search(rel):
            problems.append(f"비밀 파일이 저장소에 있음: {rel}")
            continue
        if not f.exists() or f.stat().st_size > 40_000_000 or f.suffix in {".png", ".jpg", ".db", ".gz", ".zip", ".apk", ".jar"}:
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for name, rx in SECRET_RX.items():
            if re.search(rx, text):
                problems.append(f"{name} 의심 문자열: {rel}")
        if RRN.search(text):
            problems.append(f"주민등록번호 형식 숫자: {rel}")
        for w in deny:
            if w in text:
                problems.append(f"개인 식별 문자열(PII_DENYLIST) 포함: {rel}")
    data = ROOT / "web" / "data" / "scholarships.json"
    if data.exists():
        for r in json.loads(data.read_text())["items"]:
            for k in ("url", "apply_url"):
                if r.get(k) and not re.match(r"^https?://", r[k]):
                    problems.append(f"안전하지 않은 링크({k}): {r['title'][:30]}")
            if r.get("source") == "hyin" and len(r.get("files") or []) > 1:
                problems.append(f"HY-in 학생 제출 파일명이 섞였을 수 있음: {r['title'][:30]}")
    if problems:
        print("보안 점검 실패:")
        for p in sorted(set(problems)):
            print("  -", p)
        return 1
    print(f"보안 점검 통과 ({len(files)}개 파일, 개인 식별 문자열 {len(deny)}개 확인)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
