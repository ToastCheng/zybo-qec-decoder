"""HTTP API and security tests for the web server in `qec.surface.web`."""

import http.client
import json
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from qec.surface.web import make_server


@contextmanager
def server(serial_port=None, public_origin=None):
    """Start the HTTP server on an ephemeral port and stop it cleanly when the context exits."""
    service = make_server(0, serial_port, public_origin=public_origin)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    try:
        yield service.server_port
    finally:
        service.shutdown()
        service.server_close()
        thread.join()


def request(port, method, path, body=None, **headers):
    """Send an HTTP request to localhost on `port` and return `(status, body_bytes)`."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request(method, path, body, headers)
    response = connection.getresponse()
    data = response.read()
    status = response.status
    connection.close()
    return status, data


def test_canonical_routes_and_error_recovery():
    """Valid routes serve assets and run experiments normally even after 400, 403, 404, and 413 errors."""
    with server() as port:
        status, raw = request(port, "GET", "/api/layout")
        layout = json.loads(raw)
        assert status == 200 and layout["protocol"] == "graph-v2"
        assert layout["source"] == "Software"
        for path in ["/", "/app.js", "/style.css"]:
            assert request(port, "GET", path)[0] == 200
        assert request(port, "GET", "/api/config")[0] == 404
        assert request(port, "POST", "/api/simulate", "{}")[0] == 404
        assert request(port, "GET", "/", Host="evil.test")[0] == 403
        assert (
            request(port, "POST", "/api/run", "{}", Origin="https://evil.test")[0]
            == 403
        )
        for raw in ["{}", "[]", "null", "{bad"]:
            assert request(port, "POST", "/api/run", raw)[0] == 400
        assert request(port, "POST", "/api/run", "x" * 16385)[0] == 413
        status, raw = request(
            port, "POST", "/api/run", json.dumps(layout["run_defaults"])
        )
        assert status == 200, raw
        result = json.loads(raw)
        assert result["experiment"]["compiled"]["counts"]["detectors"] == 24
        cfg = {
            "circuit": (
                Path(__file__).parents[1] / "examples/phase_bell.stim"
            ).read_text(),
            "reference": None,
            "seed": 1,
            "added_noise": 0,
            "logical_circuit": "H 0",
        }
        status, raw = request(port, "POST", "/api/circuit-run", json.dumps(cfg))
        assert status == 200, raw
        response = json.loads(raw)
        assert response["layout"]["kind"] == "circuit"
        assert response["layout"]["logical_circuit"] == "H 0"
        assert response["experiment"]["compiled"]["logical_mapping_verified"] is False


def test_explicit_public_origin_serves_assets_and_runs():
    """Configuring a public HTTPS origin permits matching Host/Origin requests alongside loopback access."""
    origin = "https://qec.toastcheng.com"
    with server(public_origin=origin) as port:
        headers = {"Host": "qec.toastcheng.com", "Origin": origin}
        for path in ["/", "/app.js", "/style.css", "/api/layout"]:
            assert request(port, "GET", path, Host=headers["Host"])[0] == 200
        status, raw = request(port, "GET", "/api/layout", **headers)
        assert status == 200
        settings = json.loads(raw)["run_defaults"]
        status, raw = request(port, "POST", "/api/run", json.dumps(settings), **headers)
        assert status == 200, raw
        assert json.loads(raw)["experiment"]["compiled"]["counts"]["detectors"] == 24
        assert request(port, "GET", "/")[0] == 200


def test_public_origin_does_not_weaken_host_or_origin_checks():
    """Mismatched, forwarded, or duplicate Host/Origin headers are rejected with 403 even with a public origin."""
    origin = "https://qec.toastcheng.com"
    with server() as port:
        assert request(port, "GET", "/", Host="qec.toastcheng.com")[0] == 403
    with server(public_origin=origin) as port:
        for host, incoming_origin in [
            ("evil.test", origin),
            ("qec.toastcheng.com.evil.test", origin),
            ("qec.toastcheng.com:443", origin),
            ("qec.toastcheng.com", "https://evil.test"),
            ("qec.toastcheng.com", "http://qec.toastcheng.com"),
            ("qec.toastcheng.com", "null"),
            (f"localhost:{port}", origin),
        ]:
            headers = {"Host": host, "Origin": incoming_origin}
            assert request(port, "GET", "/app.js", **headers)[0] == 403
            assert request(port, "POST", "/api/run", "{}", **headers)[0] == 403
        assert request(
            port, "GET", "/", Host="evil.test",
            **{"X-Forwarded-Host": "qec.toastcheng.com", "X-Forwarded-Proto": "https"},
        )[0] == 403
        for duplicate in ["Host", "Origin"]:
            connection = http.client.HTTPConnection("127.0.0.1", port)
            connection.putrequest("GET", "/", skip_host=True)
            connection.putheader("Host", "qec.toastcheng.com")
            connection.putheader("Origin", origin)
            connection.putheader(duplicate, "qec.toastcheng.com" if duplicate == "Host" else origin)
            connection.endheaders()
            response = connection.getresponse()
            assert response.status == 403
            response.read()
            connection.close()


@pytest.mark.parametrize("origin", [
    "http://qec.toastcheng.com", "https://qec.toastcheng.com/",
    "https://qec.toastcheng.com/path", "https://user@qec.toastcheng.com",
    "https://qec.toastcheng.com?x=1", "https://qec.toastcheng.com#fragment",
    "https://qec.toastcheng.com:bad", "https://qec.toastcheng.com:65536",
    "https://qec.toastcheng.com\n", "https://", "null",
])
def test_invalid_public_origins_are_rejected(origin):
    """Non-HTTPS or malformed public origin strings raise ValueError on server creation."""
    with pytest.raises(ValueError):
        make_server(0, public_origin=origin)


def test_layout_and_invalid_runs_never_open_serial():
    """Layout queries advertise FPGA mode and invalid run requests return 400 without opening the serial port."""
    with server("/no/such/serial/device") as port:
        status, raw = request(port, "GET", "/api/layout")
        assert status == 200 and json.loads(raw)["source"] == "FPGA"
        assert request(port, "POST", "/api/run", "{}")[0] == 400
        cfg = {"circuit": "BAD 0", "reference": None, "seed": 1, "added_noise": 0}
        assert request(port, "POST", "/api/circuit-run", json.dumps(cfg))[0] == 400
