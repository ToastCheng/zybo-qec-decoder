"""Capture real UART transactions; no software decoder participates in decisions."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from qec.surface.host import GraphDecoder, DecoderIdentity, ProtocolError

HERE = Path(__file__).parent
GRAPH_SHA256 = "612138bcfd40ea7e4aae8e706215afc00944fe6811d1b4d3f951b9f747e22524"


class FixedMatching(GraphDecoder):
    """Opt in to the immutable graph; normal UF host rejects this protocol."""

    def identity(self):
        payload = self._transact(1)
        if len(payload) != 60:
            raise ProtocolError("matching identity width")
        words = struct.unpack("<15I", payload)
        if words[:4] != (0xD303, 24, 78, 1):
            raise ProtocolError("not the fixed d3/r3 exact matching image")
        if any(value > 65535 for value in words):
            raise ProtocolError("matching metadata range")
        # Existing framing/generation checks are reused only after explicit opt-in.
        return DecoderIdentity((2,) + words[1:])


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--decoder", choices=("uf", "matching"), required=True)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", default="/dev/ttyUSB1")
    args = parser.parse_args()
    graph_bytes = (HERE / "graph.json").read_bytes()
    assert hashlib.sha256(graph_bytes).hexdigest() == GRAPH_SHA256
    graph = json.loads(graph_bytes)
    edges = sorted((a, 24 if b is None else b, sum(1 << i for i in data["fault_ids"]))
                   for a, b, data in graph)
    lines = args.vectors.read_text().splitlines()
    assert int(lines[0]) == len(lines) - 1 == 1050
    args.output.mkdir(parents=True, exist_ok=False)
    device = FixedMatching if args.decoder == "matching" else GraphDecoder
    rows = []
    with device(args.port, timeout=3) as board:
        try:
            initial = list(board.identity().words)
            if args.decoder == "matching":
                # Same-size wrong mask must fail in PL and leave decoding disarmed.
                wrong = list(edges)
                a, b, m = wrong[10]
                wrong[10] = (a, b, m ^ 1)
                try:
                    board.load_graph(24, wrong, 1)
                except ProtocolError as exc:
                    assert exc.status is not None
                else:
                    raise AssertionError("matching accepted a different graph")
                assert not board.identity().valid
            loaded = list(board.load_graph(24, edges, 1).words)
            for i, line in enumerate(lines[1:]):
                syndrome, cost, exact, uf, error, truth = line.split()
                s = int(syndrome, 16)
                reply = board.decode(s)
                expected = int(exact if args.decoder == "matching" else uf)
                assert reply.prediction == expected and not reply.decode_error
                if args.decoder == "matching":
                    assert reply.cycles == 9826
                rows.append(dict(index=i, population="real" if i < 512 else "uniform" if i < 1024 else "diagnostic",
                                 syndrome=s, prediction=reply.prediction, cycles=reply.cycles,
                                 truth=int(truth), expected_prediction=expected))
            final = list(board.identity().words)
            (args.output / "results.json").write_text(json.dumps(dict(
                decoder=args.decoder, graph_sha256=GRAPH_SHA256, initial=initial,
                loaded=loaded, final=final, shots=rows), indent=2) + "\n")
        finally:
            board.save_archive(args.output / "wire.json")
    print(json.dumps(dict(decoder=args.decoder, shots=len(rows),
                         cycles_min=min(r["cycles"] for r in rows),
                         cycles_max=max(r["cycles"] for r in rows))))


if __name__ == "__main__":
    main()
