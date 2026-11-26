"""Coordinate circuit layouts, presets, and software or FPGA runs for the web UI.

This module adapts both ``Lab`` (generated rotated Z-memory experiments) and
``CircuitExperiment`` (arbitrary annotated Stim circuits) into the common layout,
trace, and hardware-telemetry structures consumed by ``web.py`` and the browser
frontend.
"""

import stim

from qec.surface.host import GraphDecoder
from qec.surface.model import Lab
from qec.surface.simulation import CircuitExperiment


def _hardware(experiment):
    """Package FPGA run telemetry for the UI, or return ``None`` for software runs.

    Extracts the wire bytes of the final decode frame (opcode 5) along with the
    full UART transaction log and per-window chunk breakdown. ``cycles`` is the
    sum of FPGA core decode cycles across windows and excludes graph uploads and
    UART transfer time.
    """
    if experiment["source"] != "FPGA":
        return None
    transaction = next(
        t for t in reversed(experiment["transactions"]) if t["opcode"] == 5
    )
    return {
        "prediction": experiment["prediction"],
        "cycles": experiment["cycles"],
        "tx_hex": transaction["tx_hex"],
        "rx_hex": transaction["rx_hex"],
        "protocol": "graph-v2",
        "transactions": experiment["transactions"],
        "chunks": experiment.get("hardware_chunks", []),
        "cycle_scope": "sum of per-window FPGA core cycles; excludes uploads and UART",
    }


def _checks(circuit):
    """Extract reusable stabilizer ancillas and their data-qubit supports.

    Finds ancillas as qubits that appear in both ``R`` and ``MR``, classifies X
    checks from the initial ``H`` gates before the first ``MR``, and collects
    each ancilla's data neighbors from ``CX`` pairs. Call this only on
    recognized surface-code circuits (generated Z-memory or matched encoded
    presets), since arbitrary Stim circuits do not necessarily follow this
    stabilizer pattern.
    """
    operations = list(circuit.flattened())
    ancillas = {
        t.qubit_value
        for op in operations
        if op.name == "MR"
        for t in op.targets_copy()
        if t.is_qubit_target
    }
    reset = {
        t.qubit_value
        for op in operations
        if op.name == "R"
        for t in op.targets_copy()
        if t.is_qubit_target
    }
    ancillas &= reset
    supports = {q: set() for q in ancillas}
    xs = set()
    for op in operations:
        if op.name == "MR":
            break
        if op.name == "H":
            xs.update(t.qubit_value for t in op.targets_copy())
    for op in operations:
        if op.name != "CX":
            continue
        targets = op.targets_copy()
        for a, b in zip(targets[::2], targets[1::2]):
            if not (a.is_qubit_target and b.is_qubit_target):
                continue
            a, b = a.qubit_value, b.qubit_value
            if (a in ancillas) != (b in ancillas):
                ancilla, data = (a, b) if a in ancillas else (b, a)
                supports[ancilla].add(data)
    coords = circuit.get_final_qubit_coordinates()
    return [
        {
            "id": q,
            "coords": coords.get(q, []),
            "basis": "X" if q in xs else "Z",
            "support": sorted(supports[q]),
        }
        for q in sorted(ancillas)
    ]


def _detector_grid(layout):
    """Assign each detector to a ``(row, boundary)`` cell for the UI grid.

    Rows match stabilizer checks by 2D spatial coordinate when available (falling
    back to raw coordinates or ``D<id>``). Columns ("boundaries") group
    detectors by measurement round using their time coordinate ``coords[2:]``
    when present, or ``available_tick`` otherwise, so final data readout and
    ancilla measurements that share a physical tick stay in separate columns.
    """
    checks = {
        tuple(q["coords"][:2]): q for q in layout["checks"] if len(q["coords"]) >= 2
    }
    rows = {
        str(q["id"]): {"id": str(q["id"]), "label": f"{q['basis']}{q['id']}"}
        for q in layout["checks"]
    }
    boundaries = {}
    for detector in layout["detectors"]:
        coords = detector["coords"]
        check = checks.get(tuple(coords[:2])) if len(coords) >= 2 else None
        if check is not None:
            row_id = str(check["id"])
            label = f"{check['basis']}{check['id']}"
        elif coords:
            spatial = coords[:2]
            row_id = "coords:" + ",".join(format(c, "g") for c in spatial)
            label = "(" + ", ".join(format(c, "g") for c in spatial) + ")"
        else:
            row_id = label = f"D{detector['id']}"
        rows.setdefault(row_id, {"id": row_id, "label": label})
        detector["row"] = row_id
        # Prefer the detector's time coordinate over its tick index: final data
        # readout and the last ancilla round can land on the same tick even
        # though they belong to different measurement rounds.
        key = (
            ("time", *coords[2:])
            if len(coords) >= 3
            else ("tick", detector["available_tick"])
        )
        if key not in boundaries:
            index = len(boundaries)
            boundaries[key] = {
                "id": index,
                "label": f"r{index}",
                "available_tick": detector["available_tick"],
            }
        boundary = boundaries[key]
        boundary["available_tick"] = max(
            boundary["available_tick"], detector["available_tick"]
        )
        detector["boundary"] = boundary["id"]
    layout.update(rows=list(rows.values()), boundaries=list(boundaries.values()))
    return layout


