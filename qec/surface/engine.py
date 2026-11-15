"""Connect editor experiments to graph loading and trace rendering."""

import stim

from qec.surface.host import GraphDecoder
from qec.surface.model import Lab
from qec.surface.simulation import CircuitExperiment


def _hardware(experiment):
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
    }


def _layout(circuit, source, logical=None):
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
        ticks[-1]["operations"].append({"name": op.name, "targets": targets})
        if op.name == "DETECTOR":
            detectors.append({"id": len(detectors), "available_tick": len(ticks) - 1})
    coords = circuit.get_final_qubit_coordinates()
    detector_coords = circuit.get_detector_coordinates()
    for detector in detectors:
        detector["coords"] = detector_coords.get(detector["id"], [])
    return {
        "kind": "circuit",
        "source": source,
        "protocol": "graph-v2",
        "ticks": ticks,
        "data": [{"id": q, "coords": coords.get(q, [])} for q in sorted(used)],
        "checks": [],
        "detectors": detectors,
        "code": "Annotated physical Clifford circuit",
        "circuit": str(circuit),
        "logical_circuit": logical,
        "mapping_verified": False,
        "mapping": "No logical-to-physical mapping supplied",
    }


class EditorLab:
    """Keep initial layout and rejected requests free of serial access."""

    def __init__(self, serial_port=None):
        self.serial_port = serial_port

    def layout(self):
        layout = Lab().layout()
        layout.update(
            protocol="graph-v2",
            source="FPGA" if self.serial_port else "Software",
            serial_configured=bool(self.serial_port),
            kind="memory",
            logical_circuit="R 0\nTICK\nI 0\nTICK\nM 0",
            mapping="Known encoded Z-memory experiment",
        )
        return layout

    def run(self, settings):
        model = Lab()
        experiment = {"source": "Software", "transactions": []}

        def measured(syndrome):
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
        layout = model.layout()
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
            "injected_circuit": experiment["compiled"]["circuit"],
        }
        return {"layout": layout, "result": result, "experiment": experiment}
