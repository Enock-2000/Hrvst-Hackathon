"""
HTTP mutex for Eufy P2P livestreams — one active stream per HomeBase station.

Bridges call POST /acquire before device.start_livestream and POST /release when done.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

LISTEN_HOST = os.environ.get("COORDINATOR_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("COORDINATOR_PORT", "8090"))
LEASE_SECONDS = int(os.environ.get("COORDINATOR_LEASE_SEC", "45"))


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.holder_serial: Optional[str] = None
        self.holder_name: Optional[str] = None
        self.expires_at: float = 0.0

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            now = time.time()
            if self.holder_serial and self.expires_at > now:
                return {
                    "holder_serial": self.holder_serial,
                    "holder_name": self.holder_name,
                    "expires_in_sec": round(self.expires_at - now, 1),
                }
            return {"holder_serial": None, "holder_name": None, "expires_in_sec": 0}

    def acquire(self, serial: str, name: str) -> tuple[int, dict[str, Any]]:
        with self.lock:
            now = time.time()
            prev_serial = None
            if self.holder_serial and self.expires_at > now and self.holder_serial != serial:
                prev_serial = self.holder_serial
            self.holder_serial = serial
            self.holder_name = name or serial
            self.expires_at = now + LEASE_SECONDS
            body: dict[str, Any] = {
                "ok": True,
                "serial": serial,
                "lease_sec": LEASE_SECONDS,
            }
            if prev_serial:
                body["preempted_serial"] = prev_serial
            return 200, body

    def renew(self, serial: str) -> tuple[int, dict[str, Any]]:
        with self.lock:
            now = time.time()
            if self.holder_serial != serial or self.expires_at <= now:
                return 409, {"ok": False, "error": "not_holder", "status": self._status_unlocked()}
            self.expires_at = now + LEASE_SECONDS
            return 200, {"ok": True, "lease_sec": LEASE_SECONDS}

    def release(self, serial: str) -> tuple[int, dict[str, Any]]:
        with self.lock:
            if self.holder_serial == serial:
                self.holder_serial = None
                self.holder_name = None
                self.expires_at = 0.0
            return 200, {"ok": True}

    def _status_unlocked(self) -> dict[str, Any]:
        return {
            "holder_serial": self.holder_serial,
            "holder_name": self.holder_name,
        }


STATE = _State()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[COORD] {self.address_string()} {fmt % args}")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send(self, code: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, {"ok": True})
            return
        if path == "/status":
            self._send(200, STATE.snapshot())
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        payload = self._read_json()
        serial = str(payload.get("serial") or "").strip()
        name = str(payload.get("name") or serial).strip()

        if path == "/acquire":
            if not serial:
                self._send(400, {"error": "serial required"})
                return
            code, body = STATE.acquire(serial, name)
            print(f"[COORD] acquire {serial} ({name}) -> {code} {body}")
            self._send(code, body)
            return

        if path == "/renew":
            if not serial:
                self._send(400, {"error": "serial required"})
                return
            code, body = STATE.renew(serial)
            self._send(code, body)
            return

        if path == "/release":
            if not serial:
                self._send(400, {"error": "serial required"})
                return
            code, body = STATE.release(serial)
            print(f"[COORD] release {serial}")
            self._send(code, body)
            return

        self._send(404, {"error": "not_found"})


def main() -> None:
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"[COORD] listening on {LISTEN_HOST}:{LISTEN_PORT} lease={LEASE_SECONDS}s")
    server.serve_forever()


if __name__ == "__main__":
    main()
