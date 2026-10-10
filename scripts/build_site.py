import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
"""web/ 를 정적 사이트(site/)로 만든다 (GitHub Pages).

- index.html 안의 스크립트는 app.js 로 빼고, 보안 정책(CSP)에서 인라인 스크립트를 막는다
- 휴대폰 앱 전용 도구(tools/)는 웹에 올리지 않는다 (앱 빌드가 따로 넣는다)
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
REMOTE = "https://lussion629-creator.github.io"
shutil.rmtree(SITE, ignore_errors=True)
shutil.copytree(ROOT / "web", SITE, ignore=shutil.ignore_patterns("tools"))
from server.app import HEAD  # noqa: E402

html = (ROOT / "web" / "index.html").read_text()
scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
assert len(scripts) == 1, "index.html 에는 스크립트 블록이 하나여야 합니다"
(SITE / "app.js").write_text(scripts[0])
html = html.replace("<script>" + scripts[0] + "</script>", '<script src="app.js"></script>')
assert "<script>" not in html and not re.search(r"\son[a-z]+=", html), "인라인 스크립트·이벤트 속성이 남아 있습니다"
csp = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' " + REMOTE + "; "
       "manifest-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'")
head = re.sub(r'content="default-src[^"]*"', 'content="' + csp + '"', HEAD)
assert csp in head
(SITE / "index.html").write_text(head + html + "</body></html>")
(SITE / ".nojekyll").write_text("")
print("site/ ready")
