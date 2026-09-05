from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_SEED, WEB_ROOT
from .engine import LabRuntime


class LabHTTPServer(ThreadingHTTPServer):
    runtime: LabRuntime
    web_root: Path


class Handler(BaseHTTPRequestHandler):
    server: LabHTTPServer

    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, relative: str) -> None:
        relative = relative or "index.html"
        target = (self.server.web_root / relative).resolve()
        root = self.server.web_root.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._json(self.server.runtime.snapshot())
            return
        self._static(path.lstrip("/") or "index.html")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/control":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 16_384:
                raise ValueError("invalid body size")
            payload = json.loads(self.rfile.read(size) or b"{}")
            command = payload.get("command")
            if not isinstance(command, str):
                raise ValueError("command is required")
            result = self.server.runtime.control(command, payload.get("value"))
            self._json(result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"ok": False, "error": str(exc)}, status=400)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mini Metro Lab 本地观战服务")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.port <= 0 or args.port > 65535:
        raise SystemExit("端口必须在 1..65535")
    if not WEB_ROOT.is_dir():
        raise SystemExit(f"找不到前端目录：{WEB_ROOT}")

    runtime = LabRuntime(seed=args.seed)
    runtime.start()
    server = LabHTTPServer((args.host, args.port), Handler)
    server.runtime = runtime
    server.web_root = WEB_ROOT

    url = f"http://{args.host}:{args.port}/"
    print(f"🚇 Mini Metro Lab 已启动：{url}")
    print("按 Ctrl+C 关闭。")
    if not args.no_open:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        runtime.stop()
        print("已关闭 Mini Metro Lab。")


if __name__ == "__main__":
    main()
