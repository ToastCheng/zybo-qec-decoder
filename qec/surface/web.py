"""Loopback-only surface-code teaching lab, backed by Stim and the existing UF decoder."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import threading
from pathlib import Path
import json
from functools import lru_cache
import stim
from qec.surface.decoder import decode


class Lab:
    """Stim-backed d3 Z teaching model with optional external prediction and counterfactual replay."""

    def __init__(self, decoder=None):
        """Load the committed decoder graph and flattened ideal circuit without opening serial."""
        self.decoder = decoder
        self.config = json.loads(
            Path(__file__).with_name("graphs").joinpath("d3_z_r3.json").read_text()
        )
        self.clean = stim.Circuit.generated(
            "surface_code:rotated_memory_z", distance=3, rounds=3
        ).flattened()

    def _segments(self):
        """Split the ideal circuit at TICKs, retaining the initial pre-TICK segment."""
        segments = [stim.Circuit()]
        for op in self.clean:
            if op.name == "TICK":
                segments.append(stim.Circuit())
            else:
                segments[-1].append(op)
        return segments

    def _fault_circuit(self, faults):
        """Inject probability-one Pauli errors before operations at each selected tick."""
        circuit = stim.Circuit()
        for tick, segment in enumerate(self._segments()):
            if tick:
                circuit.append("TICK")
            for fault in faults:
                if fault["tick"] == tick:
                    circuit.append(fault["pauli"] + "_ERROR", [fault["qubit"]], 1)
            circuit += segment
        return circuit

    @lru_cache(maxsize=512)
    def _signature(self, tick, qubit, pauli):
        """Cache a singleton fault as 24 detector bits followed by its observable bit."""
        s, o = self._sample(
            self._fault_circuit([dict(tick=tick, qubit=qubit, pauli=pauli)])
        )
        return s | (o << 24)

    @lru_cache(maxsize=8)
    def _basis(self, ticks):
        # Bounded GF(2) elimination, not exponential enumeration. Each column is
        # a real Stim singleton signature. This is a representative, not MWPM.
        """Build a bounded GF(2) basis of real singleton signatures and their Pauli representatives."""
        basis = {}
        for tick in ticks:
            for datum in self.layout()["data"]:
                for pauli in "XZ":
                    value = self._signature(tick, datum["id"], pauli)
                    frame = frozenset({(tick, datum["id"], pauli)})
                    while value:
                        pivot = value.bit_length() - 1
                        if pivot not in basis:
                            basis[pivot] = (value, frame)
                            break
                        row, other = basis[pivot]
                        value ^= row
                        frame = frame ^ other
        return basis

    def _correction(self, faults, syndrome, prediction):
        """Solve the requested syndrome/prediction signature at the injected ticks, or return None."""
        # Include the observable bit: cancelling detectors alone can hide a logical error.
        value = syndrome | (prediction << 24)
        frame = frozenset()
        basis = self._basis(tuple(sorted({f["tick"] for f in faults})))
        while value:
            pivot = value.bit_length() - 1
            if pivot not in basis:
                return None
            row, other = basis[pivot]
            value ^= row
            frame = frame ^ other
        return [dict(tick=t, qubit=q, pauli=p) for t, q, p in sorted(frame)]

    def _pauli_trace(self, faults):
        """Propagate an illustrative Pauli frame through H/CX and erase reset-qubit errors."""
        frame = stim.PauliString(self.clean.num_qubits)
        frames = []
        for tick, segment in enumerate(self._segments()):
            for f in faults:
                if f["tick"] == tick:
                    local = stim.PauliString(self.clean.num_qubits)
                    local[f["qubit"]] = f["pauli"]
                    frame *= local
            for op in segment:
                if op.name in ("R", "MR"):
                    for target in op.targets_copy():
                        frame[target.value] = 0
                elif op.name in ("H", "CX"):
                    frame = frame.after(op)
            frames.append(
                {str(q): "_XYZ"[frame[q]] for q in range(len(frame)) if frame[q]}
            )
        return frames

    def simulate_faults(self, faults):
        """Validate timed faults, obtain a prediction and independently replay a same-tick representative."""
        allowed = {q["id"] for q in self.layout()["data"]}
        if not isinstance(faults, list) or len(faults) > 64:
            raise ValueError("faults must be a list of at most 64 records")
        for f in faults:
            if (
                not isinstance(f, dict)
                or set(f) != {"tick", "qubit", "pauli"}
                or type(f["tick"]) is not int
                or not 0 <= f["tick"] < len(self._segments())
                or type(f["qubit"]) is not int
                or f["qubit"] not in allowed
                or f["pauli"] not in ("X", "Y", "Z")
            ):
                raise ValueError("Expected tick, data qubit and Pauli X/Y/Z")
        injected = self._fault_circuit(faults)
        syndrome, observable = self._sample(injected)
        result = decode(self.config["detectors"], self.config["edges"], syndrome)
        indices = [i for i in range(24) if syndrome >> i & 1]
        detectors = self.layout()["detectors"]
        trace = []
        frames = self._pauli_trace(faults)
        for tick, segment in enumerate(self._segments()):
            trace.append(
                dict(
                    tick=tick,
                    operations=str(segment),
                    pauli_frame=frames[tick],
                    faults=[f for f in faults if f["tick"] <= tick],
                    detector_indices=[
                        i for i in indices if detectors[i]["available_tick"] <= tick
                    ],
                )
            )
        hardware = self.decoder(syndrome) if self.decoder is not None else None
        if self.decoder is not None and (
            not isinstance(hardware, dict)
            or type(hardware.get("prediction")) is not int
            or hardware["prediction"] not in (0, 1)
            or type(hardware.get("cycles")) is not int
            or hardware["cycles"] <= 0
        ):
            raise IOError("Invalid FPGA decoder result")
        reference_prediction = result["prediction"]
        if hardware:
            result["prediction"] = hardware["prediction"]
        correction = self._correction(faults, syndrome, result["prediction"])
        # This is a counterfactual replay, not a causal correction applied to a quantum device.
        replay = (
            self._fault_circuit(faults + correction) if correction is not None else None
        )
        rs, ro = self._sample(replay) if replay is not None else (None, None)
        return dict(
            result,
            syndrome=syndrome,
            observable=observable,
            correction=correction,
            corrected_circuit=str(replay) if replay is not None else None,
            correction_frame=self._pauli_trace(correction)[-1]
            if correction is not None
            else {},
            residual_syndrome=rs,
            residual_observable=ro,
            detector_indices=indices,
            trace=trace,
            source="FPGA" if hardware else "Simulated",
            hardware=hardware,
            reference_prediction=reference_prediction,
            host_frame=result["prediction"],
            logical_success=observable == result["prediction"] and not result["error"],
            injected_circuit=str(injected),
        )

    def _circuit(self, errors, correction=None):
        """Build the legacy injection circuit, placing errors after the first MR instruction."""
        circuit = stim.Circuit()
        inserted = False
        for op in self.clean:
            circuit.append(op)
            if op.name == "MR" and not inserted:
                for frame in (errors, correction or {}):
                    for q, pauli in sorted(
                        frame.items(), key=lambda item: int(item[0])
                    ):
                        circuit.append(pauli + "_ERROR", [int(q)], 1)
                inserted = True
        return circuit

    @staticmethod
    def _sample(circuit):
        """Sample one deterministic fault circuit and return packed syndrome and observable."""
        bits, obs = circuit.compile_detector_sampler(seed=0).sample(
            1, separate_observables=True
        )
        return sum(int(b) << i for i, b in enumerate(bits[0])), int(obs[0, 0])

    def _representatives(self):
        # Dynamic programming over independent Pauli faults. Signatures come from
        # actual circuit simulation, not geometrical guesses about graph edges.
        """Find minimum-support legacy Pauli representatives by dynamic programming over signatures."""
        representatives = {(0, 0): {}}
        for datum in self.layout()["data"]:
            q = str(datum["id"])
            effects = [(p, self._sample(self._circuit({q: p}))) for p in "XYZ"]
            updated = dict(representatives)
            for (syndrome, observable), frame in representatives.items():
                for p, (ds, do) in effects:
                    key = (syndrome ^ ds, observable ^ do)
                    candidate = dict(frame, **{q: p})
                    if key not in updated or len(candidate) < len(updated[key]):
                        updated[key] = candidate
            representatives = updated
        return representatives

    def simulate(self, errors):
        """Validate legacy qubit-to-Pauli input and return UF correction plus independent replay evidence."""
        allowed = {str(q["id"]) for q in self.layout()["data"]}
        if (
            not isinstance(errors, dict)
            or len(errors) > 9
            or any(
                q not in allowed or not isinstance(p, str) or p not in ("X", "Y", "Z")
                for q, p in errors.items()
            )
        ):
            raise ValueError(
                "errors must map canonical data-qubit IDs to X, Y or Z (at most 9)"
            )
        injected = self._circuit(errors)
        syndrome, observable = self._sample(injected)
        result = decode(self.config["detectors"], self.config["edges"], syndrome)
        residual = syndrome
        for edge in result["correction_edges"]:
            for vertex in self.config["edges"][edge][:2]:
                if vertex < self.config["detectors"]:
                    residual ^= 1 << vertex
        if not hasattr(self, "_frames"):
            self._frames = self._representatives()
        correction = self._frames.get((syndrome, result["prediction"]))
        replay = self._circuit(errors, correction) if correction is not None else None
        rs, ro = self._sample(replay) if replay is not None else (None, None)
        return dict(
            result,
            syndrome=syndrome,
            observable=observable,
            detector_indices=[i for i in range(24) if syndrome >> i & 1],
            graph_residual=residual,
            correction=correction,
            residual_syndrome=rs,
            residual_observable=ro,
            logical_success=observable == result["prediction"] and not result["error"],
            injected_circuit=str(injected),
            corrected_circuit=str(replay) if replay is not None else None,
        )

    def layout(self):
        """Derive data/check supports, detector availability and operation ticks from the actual Stim circuit."""
        coords = self.clean.get_final_qubit_coordinates()
        data = next(
            [t.value for t in op.targets_copy()] for op in self.clean if op.name == "M"
        )
        xchecks = set()
        for op in self.clean:
            if op.name == "H":
                xchecks = {t.value for t in op.targets_copy()}
                break
        support = {q: set() for q in coords if q not in data}
        for op in self.clean:
            if op.name == "MR":
                break
            if op.name == "CX":
                targets = [t.value for t in op.targets_copy()]
                for a, b in zip(targets[::2], targets[1::2]):
                    ancilla, datum = (a, b) if a in support else (b, a)
                    support[ancilla].add(datum)
        availability = [
            tick
            for tick, segment in enumerate(self._segments())
            for op in segment
            if op.name == "DETECTOR"
        ]
        ticks = [
            dict(
                id=tick,
                operations=[
                    dict(
                        name=op.name,
                        targets=[
                            t.value for t in op.targets_copy() if t.is_qubit_target
                        ],
                    )
                    for op in segment
                    if op.name in ("R", "H", "CX", "MR", "M")
                ],
            )
            for tick, segment in enumerate(self._segments())
        ]
        return dict(
            source="FPGA" if self.decoder else "Simulated",
            ticks=ticks,
            data=[dict(id=q, coords=coords[q]) for q in data],
            checks=[
                dict(
                    id=q,
                    coords=coords[q],
                    basis="X" if q in xchecks else "Z",
                    support=sorted(s),
                )
                for q, s in support.items()
            ],
            detectors=[
                dict(id=d, coords=c, available_tick=availability[d])
                for d, c in self.clean.get_detector_coordinates().items()
            ],
            injection="Before selected tick operations",
            code="Rotated surface code · d=3 · Z memory · 3 rounds",
            edges=self.config["edges"],
        )


class SerialDecoder:
    """One complete-window transaction; no reset or programming commands."""

    def __init__(self, port, timeout=1):
        """Configure a port name, bounded lock timeout and sequence counter without opening it."""
        self.port = port
        self.timeout = timeout
        self.lock = threading.Lock()
        self.sequence = 0

    def __call__(self, syndrome):
        """Serialize one exclusive UART transaction; reject invalid replies without software fallback."""
        import serial
        from qec.surface.host import request, parse

        if not self.lock.acquire(timeout=self.timeout):
            raise IOError("FPGA port busy")
        try:
            seq = self.sequence
            self.sequence = (seq + 1) % 256
            tx = request(seq, syndrome)
            # Configure handshake lines before opening: no deliberate board reset.
            ep = serial.Serial(
                port=None,
                baudrate=115200,
                timeout=self.timeout,
                write_timeout=self.timeout,
                exclusive=True,
            )
            ep.dtr = ep.rts = False
            ep.port = self.port
            with ep:
                ep.reset_input_buffer()
                if ep.write(tx) != len(tx):
                    raise IOError("Incomplete FPGA request")
                rx = ep.read(9)
            try:
                prediction, cycles = parse(rx, seq)
            except ValueError as exc:
                raise IOError(f"FPGA reply rejected: {exc}; rx={rx.hex()}") from exc
            if not cycles:
                raise IOError("FPGA reply has no decoder cycles")
            return dict(
                prediction=prediction, cycles=cycles, tx_hex=tx.hex(), rx_hex=rx.hex()
            )
        finally:
            self.lock.release()


def make_server(port=8765, decoder=None):
    """Return a loopback-bound threaded HTTP server with bounded JSON input and serialized decoding."""
    model = Lab(decoder=decoder)
    lock = threading.Lock()
    assets = Path(__file__).with_name("web_assets")

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, content, mime="application/json"):
            """Write JSON or local asset bytes with explicit length, MIME and restrictive response headers."""
            body = (
                json.dumps(content).encode() if mime == "application/json" else content
            )
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

        def do_GET(self):
            """Serve the derived layout or one of three allowlisted local assets; reject other paths."""
            if self.path == "/api/layout":
                self.reply(200, model.layout())
                return
            files = {
                "/": ("index.html", "text/html"),
                "/app.js": ("app.js", "text/javascript"),
                "/style.css": ("style.css", "text/css"),
            }
            if self.path not in files:
                self.reply(404, {"error": "Not found"})
                return
            filename, mime = files[self.path]
            self.reply(200, (assets / filename).read_bytes(), mime)

        def do_POST(self):
            """Validate framing/origin/body, acquire the decoder lock, and map input/backend errors to HTTP."""
            if self.path != "/api/simulate":
                self.reply(404, {"error": "Not found"})
                return
            # There is no cross-origin API or filesystem access. Bound memory and
            # reject unsupported framing instead of waiting for a chunked body.
            if self.headers.get("Transfer-Encoding"):
                self.reply(400, {"error": "Transfer-Encoding is not supported"})
                self.close_connection = True
                return
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                self.reply(403, {"error": "Cross-origin requests are not allowed"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.reply(
                        413 if length > 4096 else 400,
                        {"error": "Body must be 1 to 4096 bytes"},
                    )
                    self.close_connection = True
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) not in (
                    {"errors"},
                    {"faults"},
                ):
                    raise ValueError("Expected an object containing only faults")
                if not lock.acquire(timeout=2):
                    raise IOError("Decoder busy; retry")
                try:
                    if "faults" in body:
                        result = model.simulate_faults(body["faults"])
                    elif decoder:
                        # Old API is explicitly converted to the original location.
                        model.simulate(body["errors"])  # validate legacy input first
                        result = model.simulate_faults(
                            [
                                dict(tick=8, qubit=int(q), pauli=p)
                                for q, p in body["errors"].items()
                            ]
                        )
                    else:
                        result = model.simulate(body["errors"])
                finally:
                    lock.release()
                self.reply(200, result)
            except OSError as exc:
                self.reply(
                    503,
                    {"error": str(exc), "source": "FPGA" if decoder else "Simulated"},
                )
            except (ValueError, UnicodeDecodeError) as exc:
                self.reply(400, {"error": str(exc)})

        def setup(self):
            """Initialize the request stream and bound socket operations to five seconds."""
            super().setup()
            self.connection.settimeout(5)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    """Serve the local teaching lab, optionally using an explicitly selected loaded memory-image UART."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--serial-port", help="optional loaded d3 Z r3 FPGA UART, 115200 baud"
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    decoder = SerialDecoder(args.serial_port) if args.serial_port else None
    server = make_server(args.port, decoder=decoder)
    print(
        f"QEC lab: http://127.0.0.1:{server.server_port} ({'FPGA' if decoder else 'Simulated'})",
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
