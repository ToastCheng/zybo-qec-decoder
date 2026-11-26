"""Run the fixed d3/r3 Z-memory vector suite on a connected Zybo Z7-10 over UART."""
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
    """UART host client for the 0xd303 fixed d3/r3 Z-memory matching bitstream."""

    def identity(self):
        """Query metadata, verify version 0xd303 (24/78/1), and return DecoderIdentity."""
        payload = self._transact(1)
        if len(payload) != 60:
            raise ProtocolError("matching identity width")
        words = struct.unpack("<15I", payload)
        if words[:4] != (0xD303, 24, 78, 1):
            raise ProtocolError("not the fixed d3/r3 exact matching image")
        if any(value > 65535 for value in words):
            raise ProtocolError("matching metadata range")
        # Map version 0xd303 to 2 so GraphDecoder's shared framing checks apply.
        return DecoderIdentity((2,) + words[1:])


def read_vectors(path, real_shots):
    """Parse board replay vectors and check the real vs synthetic shot split.

    Returns tuples of (syndrome, cost, matching_pred, uf_pred, error, truth).
    The first real_shots rows must carry binary truth (0/1); synthetic rows use -1.
    """
    lines = path.read_text().splitlines()
    if not lines or int(lines[0]) != len(lines) - 1 or not 0 < real_shots <= len(lines) - 1:
        raise ValueError("vector count / real population")
    rows = []
    for i, line in enumerate(lines[1:]):
        s, cost, exact, uf, error, truth = line.split()
        row = (int(s, 16), int(cost, 16), int(exact), int(uf), int(error), int(truth))
        if not 0 <= row[0] < (1 << 24) or row[4] != 0:
            raise ValueError("syndrome / decoder error")
        if row[-1] not in ((0, 1) if i < real_shots else (-1,)):
            raise ValueError("truth does not match real/diagnostic population")
        rows.append(row)
    return rows


def main():
    """Replay the frozen-graph vectors on the board and archive results and wire logs.

    Verifies graph.json's SHA-256, checks (for matching) that a tampered edge
    mask is rejected in PL, replays every shot verifying predictions and exact
    cycle counts, and writes wire.json even if an assertion fails.
    """
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--decoder", choices=("uf", "matching"), required=True)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", default="/dev/ttyUSB1")
    parser.add_argument("--real-shots", type=int, default=512)
    parser.add_argument("--matching-nonzero-cycles", type=int, default=512)
    args = parser.parse_args()
    graph_bytes = (HERE / "graph.json").read_bytes()
    assert hashlib.sha256(graph_bytes).hexdigest() == GRAPH_SHA256
    graph = json.loads(graph_bytes)
    edges = sorted((a, 24 if b is None else b, sum(1 << i for i in data["fault_ids"]))
                   for a, b, data in graph)
    vectors = read_vectors(args.vectors, args.real_shots)
    args.output.mkdir(parents=True, exist_ok=False)
    device = FixedMatching if args.decoder == "matching" else GraphDecoder
    rows = []
    with device(args.port, timeout=3) as board:
        try:
            initial = list(board.identity().words)
            if args.decoder == "matching":
                # Confirm the identity gate rejects a flipped observable mask and stays disarmed.
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
            for i, (s, cost, exact, uf, error, truth) in enumerate(vectors):
                reply = board.decode(s)
                expected = int(exact if args.decoder == "matching" else uf)
                assert reply.prediction == expected and not reply.decode_error
                if args.decoder == "matching":
                    assert reply.cycles == (1 if s == 0 else args.matching_nonzero_cycles)
                rows.append(dict(index=i, population="real" if i < args.real_shots else "uniform" if i < args.real_shots + 512 else "diagnostic",
                                 syndrome=s, prediction=reply.prediction, cycles=reply.cycles,
                                 truth=int(truth), expected_prediction=expected))
            final = list(board.identity().words)
            (args.output / "results.json").write_text(json.dumps(dict(
                decoder=args.decoder, graph_sha256=GRAPH_SHA256, initial=initial,
                loaded=loaded, final=final, real_shots=args.real_shots, shots=rows), indent=2) + "\n")
        finally:
            board.save_archive(args.output / "wire.json")
    print(json.dumps(dict(decoder=args.decoder, shots=len(rows),
                         cycles_min=min(r["cycles"] for r in rows),
                         cycles_max=max(r["cycles"] for r in rows))))


if __name__ == "__main__":
    main()
