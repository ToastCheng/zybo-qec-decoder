"""Loopback annotated Clifford circuit laboratory; explicit run, local replay."""

import stim
import argparse
import json
import subprocess
import sys
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from qec.surface.runtime_host import RuntimeSerialDecoder
from qec.surface.runtime_circuit import compile_circuit, Capacities, _parse


def _prepare(settings):
    if not isinstance(settings, dict) or set(settings) != {
        "circuit",
        "reference",
        "seed",
        "added_noise",
    }:
        raise ValueError("Expected circuit, reference, seed and added_noise")
    if type(settings["seed"]) is not int or not 0 <= settings["seed"] <= 2**53 - 1:
        raise ValueError("seed must be an integer in 0..2^53-1")
    p = settings["added_noise"]
    if type(p) not in (int, float) or not 0 <= p <= 0.75:
        raise ValueError("added_noise must be finite in 0..0.75")
    circuit = _parse(settings["circuit"], Capacities())
    if not p:
        return str(circuit), settings["reference"]
    noisy = stim.Circuit()
    for op in circuit.flattened():
        data = stim.gate_data(op.name)
        targets = op.targets_copy()
        if data.is_unitary and (data.is_single_qubit_gate or data.is_two_qubit_gate):
            width = 2 if data.is_two_qubit_gate else 1
            for start in range(0, len(targets), width):
                group = targets[start : start + width]
                noisy.append(op.name, group, op.gate_args_copy())
                noisy.append("DEPOLARIZE2" if width == 2 else "DEPOLARIZE1", group, p)
        else:
            noisy.append(op)
            if data.is_unitary:
                qubits = sorted({t.qubit_value for t in targets if not t.is_combiner})
                if qubits:
                    noisy.append("DEPOLARIZE1", qubits, p)
    # At nonzero added noise the graph comes from the exact experiment, never an
    # unrelated supplied reference. Base noise instructions are retained intact.
    return str(noisy), None


from qec.surface.decoder import decode


def _mask(bits):
    return sum(int(bit) << i for i, bit in enumerate(bits))


