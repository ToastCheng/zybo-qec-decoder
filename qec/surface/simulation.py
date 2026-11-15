"""Compile bounded Stim input and sample one annotated physical experiment."""

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import stim

from qec.surface.circuit import Capacities, _parse, compile_circuit
from qec.surface.decoder import decode
from qec.surface.host import GraphDecoder


def _prepare(settings):
    if not isinstance(settings, dict) or set(settings) - {"logical_circuit"} != {
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

    return str(noisy), None


def _mask(bits):
    return sum(int(bit) << i for i, bit in enumerate(bits))


def _compile_bounded(settings, capacities=None):
    """Run compilation in a serial-free worker with a 15-second deadline."""
    try:
        worker = subprocess.run(
            [sys.executable, "-m", "qec.surface.simulation", "--compile-worker"],
            check=False,
            input=json.dumps(
                {
                    "settings": settings,
                    "capacities": asdict(capacities) if capacities else None,
                }
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
    """Extract typed Stim targets without parsing display strings."""
    targets = []
    for t in op.targets_copy():
        if t.is_combiner:
            target = {"combiner": True}
        elif t.is_measurement_record_target:
            target = {"record": t.value}
        elif t.is_sweep_bit_target:
            target = {"sweep": t.value}
        else:
            target = {"qubit": t.qubit_value}
            for basis in "XYZ":
                if getattr(t, f"is_{basis.lower()}_target"):
                    target["pauli"] = basis
            if t.is_inverted_result_target:
                target["inverted"] = True
        targets.append(target)
    data = stim.gate_data(op.name)
    return {
        "name": op.name,
        "kind": (
            "pair"
            if data.is_two_qubit_gate
            else "single"
            if data.is_single_qubit_gate
            else "product"
        ),
        "targets": targets,
        "text": str(op),
    }


class CircuitExperiment:
    """Sample first, then upload the compiled graph for an explicit hardware run."""

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
                {
                    "tick": tick,
                    "operations": [str(op) for op in segment],
                    "diagram": [_diagram_operation(op) for op in segment],
                    "paulis": str(simulator.peek_pauli_flips(instance_index=0))[1:],
                    "detectors": simulator.get_detector_flips(
                        instance_index=0
                    ).tolist(),
                    "observables": simulator.get_observable_flips(
                        instance_index=0
                    ).tolist(),
                }
            )
        syndrome = _mask(simulator.get_detector_flips(instance_index=0))
        truth = _mask(simulator.get_observable_flips(instance_index=0))
        result = {
            "compiled": compiled,
            "trace": trace,
            "seed": settings["seed"],
            "syndrome": syndrome,
            "observable_truth": truth,
        }
        if self.serial_port:
            with GraphDecoder(self.serial_port) as board:
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
                        {
                            "opcode": t["opcode"],
                            "tx_hex": t["tx"].hex(),
                            "rx_hex": t["rx"].hex(),
                            "error": t.get("error"),
                        }
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


def main():
    parser = argparse.ArgumentParser(description="Bounded compiler worker")
    parser.add_argument("--compile-worker", action="store_true", required=True)
    parser.parse_args()
    try:
        request = json.load(sys.stdin)
        text, reference = _prepare(request["settings"])
        logical_text = request["settings"].get("logical_circuit")
        if logical_text is not None:
            logical = _parse(logical_text, Capacities())
            for op in logical.flattened():
                data = stim.gate_data(op.name)
                if (
                    data.is_noisy_gate
                    and not data.is_reset
                    and not data.produces_measurements
                    or data.produces_measurements
                    and any(op.gate_args_copy())
                ):
                    raise ValueError(
                        "logical_circuit must contain noiseless Clifford operations"
                    )
                if op.name in ("DETECTOR", "OBSERVABLE_INCLUDE"):
                    raise ValueError(
                        "logical_circuit is a Clifford display, not detector annotations"
                    )
        limits = Capacities(**request["capacities"]) if request["capacities"] else None
        output = compile_circuit(text, reference, limits)
        output.update(logical_circuit=logical_text, logical_mapping_verified=False)
    # The worker returns every compiler failure through its JSON error envelope.
    except Exception as exc:  # noqa: BLE001
        output = {"error": str(exc)}
    print(json.dumps(output))


if __name__ == "__main__":
    main()
