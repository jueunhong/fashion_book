#!/usr/bin/env python3
"""내 컴퓨터의 data/ 를 Supabase 로 올린다 (로컬 → 클라우드 동기화).

  python3 sync_to_supabase.py            # shows / seasons / designers 업서트
  python3 sync_to_supabase.py --pull     # 클라우드 → 로컬 (data/shows 에 없는 쇼 내려받기)

.env.local 의 SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 를 사용한다.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import vogue

ROOT = Path(__file__).resolve().parent


def load_env() -> dict:
    env = {}
    p = ROOT / ".env.local"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("SUPABASE_")})
    return env


_OPENER = vogue._build_opener()  # macOS 파이썬의 루트 인증서 문제를 vogue.py 와 같은 방식으로 처리
ENV = load_env()
URL = ENV.get("SUPABASE_URL")
KEY = ENV.get("SUPABASE_SERVICE_ROLE_KEY")
if not URL or not KEY:
    sys.exit(".env.local 에 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 가 필요합니다")


def rest(path: str, method: str = "GET", body=None, prefer: str = "return=minimal"):
    req = urllib.request.Request(f"{URL}/rest/v1/{path}", method=method,
                                 data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                                 headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json", "Prefer": prefer})
    with _OPENER.open(req, timeout=120) as r:
        t = r.read().decode()
    return json.loads(t) if t else None


def show_row(s: dict) -> dict:
    galleries = [{"id": g["id"], "title": g["title"],
                  "items": [{k: v for k, v in it.items() if k != "local"} for it in g["items"]]} for g in s["galleries"]]
    return {
        "key": s["key"], "url": s.get("url"), "season": s["season"], "season_name": s["seasonName"],
        "brand": s["brand"], "brand_name": s["brandName"], "designers": s.get("designers", ""),
        "event_date": s.get("eventDate", ""), "pub_date": s.get("pubDate", ""), "authors": s.get("authors", []),
        "review_html": s.get("reviewHtml", ""), "cover": s.get("cover"), "galleries": galleries,
        "looks": sum(len(g["items"]) for g in galleries), "counts": {g["title"]: len(g["items"]) for g in galleries},
    }


def push() -> None:
    existing = {r["key"] for r in rest("shows?select=key&limit=10000")}
    rows = []
    for p in sorted(vogue.SHOWS.glob("*.json")):
        s = vogue.read_json(p)
        if s["key"] in existing:
            continue
        rows.append(show_row(s))
    print(f"쇼: 클라우드에 {len(existing)}개 있음, 새로 올릴 것 {len(rows)}개")
    for i in range(0, len(rows), 25):
        rest("shows", "POST", rows[i:i + 25], prefer="resolution=merge-duplicates,return=minimal")
        print(f"  {min(i + 25, len(rows))}/{len(rows)}")
    for folder, table in ((vogue.SEASONS, "seasons"), (vogue.DESIGNERS, "designers")):
        for p in sorted(folder.glob("*.json")):
            d = vogue.read_json(p)
            if table == "seasons":
                row = {"slug": d["slug"], "name": d["name"], "shows": d["shows"]}
            else:
                row = {"slug": d["slug"], "name": d["name"], "bio_html": d.get("bioHtml", ""), "collections": d["collections"]}
            rest(table, "POST", row, prefer="resolution=merge-duplicates,return=minimal")
            print(f"{table}: {d['slug']}")


def pull() -> None:
    have = {p.stem for p in vogue.SHOWS.glob("*.json")}
    keys = [r["key"] for r in rest("shows?select=key&limit=10000") if r["key"] not in have]
    print(f"내려받을 쇼 {len(keys)}개")
    for k in keys:
        r = rest(f"shows?key=eq.{k}&select=*")[0]
        show = {"key": r["key"], "url": r["url"], "season": r["season"], "seasonName": r["season_name"],
                "brand": r["brand"], "brandName": r["brand_name"], "designers": r["designers"],
                "eventDate": r["event_date"], "pubDate": r["pub_date"], "authors": r["authors"],
                "reviewHtml": r["review_html"], "cover": r["cover"], "galleries": r["galleries"],
                "fetchedAt": r["fetched_at"]}
        vogue.write_json(vogue.SHOWS / f"{k}.json", show)
        print("  ", k)
    vogue.build_index()


if __name__ == "__main__":
    pull() if "--pull" in sys.argv else push()
