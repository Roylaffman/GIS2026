"""Serve the built map demo on http://127.0.0.1:8090

Usage:  .venv\\Scripts\\python.exe serve_map.py [port]
Serves files from web/ (index.html, dem_hillshade.png, pois.geojson, lib/...).
Also exposes /config.js with the Mapbox token read from .env at runtime.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import sys
from pathlib import Path

from gis_common import WEB_DIR, load_env

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB_DIR), **kw)

    def do_GET(self):
        # runtime config endpoint: expose .env values to the browser
        if self.path.split("?")[0] == "/config.js":
            env = load_env()
            token = env.get("MAPBOX_TOKEN", "")
            body = f"window.DSH_CONFIG = {json.dumps({'mapboxToken': token})};\n"
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

    def end_headers(self):
        # defeat browser caching so edits to index.html/geojson show up on refresh
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        super().end_headers()

    def log_message(self, fmt, *args):  # quieter console
        sys.stdout.write("[%s] %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    if not (WEB_DIR / "index.html").exists():
        sys.exit("web/index.html missing - run make_web.py first")
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), QuietHandler) as httpd:
        print(f"Serving {WEB_DIR}  ->  http://127.0.0.1:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
