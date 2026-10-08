import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
"""web/ 를 정적 사이트(site/)로 복사하고 index.html 에 문서 머리말을 붙인다 (GitHub Pages, Netlify 등)."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
shutil.rmtree(SITE, ignore_errors=True)
shutil.copytree(ROOT / "web", SITE)
from server.app import HEAD  # noqa: E402
(SITE / "index.html").write_text(HEAD + (ROOT / "web" / "index.html").read_text() + "</body></html>")
(SITE / ".nojekyll").write_text("")
print("site/ ready")
