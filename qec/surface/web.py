"""Serve the circuit editor on loopback, optionally behind a public HTTPS proxy."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from qec.surface.engine import EditorLab


def make_server(port=8765, serial_port=None, public_origin=None):
    public_host = None
    if public_origin is not None:
        parsed = urlsplit(public_origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or public_origin != "https://" + parsed.netloc
            or any(character.isspace() for character in public_origin)
        ):
            raise ValueError("--public-origin must be an HTTPS origin without a path")
        # Accessing port also rejects malformed or out-of-range port numbers.
        _ = parsed.port
        public_host = parsed.netloc
    lab = EditorLab(serial_port)
    busy = threading.Lock()
    assets = Path(__file__).with_name("web_assets")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def reply(self, status, value, mime="application/json"):
            body = json.dumps(value).encode() if mime == "application/json" else value
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def trusted(self):
            """Allow only configured authorities and their matching origins.

            Do not trust forwarded headers: the tunnel preserves the public Host.
            Host validation also applies when a navigation has no Origin header.
            """
            allowed = {
                host: "http://" + host
                for host in (
                    f"127.0.0.1:{self.server.server_port}",
                    f"localhost:{self.server.server_port}",
                )
            }
            if public_host is not None and public_origin is not None:
                allowed[public_host] = public_origin
            hosts = self.headers.get_all("Host", [])
            origins = self.headers.get_all("Origin", [])
            if (
                len(hosts) != 1
                or hosts[0] not in allowed
                or len(origins) > 1
                or origins
                and origins[0] != allowed[hosts[0]]
            ):
                self.close_connection = True
                self.reply(403, {"error": "Allowed Host and same Origin required"})
                return False
            return True

        def do_GET(self):
            if not self.trusted():
                return
            if self.path == "/api/layout":
                self.reply(200, lab.layout())
                return
            files = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if self.path not in files:
                self.reply(404, {"error": "Not found"})
                return
            name, mime = files[self.path]
            self.reply(200, (assets / name).read_bytes(), mime)

        def do_POST(self):
            if not self.trusted():
                return
            if self.path not in ("/api/run", "/api/circuit-run"):
                self.reply(404, {"error": "Not found"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            try:
                length = int(lengths[0]) if len(lengths) == 1 else -1
            except ValueError:
                length = -1
            limit = 800000 if self.path == "/api/circuit-run" else 16384
            if self.headers.get("Transfer-Encoding") or not 0 < length <= limit:
                self.close_connection = True
                self.reply(
                    413 if length > limit else 400,
                    {"error": f"Body must be 1..{limit} bytes with one Content-Length"},
                )
                return
            if not busy.acquire(blocking=False):
                self.reply(429, {"error": "An experiment is already running"})
                return
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete body")
                settings = json.loads(raw)
                output = (
                    lab.run(settings)
                    if self.path == "/api/run"
                    else lab.circuit_run(settings)
                )
                self.reply(200, output)
            except OSError as exc:
                self.reply(503, {"error": str(exc)})
            except (ValueError, UnicodeDecodeError) as exc:
                self.reply(400, {"error": str(exc)})
            finally:
                busy.release()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--serial-port", help="FPGA UART, 115200 baud")
    parser.add_argument(
        "--public-origin",
        help="Exact HTTPS origin allowed through a reverse proxy (enables public runs)",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")
    try:
        server = make_server(args.port, args.serial_port, args.public_origin)
    except ValueError as exc:
        parser.error(str(exc))
    print(
        f"Circuit editor: http://127.0.0.1:{server.server_port} ({'FPGA' if args.serial_port else 'Software'})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
