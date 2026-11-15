"""Validate annotated physical Clifford circuits and extract decoding graphs."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass

import stim

from qec.surface.graph import checked_graph


@dataclass(frozen=True)
class Capacities:
    max_detectors: int = 128
    max_edges: int = 512
    max_observables: int = 32
    max_qubits: int = 1024
    max_bytes: int = 262144
    max_expanded_bytes: int = 2097152
    max_instructions: int = 20000
    max_targets: int = 100000
    max_repeat: int = 1024
    max_depth: int = 16
    max_work: int = 20000000


def _preflight(text, limits):
    """Bound source size and expanded work before Stim parses the input."""
    if not isinstance(text, str):
        # Callers use ValueError for all rejected circuit input.
        raise ValueError("preflight requires circuit text")  # noqa: TRY004
    if len(text) > limits.max_bytes or len(text.encode("utf-8")) > limits.max_bytes:
        raise ValueError("resource limit: source bytes")

    source = re.sub(r"(?m)(^[ \t]*[A-Za-z_][A-Za-z_0-9]*)\[[^\]\n]*\]", r"\1", text)
    source = re.sub(r"#[^\n]*", "", source)
    stack, multiplier = [], 1
    instructions = targets = expanded_bytes = qubits = 0
    pending = None
    for part in re.split(r"([{}\n;])", source):
        part = part.strip()
        if not part or part in ("\n", ";"):
            continue
        if part == "{":
            if pending is None or len(stack) >= limits.max_depth:
                raise ValueError("preflight invalid repeat or depth resource limit")
            stack.append(pending)
            multiplier *= pending
            pending = None
            continue
        if part == "}":
            if not stack or pending is not None:
                raise ValueError("preflight unmatched repeat")
            multiplier //= stack.pop()
            continue
        if pending is not None:
            raise ValueError("preflight expected repeat block")
        repeat = re.fullmatch(r"REPEAT\s+(\d+)", part, re.IGNORECASE)
        if repeat:
            if len(repeat[1]) > 10 or not 1 <= int(repeat[1]) <= limits.max_repeat:
                raise ValueError("resource limit: repeat count")
            pending = int(repeat[1])
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*)(?:\(([^()]*)\))?\s*(.*)", part)
        if not match:
            raise ValueError("preflight invalid instruction")
        name, args, tail = match.groups()
        if name.upper() == "OBSERVABLE_INCLUDE" and (
            not args
            or not args.isdigit()
            or len(args) > 10
            or int(args) >= limits.max_observables
        ):
            raise ValueError("resource limit: observable index")

        records = re.findall(r"(?:rec|sweep)\[(-?\d+)\]", tail)
        if any(
            len(t.lstrip("-")) > 10 or abs(int(t)) > limits.max_targets for t in records
        ):
            raise ValueError("resource limit: record index")
        physical = re.sub(r"(?:rec|sweep)\[-?\d+\]", "", tail)
        indices = re.findall(r"\d+", physical)
        for token in indices:
            if len(token) > 10 or int(token) >= limits.max_qubits:
                raise ValueError("resource limit: qubit index")
            if name.upper() != "MPAD":
                qubits = max(qubits, int(token) + 1)
        instructions += multiplier
        targets += multiplier * max(1, len(records) + len(indices) + tail.count("*"))
        expanded_bytes += multiplier * (len(part) + 1)
        if (
            instructions > limits.max_instructions
            or targets > limits.max_targets
            or expanded_bytes > limits.max_expanded_bytes
            or qubits * instructions > limits.max_work
        ):
            raise ValueError("resource limit: expanded circuit work")
    if stack or pending is not None:
        raise ValueError("preflight unclosed repeat")


def _parse(text, limits):
    _preflight(text, limits)
    circuit = stim.Circuit(text)
    if (
        circuit.num_qubits > limits.max_qubits
        or circuit.num_detectors > limits.max_detectors
        or circuit.num_observables > limits.max_observables
    ):
        raise ValueError("resource limit: circuit dimensions")

    for instruction in circuit.flattened():
        if instruction.name not in ("DETECTOR", "OBSERVABLE_INCLUDE") and any(
            t.is_measurement_record_target or t.is_sweep_bit_target
            for t in instruction.targets_copy()
        ):
            raise ValueError("adaptive feedback and sweep controls unsupported")
    return circuit


def compile_circuit(text, reference_text=None, capacities=None):
    """Validate deterministic annotations and return graph, circuit and provenance metadata."""
    limits = Capacities() if capacities is None else capacities
    if not isinstance(limits, Capacities) or any(
        type(v) is not int or v < 1 for v in asdict(limits).values()
    ):
        raise ValueError("resource capacities must be positive integers")
    if limits.max_observables > 32 or limits.max_detectors > 65535:
        raise ValueError("resource capacities exceed wire endpoint/mask widths")
    circuit = _parse(text, limits)
    ideal = circuit.without_noise()

    ideal.detector_error_model(allow_gauge_detectors=False)
    dem = circuit.detector_error_model(decompose_errors=True)
    reference = circuit if reference_text is None else _parse(reference_text, limits)
    if reference.without_noise().flattened() != ideal.flattened():
        raise ValueError(
            "reference circuit must have compatible identical noiseless operations and annotations"
        )
    reference_dem = reference.detector_error_model(decompose_errors=True)

    # Ignore zero-probability terms before checking graph signatures.
    active = stim.DetectorErrorModel()
    for instruction in reference_dem.flattened():
        if instruction.type != "error" or instruction.args_copy()[0] != 0:
            active.append(instruction)
    edges, _ = checked_graph(active, circuit.num_detectors, circuit.num_observables)
    if not edges:
        raise ValueError(
            "no nonzero graph: provide an explicit compatible noisy reference circuit"
        )
    if len(edges) > limits.max_edges:
        raise ValueError("resource limit: graph edges")

    actual_edges, _ = checked_graph(dem, circuit.num_detectors, circuit.num_observables)
    if not set(actual_edges).issubset(set(edges)):
        raise ValueError(
            "reference graph does not cover actual circuit fault signatures"
        )
    operations, detectors = [], []
    tick = measurements = 0
    flat = circuit.flattened()
    for instruction in flat:
        targets = instruction.targets_copy()
        operations.append(
            {
                "name": instruction.name,
                "tick": tick,
                "stim": str(instruction),
                "measurement_start": measurements,
                "measurement_count": instruction.num_measurements,
                "targets": [str(t) for t in targets],
                "args": instruction.gate_args_copy(),
            }
        )
        if instruction.name == "DETECTOR":
            detectors.append(
                {
                    "index": len(detectors),
                    "tick": tick,
                    "available_after_operation": len(operations) - 1,
                    "measurements": [measurements + t.value for t in targets],
                    "coordinates": instruction.gate_args_copy(),
                }
            )
        measurements += instruction.num_measurements
        tick += instruction.name == "TICK"
    graph = {
        "detectors": circuit.num_detectors,
        "observables": circuit.num_observables,
        "edges": [list(e) for e in edges],
        "boundary_vertex": circuit.num_detectors,
    }
    result = {
        "schema_version": 1,
        "circuit": str(circuit),
        "ideal": str(ideal),
        "dem": str(dem),
        "reference_dem": str(reference_dem),
        "reference_circuit": str(reference),
        "capacities": asdict(limits),
        "edges": graph["edges"],
        "boundary_vertex": circuit.num_detectors,
        "counts": {
            "qubits": circuit.num_qubits,
            "detectors": circuit.num_detectors,
            "observables": circuit.num_observables,
            "edges": len(edges),
            "measurements": measurements,
            "ticks": tick,
        },
        "layout": {
            "qubits": {
                str(k): v for k, v in circuit.get_final_qubit_coordinates().items()
            }
        },
        "operations": operations,
        "detectors": detectors,
        "stim_version": stim.__version__,
    }
    result["sha256"] = {
        name: hashlib.sha256(result[name].encode()).hexdigest()
        for name in ("circuit", "ideal", "dem", "reference_dem", "reference_circuit")
    }
    result["sha256"]["graph"] = hashlib.sha256(
        json.dumps(graph, sort_keys=True).encode()
    ).hexdigest()
    result["detector_order"] = "Stim detector index, little-endian"
    result["observable_order"] = "bit i = Stim observable L_i"
    result["limitations"] = [
        "Physical detector-annotated circuit acceptance, not logical-to-fault-tolerant QEC synthesis",
        "Unweighted runtime graph; not weighted MWPM equivalence",
        "Separator correlations remain in DEM; independent-edge approximation in graph",
        "Software compilation only; no hardware acceptance or adaptive feedback",
    ]
    return result
