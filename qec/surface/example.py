"""Inspect one simulated surface-code shot; optionally send it to the board.

Run from the repository root: python -m qec.surface.example [--port PORT].
See the root README for setup, protocols and board-loading requirements.
"""

import argparse
import json
from pathlib import Path

import pymatching
import stim

from qec.surface.decoder import decode, graph
from qec.surface.host import parse, request


def main():
    """Inspect a candidate batch, decode its first nonzero syndrome, and optionally validate one board reply."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--circuit", action="store_true", help="print the full Stim circuit only"
    )
    parser.add_argument(
        "--port", help="send this same shot to a loaded d3 Z surface image"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Stim sampling seed (default: fresh randomness)",
    )
    parser.add_argument(
        "--shots",
        type=int,
        default=256,
        help="number of candidate shots to sample; decode one (default: 256)",
    )
    parser.add_argument(
        "--noise",
        type=float,
        default=0.001,
        help="error probability at each noise location, 0 to 0.75 inclusive (default: 0.001)",
    )
    args = parser.parse_args()
    if not 0 <= args.noise <= 0.75:
        parser.error("--noise must be between 0 and 0.75 (inclusive)")
    if args.shots < 1:
        parser.error("--shots must be positive")
    if args.seed is not None and not 0 <= args.seed < 2**64:
        parser.error("--seed must fit an unsigned 64-bit integer")
    config = json.loads(Path("qec/surface/graphs/d3_z_r3.json").read_text())
    circuit_text = config["circuit"]
    if args.noise != config["noise"]:
        circuit_text = graph(
            distance=config["distance"],
            rounds=config["rounds"],
            basis=config["basis"],
            noise=args.noise,
        )["circuit"]
    circuit = stim.Circuit(circuit_text)
    if args.circuit:
        print(circuit)
        return

    detectors, observables = circuit.compile_detector_sampler(seed=args.seed).sample(
        args.shots, separate_observables=True
    )
    # Prefer a visible detection event, but preserve the actual all-zero shot if none occurred.
    index = next((i for i, row in enumerate(detectors) if row.any()), 0)
    bits = detectors[index]
    syndrome = sum(int(bit) << i for i, bit in enumerate(bits))
    result = decode(config["detectors"], config["edges"], syndrome)
    assert not result["error"]
    residual = syndrome
    for edge in result["correction_edges"]:
        a, b, _ = config["edges"][edge]
        residual ^= 1 << a
        if b < config["detectors"]:
            residual ^= 1 << b
    assert residual == 0
    matching = pymatching.Matching.from_detector_error_model(
        circuit.detector_error_model(decompose_errors=True)
    )
    matching.ensure_num_fault_ids(circuit.num_observables)
    seq = 0
    tx = request(seq, syndrome)
    window = dict(
        shot=index,
        detector_indices=[i for i, bit in enumerate(bits) if bit],
        syndrome=syndrome,
        observable=int(observables[index, 0]),
        prediction=result["prediction"],
        pymatching=int(matching.decode(bits)[0]),
        correction_edges=result["correction_edges"],
        residual=residual,
        logical_error=result["prediction"] != int(observables[index, 0]),
        tx_hex=tx.hex(" "),
    )
    if args.port:
        import serial

        with serial.Serial(args.port, 115200, timeout=1, write_timeout=1) as port:
            port.reset_input_buffer()
            assert port.write(tx) == len(tx)
            rx = port.read(9)
        prediction, cycles = parse(rx, seq)
        window.update(rx_hex=rx.hex(" "), board_prediction=prediction, pl_cycles=cycles)
        assert prediction == result["prediction"], "FPGA/reference mismatch"
        assert cycles > 0
    print(json.dumps(window, indent=2))


if __name__ == "__main__":
    main()
