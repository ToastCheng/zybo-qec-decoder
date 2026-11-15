import http.client
import json
import threading
from contextlib import contextmanager
from pathlib import Path

from qec.surface.web import make_server


@contextmanager
def server(serial_port=None):
    service = make_server(0, serial_port)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    try:
        yield service.server_port
    finally:
        service.shutdown()
        service.server_close()
        thread.join()


def request(port, method, path, body=None, **headers):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request(method, path, body, headers)
    response = connection.getresponse()
    data = response.read()
    status = response.status
    connection.close()
    return status, data


def test_canonical_routes_and_error_recovery():
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


def test_layout_and_invalid_runs_never_open_serial():
    with server("/no/such/serial/device") as port:
        status, raw = request(port, "GET", "/api/layout")
        assert status == 200 and json.loads(raw)["source"] == "FPGA"
        assert request(port, "POST", "/api/run", "{}")[0] == 400
        cfg = {"circuit": "BAD 0", "reference": None, "seed": 1, "added_noise": 0}
        assert request(port, "POST", "/api/circuit-run", json.dumps(cfg))[0] == 400
