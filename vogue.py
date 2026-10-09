#!/usr/bin/env python3
"""Vogue Runway 수집기.

보그 런웨이 페이지에 내장된 JSON(window.__PRELOADED_STATE__)에서 쇼 정보와
룩 사진 URL을 추출해 data/ 폴더에 저장한다. 표준 라이브러리만 사용한다.

사용법:
  python3 vogue.py show   https://www.vogue.com/fashion-shows/spring-2026-ready-to-wear/chanel
  python3 vogue.py show   spring-2026-ready-to-wear/chanel --download
  python3 vogue.py season spring-2026-ready-to-wear            # 시즌의 쇼 목록만 저장
  python3 vogue.py season spring-2026-ready-to-wear --all      # 시즌의 모든 쇼를 가져옴
  python3 vogue.py designer chanel                             # 브랜드의 시즌 목록 저장
  python3 vogue.py designer chanel --all --limit 10            # 최근 10개 시즌 가져옴
  python3 vogue.py index                                       # data/index.json 재생성

옵션:
  --cookies cookies.txt   브라우저에서 내보낸 Netscape 형식 쿠키 파일(로그인 세션)
  --download              이미지를 data/images/ 에 저장(오프라인 보기용, w_1600)
  --force                 이미 저장된 쇼도 다시 가져옴
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import MozillaCookieJar
from pathlib import Path

BASE = "https://www.vogue.com"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SHOWS = DATA / "shows"
SEASONS = DATA / "seasons"
DESIGNERS = DATA / "designers"
IMAGES = DATA / "images"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
REQUEST_DELAY = 0.8  # 페이지 요청 사이 대기(초). 서버에 부담을 주지 않기 위함.
IMAGE_DELAY = 0.25   # 이미지(CDN) 다운로드 사이 대기(초).

_opener = None
_last_request = 0.0


def _ssl_context() -> ssl.SSLContext:
    """python.org 배포판 파이썬은 루트 인증서가 없을 수 있어 대안을 찾는다."""
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) > 0:
        return ctx
    for cafile in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if os.path.exists(cafile):
            return ssl.create_default_context(cafile=cafile)
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    log("경고: 루트 인증서를 찾지 못해 인증서 검증 없이 접속합니다.")
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _build_opener(*handlers) -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_context()), *handlers)


LOG_HOOK = None  # server.py 가 작업 로그를 받기 위해 설정하는 콜백


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    if LOG_HOOK:
        try:
            LOG_HOOK(msg)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- HTTP

def set_cookies(path: str | None) -> None:
    """Netscape cookies.txt 파일을 읽어 이후 요청에 사용한다."""
    global _opener
    if not path:
        _opener = _build_opener()
        return
    jar = MozillaCookieJar(path)
    jar.load(ignore_discard=True, ignore_expires=True)
    _opener = _build_opener(urllib.request.HTTPCookieProcessor(jar))
    log(f"쿠키 {len(jar)}개 로드: {path}")


def get(url: str, binary: bool = False, delay: float | None = None) -> bytes | str:
    global _opener, _last_request
    if _opener is None:
        _opener = _build_opener()
    wait = (REQUEST_DELAY if delay is None else delay) - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with _opener.open(req, timeout=60) as resp:
        body = resp.read()
    _last_request = time.time()
    return body if binary else body.decode("utf-8", errors="replace")


def preloaded_state(page_html: str) -> dict:
    """HTML에서 window.__PRELOADED_STATE__ JSON을 꺼낸다."""
    m = re.search(r"window\.__PRELOADED_STATE__\s*=\s*", page_html)
    if not m:
        raise ValueError("페이지에서 __PRELOADED_STATE__ 를 찾지 못했습니다 (URL이 맞는지, 로그인 쿠키가 필요한지 확인).")
    obj, _ = json.JSONDecoder().raw_decode(page_html, m.end())
    return obj


# ---------------------------------------------------------------- 유틸

def normalize_show_path(ref: str) -> str:
    """URL 또는 'season/brand' 를 '/fashion-shows/season/brand' 경로로 정규화."""
    ref = ref.strip()
    if ref.startswith("http"):
        ref = urllib.parse.urlparse(ref).path
    ref = ref.strip("/")
    if ref.startswith("fashion-shows/"):
        ref = ref[len("fashion-shows/"):]
    parts = [p for p in ref.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"쇼 경로 형식이 아닙니다: {ref} (예: spring-2026-ready-to-wear/chanel)")
    return f"/fashion-shows/{parts[0]}/{parts[1]}"


def show_key(path: str) -> str:
    season, brand = path.strip("/").split("/")[1:3]
    return f"{season}__{brand}"


def parse_photo(url: str) -> tuple[str, str] | None:
    """assets.vogue.com 사진 URL에서 (photo_id, filename) 추출."""
    m = re.match(r"https://assets\.vogue\.com/photos/([a-f0-9]+)/[^/]+/[^/]+/(.+)$", url)
    return (m.group(1), m.group(2)) if m else None


def photo_url(photo_id: str, filename: str, width: int | None = 1024) -> str:
    size = "pass" if width is None else f"w_{width},c_limit"
    return f"https://assets.vogue.com/photos/{photo_id}/master/{size}/{filename}"


def image_from(obj: dict | None) -> dict | None:
    """보그 이미지 객체 → {id, file, w, h}"""
    if not obj or not isinstance(obj, dict):
        return None
    sources = obj.get("sources") or {}
    src = sources.get("md") or sources.get("lg") or sources.get("sm") or {}
    url = src.get("url")
    if not url:
        return None
    parsed = parse_photo(url)
    if not parsed:
        return {"url": url}
    pid, fname = parsed
    out = {"id": pid, "file": fname}
    if src.get("width") and src.get("height"):
        out["w"], out["h"] = src["width"], src["height"]
    return out


_ALLOWED_TAGS = {"p", "em", "strong", "b", "i", "a", "h2", "h3", "h4", "br", "ul", "ol", "li",
                 "blockquote", "span", "div"}


def jsonml_to_html(node) -> str:
    """보그 리뷰 본문(JsonML 형식) → 안전한 HTML 문자열."""
    if node is None:
        return ""
    if isinstance(node, str):
        return html.escape(node)
    if isinstance(node, list) and node and isinstance(node[0], str):
        tag = node[0].lower()
        rest = node[1:]
        attrs = {}
        if rest and isinstance(rest[0], dict):
            attrs, rest = rest[0], rest[1:]
        inner = "".join(jsonml_to_html(c) for c in rest)
        if tag not in _ALLOWED_TAGS:
            return inner
        if tag == "br":
            return "<br>"
        attr_s = ""
        if tag == "a" and attrs.get("href"):
            href = attrs["href"]
            if href.startswith("/"):
                href = BASE + href
            attr_s = f' href="{html.escape(href)}" target="_blank" rel="noopener"'
        return f"<{tag}{attr_s}>{inner}</{tag}>"
    if isinstance(node, list):
        return "".join(jsonml_to_html(c) for c in node)
    return ""


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def season_title(text: str) -> str:
    """'spring-2026-ready-to-wear' / 'SPRING 2026 READY-TO-WEAR' → 'Spring 2026 Ready-to-Wear'"""
    t = text.strip().lower().replace("ready-to-wear", "ready_to_wear").replace("pre-fall", "pre_fall")
    words = [w for w in re.split(r"[\s-]+", t) if w]
    out = []
    for w in words:
        if w == "ready_to_wear":
            out.append("Ready-to-Wear")
        elif w == "pre_fall":
            out.append("Pre-Fall")
        else:
            out.append(w.capitalize())
    return " ".join(out)


# ---------------------------------------------------------------- 쇼

def fetch_show(ref: str, force: bool = False, download: bool = False) -> dict:
    path = normalize_show_path(ref)
    key = show_key(path)
    out_path = SHOWS / f"{key}.json"
    if out_path.exists() and not force:
        show = read_json(out_path)
        log(f"이미 있음: {key} ({sum(len(g['items']) for g in show['galleries'])}장)")
    else:
        log(f"가져오는 중: {BASE}{path}")
        state = preloaded_state(get(BASE + path))
        t = state.get("transformed", {})
        content = t.get("runwayShowContent") or {}
        gal_root = t.get("runwayShowGalleries") or {}
        access = t.get("access") or {}
        if access.get("contentRestricted"):
            log("주의: 이 페이지는 접근이 제한되어 있습니다. --cookies 로 로그인 쿠키를 넘겨 보세요.")

        season_slug, brand_slug = path.strip("/").split("/")[1:3]
        header = content.get("sectionHeader") or {}
        season_name = season_title(re.sub(r"<[^>]+>", "", header.get("subHed") or "") or season_slug)
        brand_name = re.sub(r"<[^>]+>", "", header.get("hed") or "") or content.get("brand") or brand_slug

        galleries = []
        for g in gal_root.get("galleries") or []:
            items = []
            for i, it in enumerate(g.get("items") or [], 1):
                img = image_from(it.get("image"))
                if not img:
                    continue
                items.append({"n": i, "caption": it.get("caption") or f"Look {i}", **img})
            if items:
                galleries.append({"id": g.get("id") or f"gallery-{len(galleries)}",
                                  "title": g.get("title") or "Gallery", "items": items})

        if not galleries:
            raise ValueError("룩 사진 목록이 비어 있습니다. 구독자 전용 페이지라면 --cookies 로 로그인 쿠키를 넘겨 보세요.")

        authors = []
        try:
            for a in (content.get("contributors") or {}).get("author", {}).get("items", []):
                if a.get("name"):
                    authors.append(a["name"])
        except AttributeError:
            pass

        cover = galleries[0]["items"][0]
        show = {
            "key": key,
            "url": BASE + path,
            "season": season_slug,
            "seasonName": season_name,
            "brand": brand_slug,
            "brandName": brand_name,
            "designers": content.get("designersDek") or "",
            "eventDate": content.get("eventDate") or "",
            "pubDate": content.get("pubDate") or "",
            "authors": authors,
            "reviewHtml": jsonml_to_html(content.get("review")),
            "cover": {k: cover[k] for k in ("id", "file") if k in cover},
            "galleries": galleries,
            "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        write_json(out_path, show)
        log(f"저장: {out_path.relative_to(ROOT)}  ({', '.join(f'{g['title']} {len(g['items'])}' for g in galleries)})")

    if download:
        download_images(show)
    build_index()
    return show


def download_images(show: dict, width: int = 1600) -> None:
    changed = False
    for g in show["galleries"]:
        folder = IMAGES / show["key"] / g["id"]
        folder.mkdir(parents=True, exist_ok=True)
        for it in g["items"]:
            if "id" not in it:
                continue
            target = folder / f"{it['n']:03d}.jpg"
            rel = str(target.relative_to(DATA)).replace(os.sep, "/")
            if target.exists() and target.stat().st_size > 0:
                if it.get("local") != rel:
                    it["local"] = rel; changed = True
                continue
            log(f"  다운로드 {show['key']} {g['title']} {it['n']}/{len(g['items'])}")
            data = get(photo_url(it["id"], it["file"], width), binary=True, delay=IMAGE_DELAY)
            target.write_bytes(data)
            it["local"] = rel
            changed = True
    if changed:
        write_json(SHOWS / f"{show['key']}.json", show)


# ---------------------------------------------------------------- 시즌 / 디자이너

def fetch_season(slug: str, fetch_all: bool = False, force: bool = False, download: bool = False,
                 limit: int | None = None, progress=None) -> dict:
    slug = slug.strip("/").split("/")[-1]
    log(f"시즌 목록: {BASE}/fashion-shows/{slug}")
    state = preloaded_state(get(f"{BASE}/fashion-shows/{slug}"))
    sc = state.get("transformed", {}).get("runwaySeasonContent") or {}
    shows = []
    for group in sc.get("allShows") or []:
        for link in group.get("links") or []:
            url = link.get("url") or ""
            if not url.startswith("/fashion-shows/"):
                continue
            parts = url.strip("/").split("/")
            if len(parts) < 3:
                continue
            shows.append({"name": link.get("text") or parts[2], "brand": parts[2],
                          "path": f"/fashion-shows/{parts[1]}/{parts[2]}"})
    covers = {}
    for c in sc.get("curatedShows") or []:
        img = image_from(c.get("image"))
        if img and c.get("url"):
            covers[c["url"].strip("/").split("/")[-1]] = img
    for s in shows:
        if s["brand"] in covers:
            s["cover"] = covers[s["brand"]]
    season = {"slug": slug, "name": sc.get("name") or season_title(slug), "shows": shows,
              "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
    write_json(SEASONS / f"{slug}.json", season)
    log(f"시즌 '{season['name']}' 쇼 {len(shows)}개")
    if fetch_all:
        targets = shows[:limit] if limit else shows
        for i, s in enumerate(targets, 1):
            if progress:
                progress(i, len(targets), s["name"])
            try:
                fetch_show(s["path"], force=force, download=download)
            except Exception as e:  # noqa: BLE001
                log(f"  실패 {s['path']}: {e}")
    build_index()
    return season


def fetch_designer(slug: str, fetch_all: bool = False, force: bool = False, download: bool = False,
                   limit: int | None = None, progress=None) -> dict:
    slug = slug.strip("/").split("/")[-1]
    log(f"디자이너 목록: {BASE}/fashion-shows/designer/{slug}")
    state = preloaded_state(get(f"{BASE}/fashion-shows/designer/{slug}"))
    dc = state.get("transformed", {}).get("runwayDesignerContent") or {}
    collections = []
    for c in dc.get("designerCollections") or []:
        url = c.get("url") or ""
        parts = url.strip("/").split("/")
        if len(parts) < 3:
            continue
        item = {"name": c.get("hed") or season_title(parts[1]), "season": parts[1],
                "path": f"/fashion-shows/{parts[1]}/{parts[2]}"}
        img = image_from(c.get("image"))
        if img:
            item["cover"] = img
        collections.append(item)
    designer = {"slug": slug, "name": dc.get("name") or slug, "bioHtml": jsonml_to_html(dc.get("body")),
                "collections": collections, "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
    write_json(DESIGNERS / f"{slug}.json", designer)
    log(f"디자이너 '{designer['name']}' 컬렉션 {len(collections)}개")
    if fetch_all:
        targets = collections[:limit] if limit else collections
        for i, c in enumerate(targets, 1):
            if progress:
                progress(i, len(targets), c["name"])
            try:
                fetch_show(c["path"], force=force, download=download)
            except Exception as e:  # noqa: BLE001
                log(f"  실패 {c['path']}: {e}")
    build_index()
    return designer


# ---------------------------------------------------------------- 인덱스

def build_index() -> dict:
    shows = []
    for p in sorted(SHOWS.glob("*.json")):
        try:
            s = read_json(p)
        except Exception:  # noqa: BLE001
            continue
        shows.append({
            "key": s["key"], "season": s["season"], "seasonName": s["seasonName"],
            "brand": s["brand"], "brandName": s["brandName"], "designers": s.get("designers", ""),
            "eventDate": s.get("eventDate", ""), "cover": s.get("cover"),
            "counts": {g["title"]: len(g["items"]) for g in s["galleries"]},
            "looks": sum(len(g["items"]) for g in s["galleries"]),
            "local": any(it.get("local") for g in s["galleries"] for it in g["items"]),
            "fetchedAt": s.get("fetchedAt", ""),
        })
    seasons = []
    for p in sorted(SEASONS.glob("*.json")):
        try:
            s = read_json(p)
            seasons.append({"slug": s["slug"], "name": s["name"], "count": len(s["shows"])})
        except Exception:  # noqa: BLE001
            pass
    designers = []
    for p in sorted(DESIGNERS.glob("*.json")):
        try:
            d = read_json(p)
            designers.append({"slug": d["slug"], "name": d["name"], "count": len(d["collections"])})
        except Exception:  # noqa: BLE001
            pass
    index = {"shows": shows, "seasons": seasons, "designers": designers,
             "builtAt": time.strftime("%Y-%m-%dT%H:%M:%S")}
    write_json(DATA / "index.json", index)
    return index


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["show", "season", "designer", "index"])
    ap.add_argument("target", nargs="?", help="쇼 URL, 시즌 슬러그, 디자이너 슬러그")
    ap.add_argument("--cookies", help="Netscape 형식 cookies.txt")
    ap.add_argument("--download", action="store_true", help="이미지를 로컬에 저장")
    ap.add_argument("--force", action="store_true", help="이미 있는 쇼도 다시 가져옴")
    ap.add_argument("--all", action="store_true", help="시즌/디자이너의 쇼를 전부 가져옴")
    ap.add_argument("--limit", type=int, help="--all 일 때 최대 개수")
    args = ap.parse_args(argv)

    cookies = args.cookies or (str(ROOT / "cookies.txt") if (ROOT / "cookies.txt").exists() else None)
    set_cookies(cookies)

    if args.command == "index":
        idx = build_index()
        log(f"index.json: 쇼 {len(idx['shows'])}개")
        return 0
    if not args.target:
        ap.error("target 이 필요합니다")
    if args.command == "show":
        fetch_show(args.target, force=args.force, download=args.download)
    elif args.command == "season":
        fetch_season(args.target, fetch_all=args.all, force=args.force, download=args.download, limit=args.limit)
    elif args.command == "designer":
        fetch_designer(args.target, fetch_all=args.all, force=args.force, download=args.download, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
