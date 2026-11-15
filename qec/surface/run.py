"""Compile, sample and archive annotated circuit decoding runs."""

import argparse
import hashlib
import json
import platform
from contextlib import ExitStack
from pathlib import Path

import stim

from qec.surface.circuit import Capacities, compile_circuit
from qec.surface.decoder import decode
from qec.surface.host import GraphDecoder


def _write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def run_circuit(
    text,
    *,
    reference_text=None,
    shots=128,
    seed=123,
    port=None,
    out=None,
    decoder_factory=GraphDecoder,
):
    """Compile and upload once, then record sampled shots and measured replies."""
    if type(shots) is not int or not 1 <= shots <= 4096:
        raise ValueError("shots must be an integer in 1..4096")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    compiled = compile_circuit(text, reference_text=reference_text)
    destination = Path(out) if out is not None else None
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=False)
    source = "FPGA" if port is not None else "Software"
    board = None
    completed = 0
    failures = 0
    mismatches = 0
    try:
        with ExitStack() as stack:
            if port is not None:
                board = stack.enter_context(decoder_factory(port))
                identity = board.identity()
                capacities = Capacities(
                    max_detectors=identity.max_detectors,
                    max_edges=identity.max_edges,
                    max_observables=identity.max_observables,
                )
                compiled = compile_circuit(
                    text, reference_text=reference_text, capacities=capacities
                )
                board.load_graph(
                    compiled["counts"]["detectors"],
                    compiled["edges"],
                    compiled["counts"]["observables"],
                )
            if destination is not None:
                _write_json(destination / "circuit.json", compiled)
                rows = stack.enter_context((destination / "shots.jsonl").open("x"))
            else:
                rows = None
            circuit = stim.Circuit(compiled["circuit"])
            detectors, observables = circuit.compile_detector_sampler(seed=seed).sample(
                shots, separate_observables=True
            )
            for index, (detector_bits, observable_bits) in enumerate(
                zip(detectors, observables)
            ):
                syndrome = sum(int(bit) << i for i, bit in enumerate(detector_bits))
                observable = sum(int(bit) << i for i, bit in enumerate(observable_bits))
                reference = decode(circuit.num_detectors, compiled["edges"], syndrome)
                if board is not None:
                    answer = board.decode(syndrome)
                    if (
                        answer.decode_error
                        or answer.cycles <= 0
                        or not 0 <= answer.prediction < 2**circuit.num_observables
                    ):
                        raise OSError(
                            "FPGA returned invalid prediction/cycles/decode_error"
                        )
                    prediction, cycles = answer.prediction, answer.cycles
                else:
                    if reference["error"]:
                        raise ValueError(
                            "Software reference could not resolve syndrome"
                        )
                    prediction, cycles = reference["prediction"], None
                logical_error = prediction != observable
                mismatch = prediction != reference["prediction"] or bool(
                    reference["error"]
                )
                row = {
                    "shot": index,
                    "syndrome": syndrome,
                    "observable": observable,
                    "prediction": prediction,
                    "cycles": cycles,
                    "source": source,
                    "reference_prediction": reference["prediction"],
                    "reference_decode_error": bool(reference["error"]),
                    "reference_mismatch": mismatch,
                    "logical_error": logical_error,
                }
                if rows is not None:
                    rows.write(json.dumps(row) + "\n")
                    rows.flush()
                completed += 1
                failures += logical_error
                mismatches += mismatch
        summary = dict(
            source=source,
            shots=completed,
            seed=seed,
            **compiled["counts"],
            logical_failures=failures,
            reference_mismatches=mismatches,
            graph_sha256=compiled["sha256"]["graph"],
        )
        if destination is not None:
            if board is not None:
                board.save_archive(destination / "wire.json")
            hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in destination.iterdir()
                if path.is_file()
            }
            _write_json(
                destination / "manifest.json",
                {
                    "schema_version": 1,
                    "source": source,
                    "seed": seed,
                    "shots": shots,
                    "stim_version": stim.__version__,
                    "python": platform.python_version(),
                    "machine": platform.machine(),
                    "files": hashes,
                    "timing_scope": "FPGA acceptance to result cycles; excludes host, UART and graph upload",
                    "limitations": compiled["limitations"],
                },
            )
            _write_json(destination / "summary.json", summary)
        return summary
    except Exception as exc:
        if destination is not None:
            if board is not None:
                board.save_archive(destination / "wire.json")
            _write_json(
                destination / "error.json",
                {
                    "source": source,
                    "completed_shots": completed,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("circuit", type=Path)
    parser.add_argument(
        "--reference",
        type=Path,
        help="explicit compatible noisy reference for an empty/zero-noise graph",
    )
    parser.add_argument("--shots", type=int, default=128)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--port", help="UART of an already loaded runtime image")
    parser.add_argument(
        "--out", type=Path, help="fresh archive directory; never overwritten"
    )
    args = parser.parse_args()
    result = run_circuit(
        args.circuit.read_text(),
        reference_text=args.reference.read_text() if args.reference else None,
        shots=args.shots,
        seed=args.seed,
        port=args.port,
        out=args.out,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
