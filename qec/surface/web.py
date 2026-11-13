"""Loopback-only surface-code teaching lab, backed by Stim and the existing UF decoder."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import threading
from pathlib import Path
import json
import stim
from qec.surface.decoder import decode


class Lab:
    def __init__(self):
        self.config = json.loads(Path(__file__).with_name('graphs').joinpath('d3_z_r3.json').read_text())
        self.clean = stim.Circuit.generated('surface_code:rotated_memory_z', distance=3, rounds=3).flattened()

    def _circuit(self, errors, correction=None):
        circuit = stim.Circuit()
        inserted = False
        for op in self.clean:
            circuit.append(op)
            if op.name == 'MR' and not inserted:
                for frame in (errors, correction or {}):
                    for q, pauli in sorted(frame.items(), key=lambda item: int(item[0])):
                        circuit.append(pauli + '_ERROR', [int(q)], 1)
                inserted = True
        return circuit

    @staticmethod
    def _sample(circuit):
        bits, obs = circuit.compile_detector_sampler(seed=0).sample(1, separate_observables=True)
        return sum(int(b) << i for i, b in enumerate(bits[0])), int(obs[0, 0])

    def _representatives(self):
        # Dynamic programming over independent Pauli faults. Signatures come from
        # actual circuit simulation, not geometrical guesses about graph edges.
        representatives = {(0, 0): {}}
        for datum in self.layout()['data']:
            q = str(datum['id'])
            effects = [(p, self._sample(self._circuit({q: p}))) for p in 'XYZ']
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
        allowed = {str(q['id']) for q in self.layout()['data']}
        if not isinstance(errors, dict) or len(errors) > 9 or any(
                q not in allowed or not isinstance(p, str) or p not in ('X', 'Y', 'Z')
                for q, p in errors.items()):
            raise ValueError('errors must map canonical data-qubit IDs to X, Y or Z (at most 9)')
        injected = self._circuit(errors)
        syndrome, observable = self._sample(injected)
        result = decode(self.config['detectors'], self.config['edges'], syndrome)
        residual = syndrome
        for edge in result['correction_edges']:
            for vertex in self.config['edges'][edge][:2]:
                if vertex < self.config['detectors']:
                    residual ^= 1 << vertex
        if not hasattr(self, '_frames'):
            self._frames = self._representatives()
        correction = self._frames.get((syndrome, result['prediction']))
        replay = self._circuit(errors, correction) if correction is not None else None
        rs, ro = self._sample(replay) if replay is not None else (None, None)
        return dict(result, syndrome=syndrome, observable=observable,
                    detector_indices=[i for i in range(24) if syndrome >> i & 1],
                    graph_residual=residual, correction=correction,
                    residual_syndrome=rs, residual_observable=ro,
                    logical_success=observable == result['prediction'] and not result['error'],
                    injected_circuit=str(injected), corrected_circuit=str(replay) if replay is not None else None)

    def layout(self):
        coords = self.clean.get_final_qubit_coordinates()
        data = next([t.value for t in op.targets_copy()] for op in self.clean if op.name == 'M')
        xchecks = set()
        for op in self.clean:
            if op.name == 'H':
                xchecks = {t.value for t in op.targets_copy()}
                break
        support = {q: set() for q in coords if q not in data}
        for op in self.clean:
            if op.name == 'MR':
                break
            if op.name == 'CX':
                targets = [t.value for t in op.targets_copy()]
                for a, b in zip(targets[::2], targets[1::2]):
                    ancilla, datum = (a, b) if a in support else (b, a)
                    support[ancilla].add(datum)
        return dict(data=[dict(id=q, coords=coords[q]) for q in data],
                    checks=[dict(id=q, coords=coords[q], basis='X' if q in xchecks else 'Z', support=sorted(s))
                            for q, s in support.items()],
                    detectors=[dict(id=d, coords=c) for d, c in self.clean.get_detector_coordinates().items()],
                    injection='Immediately after the first ancilla MR, before round 2 gates.',
                    code='Rotated surface code · d=3 · Z memory · 3 rounds',
                    edges=self.config['edges'])


def make_server(port=8765):
    model = Lab()
    lock = threading.Lock()
    assets = Path(__file__).with_name('web_assets')

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, content, mime='application/json'):
            body = json.dumps(content).encode() if mime == 'application/json' else content
            self.send_response(status)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/api/layout':
                self.reply(200, model.layout())
                return
            files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                     '/style.css': ('style.css', 'text/css')}
            if self.path not in files:
                self.reply(404, {'error': 'Not found'})
                return
            filename, mime = files[self.path]
            self.reply(200, (assets / filename).read_bytes(), mime)

        def do_POST(self):
            if self.path != '/api/simulate':
                self.reply(404, {'error': 'Not found'})
                return
            # There is no cross-origin API or filesystem access. Bound memory and
            # reject unsupported framing instead of waiting for a chunked body.
            if self.headers.get('Transfer-Encoding'):
                self.reply(400, {'error': 'Transfer-Encoding is not supported'})
                self.close_connection = True
                return
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                self.reply(403, {'error': 'Cross-origin requests are not allowed'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    self.reply(413 if length > 4096 else 400, {'error': 'Body must be 1 to 4096 bytes'})
                    self.close_connection = True
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {'errors'}:
                    raise ValueError('Expected an object containing only errors')
                with lock:
                    result = model.simulate(body['errors'])
                self.reply(200, result)
            except (ValueError, UnicodeDecodeError) as exc:
                self.reply(400, {'error': str(exc)})

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    server = make_server(args.port)
    print(f'QEC lab: http://127.0.0.1:{server.server_port} (software only)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