def _memory_layout(model):
    """Add check supports, mapping metadata, and a detector grid to ``model.layout()``."""
    layout = model.layout()
    layout.update(
        checks=_checks(model.clean),
        mapping_verified=True,
        mapping="Known encoded Z-memory experiment",
    )
    return _detector_grid(layout)


def _layout(circuit, source, logical=None):
    """Build UI layout metadata from a Stim circuit without running a simulation.

    Extracts per-tick operations with typed targets, qubit and detector
    coordinates, and detector grid placement. If ``logical`` is supplied and
    matches one of the known presets in ``encoded.examples()`` (along with the
    noise-stripped physical circuit), populates stabilizer check supports and
    sets ``mapping_verified=True``; otherwise treats all qubits as generic data
    qubits and leaves the mapping unverified.
    """
    ticks = [{"id": 0, "operations": []}]
    used = set()
    detectors = []
    for op in circuit.flattened():
        if op.name == "TICK":
            ticks.append({"id": len(ticks), "operations": []})
            continue
        targets = [
            t.qubit_value
            for t in op.targets_copy()
            if not (
                t.is_combiner or t.is_measurement_record_target or t.is_sweep_bit_target
            )
        ]
        used.update(targets)
        typed_targets = []
        for target in op.targets_copy():
            if target.is_combiner:
                typed_targets.append({"type": "combiner"})
                continue
            kind = "qubit"
            if target.is_measurement_record_target:
                kind = "rec"
            elif target.is_sweep_bit_target:
                kind = "sweep"
            elif target.is_x_target:
                kind = "X"
            elif target.is_y_target:
                kind = "Y"
            elif target.is_z_target:
                kind = "Z"
            detail = {"type": kind, "value": target.value}
            if target.is_inverted_result_target:
                detail["inverted"] = True
            typed_targets.append(detail)
        ticks[-1]["operations"].append(
            {
                "name": op.name,
                "targets": targets,
                "typed_targets": typed_targets,
                "args": op.gate_args_copy(),
            }
        )
        if op.name == "DETECTOR":
            detectors.append({"id": len(detectors), "available_tick": len(ticks) - 1})
    coords = circuit.get_final_qubit_coordinates()
    detector_coords = circuit.get_detector_coordinates()
    for detector in detectors:
        detector["coords"] = detector_coords.get(detector["id"], [])
    from qec.surface.encoded import examples

    matched = None
    if logical:
        physical = circuit.without_noise()
        logical_circuit = stim.Circuit(logical)
        for entry in examples():
            if physical == stim.Circuit(
                entry["circuit"]
            ).without_noise() and logical_circuit == stim.Circuit(
                entry["logical_circuit"]
            ):
                matched = entry
                break
    checks = _checks(circuit) if matched else []
    check_ids = {check["id"] for check in checks}
    layout = {
        "kind": "circuit",
        "source": source,
        "protocol": "graph-v2",
        "ticks": ticks,
        "data": [
            {"id": q, "coords": coords.get(q, [])} for q in sorted(used - check_ids)
        ],
        "checks": checks,
        "detectors": detectors,
        "code": "Annotated physical Clifford circuit",
        "circuit": str(circuit),
        "logical_circuit": logical,
        "mapping_verified": False,
        "mapping": "No logical-to-physical mapping supplied",
    }
    if matched:
        layout.update(
            mapping_verified=True,
            encoded_example=matched["id"],
            mapping=matched["label"],
            code=matched["label"],
            noise_model=matched.get("noise_model"),
            semantic_adaptation=matched.get("semantic_adaptation"),
        )
    return _detector_grid(layout)


