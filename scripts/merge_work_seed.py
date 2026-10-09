"""브라우저에서 모은 한양대 근로 모집 글을 data/seed/hanyang_work.json 에 더한다.

  python scripts/merge_work_seed.py --known          # 이미 가진 글 번호(JSON 배열)를 출력
  python scripts/merge_work_seed.py new.json         # 새 글을 더하고 몇 건 늘었는지 출력
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "hanyang_work.json"
FIELDS = {"id", "title", "campus", "dept", "date", "cat", "detail"}


def main():
    data = json.loads(SEED.read_text()) if SEED.exists() else {"records": []}
    recs = data["records"]
    if sys.argv[1:] == ["--known"]:
        print(json.dumps([r["id"] for r in recs]))
        return
    new = json.loads(Path(sys.argv[1]).read_text())
    if isinstance(new, str):
        new = json.loads(new)
    have = {r["id"] for r in recs}
    added = 0
    for r in new:
        if not isinstance(r, dict) or not re.fullmatch(r"\d{4,8}", str(r.get("id", ""))) or r["id"] in have:
            continue
        r = {k: v for k, v in r.items() if k in FIELDS}
        r["title"] = str(r.get("title", ""))[:200]
        if isinstance(r.get("detail"), dict):
            r["detail"] = {k: (str(v)[:1500] if k == "text" else v) for k, v in r["detail"].items() if k in ("start", "end", "text", "files")}
        recs.insert(0, r)
        have.add(r["id"])
        added += 1
    recs.sort(key=lambda r: r.get("date", ""), reverse=True)
    data["records"] = recs[:200]
    data["collectedAt"] = date.today().isoformat()
    SEED.write_text(json.dumps(data, ensure_ascii=False))
    print(added)


if __name__ == "__main__":
    main()