def _compile_bounded(settings, capacities=None):
    """Kill a costly compiler worker after 15 seconds; no serial in the worker."""
    try:
        worker = subprocess.run(
            [sys.executable, "-m", "qec.surface.runtime_web", "--compile-worker"],
            input=json.dumps(
                dict(
                    settings=settings,
                    capacities=asdict(capacities) if capacities else None,
                )
            ),
            text=True,
            capture_output=True,
            timeout=15,
            cwd=Path(__file__).resolve().parents[2],
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Circuit compilation timeout (15 seconds)") from exc
    if worker.returncode:
        raise ValueError("Circuit compiler worker failed")
    output = json.loads(worker.stdout)
    if "error" in output:
        raise ValueError(output["error"])
    return output


def _diagram_operation(op):
    """Typed targets from Stim, never inferred from debug/source strings."""
    targets = []
    for t in op.targets_copy():
        if t.is_combiner:
            target = dict(combiner=True)
        elif t.is_measurement_record_target:
            target = dict(record=t.value)
        elif t.is_sweep_bit_target:
            target = dict(sweep=t.value)
        else:
            target = dict(qubit=t.qubit_value)
            for basis in "XYZ":
                if getattr(t, f"is_{basis.lower()}_target"):
                    target["pauli"] = basis
            if t.is_inverted_result_target:
                target["inverted"] = True
        targets.append(target)
    data = stim.gate_data(op.name)
    return dict(
        name=op.name,
        kind=(
            "pair"
            if data.is_two_qubit_gate
            else "single" if data.is_single_qubit_gate else "product"
        ),
        targets=targets,
        text=str(op),
    )


class RuntimeLab:
    """Single-shot experiments; never substitutes software for a hardware result."""

    def __init__(self, serial_port=None):
        self.serial_port = serial_port

    def validate(self, settings):
        return _compile_bounded(settings)

    def run(self, settings):
        compiled = self.validate(settings)
        circuit = stim.Circuit(compiled["circuit"])
        simulator = stim.FlipSimulator(
            batch_size=1,
            num_qubits=circuit.num_qubits,
            seed=settings["seed"],
            disable_stabilizer_randomization=True,
        )
        segments = [stim.Circuit()]
        for op in circuit.flattened():
            if op.name == "TICK":
                segments.append(stim.Circuit())
            else:
                segments[-1].append(op)
        trace = []
        for tick, segment in enumerate(segments):
            simulator.do(segment)
            trace.append(
                dict(
                    tick=tick,
                    operations=[str(op) for op in segment],
                    diagram=[_diagram_operation(op) for op in segment],
                    paulis=str(simulator.peek_pauli_flips(instance_index=0))[1:],
                    detectors=simulator.get_detector_flips(instance_index=0).tolist(),
                    observables=simulator.get_observable_flips(
                        instance_index=0
                    ).tolist(),
                )
            )
        syndrome = _mask(simulator.get_detector_flips(instance_index=0))
        truth = _mask(simulator.get_observable_flips(instance_index=0))
        result = dict(
            compiled=compiled,
            trace=trace,
            seed=settings["seed"],
            syndrome=syndrome,
            observable_truth=truth,
        )
        if self.serial_port:
            # Invalid circuits are rejected above before opening the exclusive port.
            # Read real capacities, validate again, upload every run, never fallback.
            with RuntimeSerialDecoder(self.serial_port) as board:
                identity = board.identity()
                limits = Capacities(
                    max_detectors=identity.max_detectors,
                    max_edges=identity.max_edges,
                    max_observables=identity.max_observables,
                )
                compiled = _compile_bounded(settings, limits)
                loaded = board.load_graph(
                    circuit.num_detectors, compiled["edges"], circuit.num_observables
                )
                answer = board.decode(syndrome)
                result.update(
                    source="FPGA",
                    compiled=compiled,
                    prediction=answer.prediction,
                    cycles=answer.cycles,
                    identity=list(loaded.words),
                    transactions=[
                        dict(
                            opcode=t["opcode"],
                            tx_hex=t["tx"].hex(),
                            rx_hex=t["rx"].hex(),
                            error=t.get("error"),
                        )
                        for t in board.transactions
                    ],
                )
            return result
        answer = decode(circuit.num_detectors, compiled["edges"], syndrome)
        if answer["error"]:
            raise ValueError("Software graph decoder could not resolve syndrome")
        result.update(
            source="Software",
            prediction=answer["prediction"],
            cycles=None,
            transactions=[],
        )
        return result


ASSETS = Path(__file__).with_name("runtime_web_assets")
EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "runtime"


def make_server(port=8766, serial_port=None):
    """Bind IPv4 loopback only; exact Host/Origin allowlist, bounded POST work."""
    lab = RuntimeLab(serial_port)
    busy = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def respond(self, status, value, content_type="application/json"):
            data = (
                json.dumps(value).encode()
                if content_type == "application/json"
                else value
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            hosts = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            if self.headers.get("Host") not in hosts or (
                self.headers.get("Origin") is not None
                and self.headers["Origin"] not in {"http://" + h for h in hosts}
            ):
                self.respond(403, {"error": "Loopback Host/Origin required"})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            if path == "/api/config":
                self.respond(
                    200,
                    dict(
                        source="FPGA" if serial_port else "Software",
                        example=(EXAMPLES / "phase_bell.stim").read_text(),
                        serial_configured=bool(serial_port),
                    ),
                )
            elif path in ("/", "/app.js", "/style.css"):
                name, mime = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/style.css": ("style.css", "text/css; charset=utf-8"),
                }[path]
                self.respond(200, (ASSETS / name).read_bytes(), mime)
            else:
                self.respond(404, {"error": "Not found"})

        def do_POST(self):
            if not self.allowed():
                return
            if self.path not in ("/api/run", "/api/validate"):
                self.respond(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if not 0 <= length <= 600000 or self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self.respond(413, {"error": "Body must have Content-Length <= 600000"})
                return
            if not busy.acquire(blocking=False):
                self.respond(429, {"error": "An experiment is already running"})
                return
            try:
                settings = json.loads(self.rfile.read(length))
                output = (
                    lab.run(settings)
                    if self.path == "/api/run"
                    else lab.validate(settings)
                )
                self.respond(200, output)
            except Exception as exc:
                self.respond(400, {"error": str(exc)})
            finally:
                busy.release()

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--serial-port")
    parser.add_argument("--compile-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.compile_worker:
        try:
            request = json.load(sys.stdin)
            text, reference = _prepare(request["settings"])
            limits = (
                Capacities(**request["capacities"]) if request["capacities"] else None
            )
            output = compile_circuit(text, reference, limits)
        except Exception as exc:
            output = {"error": str(exc)}
        print(json.dumps(output))
        return
    server = make_server(args.port, args.serial_port)
    print(
        f"Runtime circuit lab: http://127.0.0.1:{server.server_port} (explicit Run only)",
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