class EditorLab:
    """Facade used by the HTTP server to serve layouts and run experiments.

    Keeps initial layout requests and rejected inputs free of serial I/O by
    opening the FPGA UART only when an actual run executes.
    """

    def __init__(self, serial_port=None):
        """Store an optional FPGA UART device path without opening it."""
        self.serial_port = serial_port

    def layout(self):
        """Return the default Z-memory layout and encoded preset previews without serial I/O."""
        from qec.surface.encoded import examples

        model = Lab()
        layout = _memory_layout(model)
        layout.update(
            circuit=str(model.clean),
            reference_circuit=model.reference,
            examples=[
                dict(
                    entry,
                    layout=_layout(
                        stim.Circuit(entry["circuit"]),
                        "FPGA" if self.serial_port else "Software",
                        entry["logical_circuit"],
                    ),
                )
                for entry in examples()
            ],
            protocol="graph-v2",
            source="FPGA" if self.serial_port else "Software",
            serial_configured=bool(self.serial_port),
            kind="memory",
            logical_circuit="R 0\nTICK\nI 0\nTICK\nM 0",
            mapping="Known encoded Z-memory experiment",
        )
        return layout

    def run(self, settings):
        """Run a generated Z-memory shot and return its layout, trace, and decode data.

        Uses the FPGA when ``serial_port`` is configured, uploading the shot's
        compiled graph before decoding; otherwise runs the software decoder.
        Any physical correction returned in the payload is a host-computed
        representative rather than an output of the FPGA decoder.
        """
        model = Lab()
        experiment = {"source": "Software", "transactions": []}

        def measured(syndrome):
            """Upload the shot's graph to the FPGA, decode ``syndrome``, and log UART frames."""
            compiled = model.compiled
            with GraphDecoder(self.serial_port) as board:
                identity = board.identity()
                counts = compiled["counts"]
                if (
                    counts["detectors"] > identity.max_detectors
                    or counts["edges"] > identity.max_edges
                    or counts["observables"] > identity.max_observables
                ):
                    raise ValueError("Experiment exceeds FPGA capacities")
                loaded = board.load_graph(
                    counts["detectors"], compiled["edges"], counts["observables"]
                )
                answer = board.decode(syndrome)
                experiment.update(
                    source="FPGA",
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
            return _hardware(experiment)

        if self.serial_port:
            model.decoder = measured
        result = model.run(settings)
        experiment.update(
            compiled=model.compiled,
            trace=result["trace"],
            syndrome=result["syndrome"],
            observable_truth=result["observable"],
            prediction=result["prediction"],
        )
        layout = _memory_layout(model)
        layout.update(
            protocol="graph-v2",
            kind="memory",
            source=result["source"],
            logical_circuit="R 0\nTICK\nI 0\nTICK\nM 0",
        )
        result.update(
            experiment=experiment,
            layout=layout,
            protocol="graph-v2",
            correction_provenance="host representative, not FPGA correction",
        )
        return result

    def circuit_run(self, settings):
        """Run an arbitrary annotated Stim circuit and format its trace for the UI.

        Delegates compilation, simulation, and decoding to ``CircuitExperiment``,
        then reshapes the tick trace and layout to match ``run()``. Physical
        correction and residual fields are left empty because host GF(2)
        correction overlays are only computed for the fixed Z-memory lab.
        """
        experiment = CircuitExperiment(self.serial_port).run(settings)
        layout = _layout(
            stim.Circuit(experiment["compiled"]["circuit"]),
            experiment["source"],
            experiment["compiled"].get("logical_circuit"),
        )
        trace = [
            {
                "tick": t["tick"],
                "operations": t["operations"],
                "pauli_frame": {
                    str(q): p for q, p in enumerate(t["paulis"]) if p != "_"
                },
                "detector_indices": [i for i, bit in enumerate(t["detectors"]) if bit],
            }
            for t in experiment["trace"]
        ]
        result = {
            "trace": trace,
            "detector_indices": trace[-1]["detector_indices"],
            "syndrome": experiment["syndrome"],
            "observable": experiment["observable_truth"],
            "prediction": experiment["prediction"],
            "hardware": _hardware(experiment),
            "source": experiment["source"],
            "host_frame": experiment["prediction"],
            "logical_success": experiment["prediction"]
            == experiment["observable_truth"],
            "correction": None,
            "correction_frame": {},
            "residual_syndrome": None,
            "residual_observable": None,
            "injected_circuit": experiment["injected_circuit"],
        }
        return {"layout": layout, "result": result, "experiment": experiment}
