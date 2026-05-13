#!/usr/bin/env python3
"""
Micromedex CKO Local Proxy Server
==================================
Runs a local HTTP server on localhost:8765 that:
  1. Accepts JSON POST requests from the browser (no auth needed from browser side)
  2. Forwards them to the real CKO endpoint with HTTP Basic Auth
  3. Returns the CKO response to the browser with CORS headers

Why this is needed:
  - Browsers block cross-origin requests (CORS)
  - The Micromedex server only allows requests from whitelisted IPs
  - Running this proxy on your own machine (whose IP is whitelisted) solves both

Usage:
  python proxy.py

  Or with custom settings:
  CKO_URL="https://..." CKO_USERNAME="user" CKO_PASSWORD="pass" python proxy.py
  python proxy.py --port 8765 --url "https://..." --username "user" --password "pass"

Then open micromedex-ui/index.html in your browser.
The UI will automatically connect to http://localhost:8765/cko

Requirements:
  Python 3.6+  (no third-party packages needed — uses only stdlib)
  Optional: pip install requests   (faster, better SSL handling)
"""

import os
import sys
import json
import base64
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ──────────────────────────────────────────────────────────────
# CONFIG — from env vars or CLI args
# ──────────────────────────────────────────────────────────────
DEFAULT_PORT    = 8765
DEFAULT_CKO_URL = "https://www.micromedexsolutions.com/ckoapp/librarian/PFActionId/ckoapp.JsonRequest"

# Try requests first, fall back to urllib
try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error


# ──────────────────────────────────────────────────────────────
# REQUEST HANDLER
# ──────────────────────────────────────────────────────────────
class CKOProxyHandler(BaseHTTPRequestHandler):
    # Set by main() after parsing args
    cko_url      = DEFAULT_CKO_URL
    cko_username = ""
    cko_password = ""

    def log_message(self, fmt, *args):
        """Custom log — shorter and colored."""
        method = args[0] if args else ""
        status = args[1] if len(args) > 1 else ""
        color  = "\033[92m" if str(status).startswith("2") else "\033[91m"
        reset  = "\033[0m"
        print(f"  {color}{status}{reset}  {self.path}")

    # ── CORS preflight ──────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ── Health check / info ─────────────────────────────────────
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = json.dumps({
                "status": "ok",
                "proxy": "Micromedex CKO Proxy",
                "target": self.cko_url,
                "authenticated": bool(self.cko_username)
            }).encode()
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    # ── Main proxy path ─────────────────────────────────────────
    def do_POST(self):
        if self.path not in ("/cko", "/cko/"):
            self.send_response(404)
            self._cors_headers()
            self.end_headers()
            return

        # Read request body
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""

        # Forward to CKO
        try:
            response_body, status_code = self._forward(body)
        except Exception as e:
            error = json.dumps({"proxy_error": str(e)}).encode()
            self.send_response(502)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error)
            return

        self.send_response(status_code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _cors_headers(self):
        """Add permissive CORS headers so the browser won't block the response."""
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _forward(self, body: bytes):
        """Forward the request body to CKO with Basic Auth. Returns (response_bytes, http_status)."""
        headers = {"Content-Type": "application/json"}

        if self.cko_username:
            creds = base64.b64encode(
                f"{self.cko_username}:{self.cko_password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {creds}"

        if HAS_REQUESTS:
            resp = _requests.post(
                self.cko_url,
                data=body,
                headers=headers,
                timeout=30,
                verify=True
            )
            return resp.content, resp.status_code
        else:
            req = urllib.request.Request(
                self.cko_url, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    return res.read(), res.status
            except urllib.error.HTTPError as e:
                return e.read(), e.code


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Micromedex CKO Local Proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--port", "-p", type=int,
                        default=int(os.environ.get("PROXY_PORT", DEFAULT_PORT)),
                        help=f"Local port to listen on (default: {DEFAULT_PORT})")
    parser.add_argument("--url",
                        default=os.environ.get("CKO_URL", DEFAULT_CKO_URL),
                        help="CKO endpoint URL")
    parser.add_argument("--username",
                        default=os.environ.get("CKO_USERNAME", ""),
                        help="CKO username")
    parser.add_argument("--password",
                        default=os.environ.get("CKO_PASSWORD", ""),
                        help="CKO password")
    args = parser.parse_args()

    # Inject config into handler class
    CKOProxyHandler.cko_url      = args.url
    CKOProxyHandler.cko_username = args.username
    CKOProxyHandler.cko_password = args.password

    server = HTTPServer(("127.0.0.1", args.port), CKOProxyHandler)

    # ── Print startup banner ──────────────────────────────────
    bold  = "\033[1m"
    cyan  = "\033[96m"
    green = "\033[92m"
    gray  = "\033[90m"
    reset = "\033[0m"

    print(f"\n{bold}Micromedex CKO Proxy{reset}")
    print(f"  Listening on  {cyan}http://localhost:{args.port}{reset}")
    print(f"  CKO endpoint  {gray}{args.url}{reset}")
    print(f"  Auth          {green if args.username else gray}{'✓ ' + args.username if args.username else '✗ no credentials set'}{reset}")
    print()
    print(f"  In the UI, set Endpoint URL to:  {cyan}http://localhost:{args.port}/cko{reset}")
    print(f"  Leave Username and Password blank in the UI (proxy handles auth).")
    print()
    print(f"  Press Ctrl+C to stop.\n")

    if not args.username:
        print(f"\033[93m  ⚠ Warning: no credentials set. Use --username / --password or CKO_USERNAME / CKO_PASSWORD env vars.\033[0m\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Proxy stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
