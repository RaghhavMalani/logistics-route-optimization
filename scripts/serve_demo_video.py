"""Loopback-only final-demo player with byte ranges for browser video seeking."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote
import argparse
import mimetypes
import re

ROOT = Path(__file__).resolve().parents[1] / "work/current-source-demo/video/final"
FILES = {"player.html", "portwatch-demonstration.mp4", "portwatch-demonstration.webm",
         "captions.vtt", "poster.png", "chapters.txt", "manifest.json", "edit-plan.json"}


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.respond(head=True)

    def do_GET(self):
        self.respond()

    def respond(self, head=False):
        name = unquote(urlsplit(self.path).path).removeprefix("/") or "player.html"
        if name not in FILES or not (ROOT / name).is_file():
            self.send_error(404)
            return
        path = ROOT / name
        size = path.stat().st_size
        start, end, partial = 0, size - 1, False
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            if not match or not any(match.groups()):
                self.send_error(416)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                start = max(0, size - int(last))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            partial = True
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "text/vtt" if name.endswith(".vtt") else
                         (mimetypes.guess_type(name)[0] or "application/octet-stream"))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if head:
            return
        try:
            with path.open("rb") as source:
                source.seek(start)
                remaining = end - start + 1
                while remaining:
                    block = source.read(min(65536, remaining))
                    if not block:
                        break
                    self.wfile.write(block)
                    remaining -= len(block)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Browsers cancel old ranges during a seek.


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8921)
    args = parser.parse_args()
    print(f"Local player: http://127.0.0.1:{args.port}/player.html", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
