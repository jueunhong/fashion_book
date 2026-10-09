#!/usr/bin/env python3
"""배포용 정적 사이트 생성: dist/ 에 뷰어와 data/*.json 을 복사한다.

  python3 export.py            # dist/ 생성
  npx vercel --prod            # 프로젝트 루트에서 실행하면 dist/ 가 배포됨 (vercel.json 참고)

이미지는 포함하지 않고(용량), 배포본은 보그 CDN 에서 바로 불러온다.
"""
import json
import shutil
import sys
from pathlib import Path

import vogue

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


def strip_local(show: dict) -> dict:
    for g in show.get("galleries", []):
        for it in g.get("items", []):
            it.pop("local", None)
    return show


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "data").mkdir(parents=True)
    html = (ROOT / "viewer" / "index.html").read_text(encoding="utf-8")
    env = {}
    envp = ROOT / ".env.local"
    if envp.exists():
        for line in envp.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    import os
    url = os.environ.get("SUPABASE_URL") or env.get("SUPABASE_URL")
    anon = os.environ.get("SUPABASE_ANON_KEY") or env.get("SUPABASE_ANON_KEY")
    if url and anon:
        cfg = json.dumps({"url": url, "anon": anon})
        html = html.replace("window.RB_CLOUD = null;", f"window.RB_CLOUD = {cfg};", 1)
        print(f"클라우드 모드: {url}")
    else:
        print("클라우드 설정 없음(.env.local): 읽기 전용 정적 모드로 내보냄")
    (DIST / "index.html").write_text(html, encoding="utf-8")
    # 로고 등 뷰어 정적 파일 (index.html 제외) → dist/viewer/
    (DIST / "viewer").mkdir(exist_ok=True)
    for p in (ROOT / "viewer").iterdir():
        if p.is_file() and p.name != "index.html" and not p.name.startswith("."):
            shutil.copy(p, DIST / "viewer" / p.name)

    index = vogue.build_index()
    for s in index["shows"]:
        s["local"] = False
    (DIST / "data" / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    n = 0
    for sub in ("shows", "seasons", "designers"):
        src = vogue.DATA / sub
        dst = DIST / "data" / sub
        dst.mkdir()
        for p in sorted(src.glob("*.json")) if src.exists() else []:
            obj = vogue.read_json(p)
            if sub == "shows":
                obj = strip_local(obj)
            (dst / p.name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
            n += 1
    size = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"dist/ 생성: 쇼 {len(index['shows'])}개, JSON {n}개, 총 {size/1024/1024:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
