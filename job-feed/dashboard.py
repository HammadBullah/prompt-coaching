#!/usr/bin/env python3
"""
Tiny stdlib HTTP server for the job feed dashboard.

Serves:
  /          -> index.html (reads live data via /api/jobs)
  /api/jobs  -> {"jobs": [...], "meta": {...}}

Run:  python3 job-feed/dashboard.py [port]   (default 8000, binds 0.0.0.0)
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
INDEX = os.path.join(ROOT, "index.html")


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep logs quiet
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(INDEX, "r", encoding="utf-8") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/api/jobs":
            payload = {
                "jobs": read_json(os.path.join(DATA, "jobs.json"), []),
                "meta": read_json(os.path.join(DATA, "meta.json"), {}),
            }
            self._send(200, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Job feed dashboard on http://0.0.0.0:{port}", flush=True)
    srv.serve_forever()
