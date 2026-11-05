"""Authenticated identity publisher; bind localhost and expose with Tailscale Serve."""

import hmac
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from trustnet.gate.identity import export_local


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != "/identities":
            self.send_error(404)
            return
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, "Bearer " + os.environ["TN_IDENTITY_TOKEN"]):
            self.send_error(401)
            return
        try:
            raw = export_local(Path("data/published-identities.json"))
        except Exception:
            self.send_error(503)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    if not os.environ.get("TN_IDENTITY_TOKEN"):
        raise SystemExit("TN_IDENTITY_TOKEN required")
    HTTPServer(("127.0.0.1", 8792), Handler).serve_forever()
