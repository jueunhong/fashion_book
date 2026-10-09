#!/usr/bin/env python3
"""Runway Book 로컬 서버.

  python3 server.py            # http://localhost:8765 를 열어 뷰어 표시
  python3 server.py --port 9000 --no-open

뷰어(viewer/index.html)를 서빙하고, 웹 UI에서 보그 URL을 넣으면 백그라운드에서
vogue.py 로 쇼를 가져오는 API 를 제공한다. 표준 라이브러리만 사용.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import queue
import shutil
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import vogue

ROOT = Path(__file__).resolve().parent
VIEWER = ROOT / "viewer"
DATA = vogue.DATA

# ---------------------------------------------------------------- 작업 큐 (한 번에 하나씩 순서대로 실행)

_jobs: dict[int, dict] = {}
_job_order: list[int] = []
_job_lock = threading.Lock()
_job_queue: "queue.Queue[int]" = queue.Queue()
_current_job = threading.local()
_job_seq = 0


def _job_log(msg: str) -> None:
    job_id = getattr(_current_job, "id", None)
    if job_id is None:
        return
    with _job_lock:
        job = _jobs.get(job_id)
        if job:
            job["log"].append(msg)
            job["log"] = job["log"][-200:]
            job["message"] = msg


vogue.LOG_HOOK = _job_log


def submit_job(kind: str, label: str, fn) -> dict:
    global _job_seq
    with _job_lock:
        _job_seq += 1
        job = {"id": _job_seq, "kind": kind, "label": label, "status": "queued", "progress": None,
               "message": "대기 중", "log": [], "createdAt": time.time(), "result": None}
        _jobs[job["id"]] = job
        _job_order.append(job["id"])
        if len(_job_order) > 100:
            old = _job_order.pop(0)
            _jobs.pop(old, None)
    job["_fn"] = fn
    _job_queue.put(job["id"])
    return public_job(job)


def public_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def _worker() -> None:
    while True:
        job_id = _job_queue.get()
        job = _jobs.get(job_id)
        if not job:
            continue
        _current_job.id = job_id
        job["status"] = "running"
        job["message"] = "시작"
        try:
            job["result"] = job["_fn"](job)
            job["status"] = "done"
            job["message"] = "완료"
        except Exception as e:  # noqa: BLE001
            job["status"] = "error"
            job["message"] = f"오류: {e}"
            job["log"].append(traceback.format_exc())
        finally:
            job["finishedAt"] = time.time()
            _current_job.id = None


threading.Thread(target=_worker, daemon=True, name="fetch-worker").start()


def _progress(job):
    def cb(i, n, name):
        job["progress"] = {"i": i, "n": n, "name": name}
    return cb


# ---------------------------------------------------------------- HTTP 핸들러

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 조용히
        pass

    # --- 응답 유틸
    def send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, cache: bool = False) -> None:
        if not path.is_file():
            self.send_json({"error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/json":
            ctype += "; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    # --- 라우팅
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(url.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if path == "/" or path == "/index.html":
                return self.send_file(VIEWER / "index.html")
            if path.startswith("/data/"):
                target = (DATA / path[len("/data/"):]).resolve()
                if DATA.resolve() not in target.parents:
                    return self.send_json({"error": "forbidden"}, 403)
                return self.send_file(target, cache=target.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
            if path == "/api/index":
                return self.send_json(vogue.build_index())
            if path.startswith("/api/show/"):
                key = path[len("/api/show/"):]
                return self.send_file(vogue.SHOWS / f"{key}.json")
            if path.startswith("/api/season/"):
                slug = path[len("/api/season/"):]
                return self.send_json(self.listing("season", slug, refresh="refresh" in qs))
            if path.startswith("/api/designer/"):
                slug = path[len("/api/designer/"):]
                return self.send_json(self.listing("designer", slug, refresh="refresh" in qs))
            if path == "/api/jobs":
                with _job_lock:
                    jobs = [public_job(_jobs[i]) for i in _job_order[-30:]]
                return self.send_json({"jobs": jobs, "busy": any(j["status"] in ("queued", "running") for j in jobs)})
            if path.startswith("/viewer/"):
                target = (VIEWER / path[len("/viewer/"):]).resolve()
                if VIEWER.resolve() not in target.parents:
                    return self.send_json({"error": "forbidden"}, 403)
                return self.send_file(target)
            self.send_json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.send_json({"error": str(e)}, 500)

    def do_POST(self):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        body = self.read_body()
        try:
            if path == "/api/fetch":
                ref = (body.get("ref") or "").strip()
                if not ref:
                    return self.send_json({"error": "ref 가 필요합니다"}, 400)
                show_path = vogue.normalize_show_path(ref)
                force, download = bool(body.get("force")), bool(body.get("download"))
                job = submit_job("show", show_path.replace("/fashion-shows/", ""),
                                 lambda job: vogue.fetch_show(show_path, force=force, download=download)["key"])
                return self.send_json({"job": job})
            if path in ("/api/fetch-season", "/api/fetch-designer"):
                slug = (body.get("slug") or "").strip().strip("/").split("/")[-1]
                if not slug:
                    return self.send_json({"error": "slug 가 필요합니다"}, 400)
                limit = int(body.get("limit") or 0) or None
                download = bool(body.get("download"))
                force = bool(body.get("force"))
                fn = vogue.fetch_season if path.endswith("season") else vogue.fetch_designer
                kind = "season" if path.endswith("season") else "designer"
                job = submit_job(kind, slug,
                                 lambda job: fn(slug, fetch_all=True, force=force, download=download,
                                                limit=limit, progress=_progress(job))["name"])
                return self.send_json({"job": job})
            if path == "/api/download":
                key = (body.get("key") or "").strip()
                p = vogue.SHOWS / f"{key}.json"
                if not p.is_file():
                    return self.send_json({"error": "없는 쇼"}, 404)

                def run(job):
                    show = vogue.read_json(p)
                    vogue.download_images(show)
                    vogue.build_index()
                    return key
                return self.send_json({"job": submit_job("download", key, run)})
            if path == "/api/delete":
                key = (body.get("key") or "").strip()
                p = vogue.SHOWS / f"{key}.json"
                if key and p.is_file():
                    p.unlink()
                    shutil.rmtree(vogue.IMAGES / key, ignore_errors=True)
                    vogue.build_index()
                    return self.send_json({"ok": True})
                return self.send_json({"error": "없는 쇼"}, 404)
            self.send_json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.send_json({"error": str(e)}, 500)

    def listing(self, kind: str, slug: str, refresh: bool) -> dict:
        folder = vogue.SEASONS if kind == "season" else vogue.DESIGNERS
        p = folder / f"{slug}.json"
        if refresh or not p.is_file():
            data = vogue.fetch_season(slug) if kind == "season" else vogue.fetch_designer(slug)
        else:
            data = vogue.read_json(p)
        items = data["shows"] if kind == "season" else data["collections"]
        for it in items:
            it["key"] = vogue.show_key(it["path"])
            it["fetched"] = (vogue.SHOWS / f"{it['key']}.json").is_file()
        return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="브라우저를 자동으로 열지 않음")
    ap.add_argument("--cookies", help="Netscape 형식 cookies.txt (기본: ./cookies.txt 가 있으면 사용)")
    args = ap.parse_args()

    cookies = args.cookies or (str(ROOT / "cookies.txt") if (ROOT / "cookies.txt").exists() else None)
    vogue.set_cookies(cookies)
    DATA.mkdir(exist_ok=True)
    vogue.build_index()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://localhost:{args.port}/"
    print(f"Runway Book: {url}  (종료: Ctrl+C)")
    if not args.no_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
