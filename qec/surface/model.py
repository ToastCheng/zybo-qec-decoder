"""Sample generated Z-memory shots and verify host counterfactual corrections."""

from functools import lru_cache

import stim

from qec.surface.decoder import decode


class Lab:
    """Sample Z-memory faults and independently replay host correction representatives."""

    def __init__(self, decoder=None):
        self.decoder = decoder
        self.configure("surface_code:rotated_memory_z", 3, 3)

    def configure(self, generator, distance, rounds):
        self._signature.cache_clear()
        self._basis.cache_clear()
        self.clean = stim.Circuit.generated(
            generator, distance=distance, rounds=rounds
        ).flattened()
        self.generator, self.distance, self.rounds = generator, distance, rounds
        reference = stim.Circuit.generated(
            generator,
            distance=distance,
            rounds=rounds,
            after_clifford_depolarization=0.001,
        ).flattened()
        self.reference = str(reference)
        from qec.surface.circuit import compile_circuit

        self.compiled = compile_circuit(str(self.clean), self.reference)
        self.config = {
            "detectors": self.clean.num_detectors,
            "edges": self.compiled["edges"],
        }

    def run(self, settings):
        if not isinstance(settings, dict) or set(settings) != {
            "circuit",
            "distance",
            "rounds",
            "noise",
            "seed",
            "faults",
        }:
            raise ValueError(
                "Expected circuit, distance, rounds, noise, seed and faults"
            )
        if (
            settings["circuit"] != "surface_code:rotated_memory_z"
            or type(settings["distance"]) is not int
            or not 3 <= settings["distance"] <= 7
            or settings["distance"] % 2 == 0
            or type(settings["rounds"]) is not int
            or not 1 <= settings["rounds"] <= 8
        ):
            raise ValueError(
                "Expected rotated Z memory, odd distance 3..7 and rounds 1..8"
            )
        if type(settings["seed"]) is not int or not 0 <= settings["seed"] <= 2**53 - 1:
            raise ValueError("seed must be an unsigned safe integer (0..2^53-1)")
        noise = settings["noise"]
        if not isinstance(noise, dict) or set(noise) != {
            "after_clifford_depolarization",
            "before_round_data_depolarization",
            "before_measure_flip_probability",
            "after_reset_flip_probability",
        }:
            raise ValueError(
                "noise must contain exactly the four supported Stim noise rates"
            )
        if any(
            type(p) not in (int, float) or not 0 <= p <= 0.75 for p in noise.values()
        ):
            raise ValueError("noise rates must be finite nonboolean numbers in 0..0.75")
        self.configure(settings["circuit"], settings["distance"], settings["rounds"])
        self._validate_faults(settings["faults"])
        circuit = stim.Circuit.generated(
            settings["circuit"],
            distance=settings["distance"],
            rounds=settings["rounds"],
            **settings["noise"],
        ).flattened()
        faults = settings["faults"]

        simulator = stim.FlipSimulator(
            batch_size=1,
            num_qubits=circuit.num_qubits,
            seed=settings["seed"],
            disable_stabilizer_randomization=True,
        )
        segments = [stim.Circuit()]
        for op in circuit:
            if op.name == "TICK":
                segments.append(stim.Circuit())
            else:
                segments[-1].append(op)
        injected = stim.Circuit()
        frozen = stim.Circuit()
        trace = []
        events = []
        noise_ops = {"DEPOLARIZE1", "DEPOLARIZE2", "X_ERROR", "Y_ERROR", "Z_ERROR"}
        operation_index = 0
        for tick, segment in enumerate(segments):
            if tick:
                injected.append("TICK")
                frozen.append("TICK")
            for fault in faults:
                if fault["tick"] == tick:
                    op = stim.CircuitInstruction(
                        fault["pauli"] + "_ERROR", [fault["qubit"]], [1]
                    )
                    simulator.do(op)
                    injected.append(op)
                    frozen.append(op)
            for op in segment:
                injected.append(op)
                before = (
                    simulator.peek_pauli_flips(instance_index=0)
                    if op.name in noise_ops
                    else None
                )
                simulator.do(op)
                if before is not None:
                    after = simulator.peek_pauli_flips(instance_index=0)
                    for qubit in range(circuit.num_qubits):
                        pauli = before[qubit] ^ after[qubit]
                        if pauli:
                            label = "_XYZ"[pauli]
                            events.append(
                                {
                                    "tick": tick,
                                    "operation_index": operation_index,
                                    "operation": op.name,
                                    "qubit": qubit,
                                    "pauli": label,
                                }
                            )
                            frozen.append(label + "_ERROR", [qubit], 1)
                else:
                    frozen.append(op)
                operation_index += 1
            frame = simulator.peek_pauli_flips(instance_index=0)
            bits = simulator.get_detector_flips(instance_index=0)
            trace.append(
                {
                    "tick": tick,
                    "operations": str(segment),
                    "pauli_frame": {
                        str(q): "_XYZ"[frame[q]] for q in range(len(frame)) if frame[q]
                    },
                    "faults": [f for f in faults if f["tick"] <= tick],
                    "detector_indices": [i for i, bit in enumerate(bits) if bit],
                }
            )
        bits = simulator.get_detector_flips(instance_index=0)
        syndrome = sum(int(bit) << i for i, bit in enumerate(bits))
        observable = int(simulator.get_observable_flips(instance_index=0)[0])
        if self._sample(frozen) != (syndrome, observable):
            raise OSError("Sampled noise replay did not reproduce the original shot")
        from qec.surface.circuit import compile_circuit

        self.compiled = compile_circuit(
            str(injected), None if any(noise.values()) else self.reference
        )
        self.config = {
            "detectors": self.clean.num_detectors,
            "edges": self.compiled["edges"],
        }
        result = decode(self.config["detectors"], self.config["edges"], syndrome)
        reference_prediction = result["prediction"]
        hardware = self.decoder(syndrome) if self.decoder is not None else None
        if self.decoder is not None and (
            not isinstance(hardware, dict)
            or type(hardware.get("prediction")) is not int
            or hardware["prediction"] not in (0, 1)
            or type(hardware.get("cycles")) is not int
            or hardware["cycles"] <= 0
        ):
            raise OSError("Invalid FPGA decoder result")
        if hardware is not None:
            result["prediction"] = hardware["prediction"]

        correction = self._correction(
            [{"tick": t} for t in range(len(segments))], syndrome, result["prediction"]
        )
        replay = None
        rs = ro = None
        if correction is not None:
            replay = stim.Circuit()
            tick = 0
            for op in frozen:
                if op.name == "TICK":
                    tick += 1
                if op.name == "TICK" or len(replay) == 0:
                    if op.name == "TICK":
                        replay.append(op)
                    for fault in correction:
                        if fault["tick"] == tick:
                            replay.append(
                                fault["pauli"] + "_ERROR", [fault["qubit"]], 1
                            )
                    if op.name == "TICK":
                        continue
                replay.append(op)
            rs, ro = self._sample(replay)
            if rs != 0 or ro != observable ^ result["prediction"]:
                correction = replay = None
                rs = ro = None
        return dict(
            result,
            settings=settings,
            syndrome=syndrome,
            observable=observable,
            detector_indices=trace[-1]["detector_indices"],
            trace=trace,
            source="FPGA" if hardware is not None else "Software",
            hardware=hardware,
            reference_prediction=reference_prediction,
            host_frame=result["prediction"],
            logical_success=observable == result["prediction"] and not result["error"],
            injected_circuit=str(injected),
            sampled_circuit=str(frozen),
            sampled_noise={
                "events": events,
                "simulator": "stim.FlipSimulator",
                "stim_version": stim.__version__,
                "seed": settings["seed"],
                "stabilizer_randomization": False,
                "provenance": "Actual per-operation sampled Pauli deltas; explicit faults excluded",
            },
            correction=correction,
            correction_status=(
                "verified_counterfactual" if correction is not None else "unavailable"
            ),
            corrected_circuit=str(replay) if replay is not None else None,
            correction_frame=(
                self._pauli_trace(correction)[-1] if correction is not None else {}
            ),
            residual_syndrome=rs,
            residual_observable=ro,
        )

    def _segments(self):
        segments = [stim.Circuit()]
        for op in self.clean:
            if op.name == "TICK":
                segments.append(stim.Circuit())
            else:
                segments[-1].append(op)
        return segments

    def _fault_circuit(self, faults):
        circuit = stim.Circuit()
        for tick, segment in enumerate(self._segments()):
            if tick:
                circuit.append("TICK")
            for fault in faults:
                if fault["tick"] == tick:
                    circuit.append(fault["pauli"] + "_ERROR", [fault["qubit"]], 1)
            circuit += segment
        return circuit

    # Bounded shared caches retain instances until eviction; configure clears both.
    @lru_cache(maxsize=512)  # noqa: B019
    def _signature(self, tick, qubit, pauli):
        """Pack detector bits below observable bits for one simulated fault."""
        s, o = self._sample(
            self._fault_circuit([{"tick": tick, "qubit": qubit, "pauli": pauli}])
        )
        return s | (o << self.clean.num_detectors)

    @lru_cache(maxsize=8)  # noqa: B019 - Bounded and cleared on configure, like _signature.
    def _basis(self, ticks):
        """Build a GF(2) basis of fault signatures and their physical representatives."""
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
        """Find a same-tick representative matching detectors and logical prediction."""

        value = syndrome | (prediction << self.clean.num_detectors)
        frame = frozenset()
        basis = self._basis(tuple(sorted({f["tick"] for f in faults})))
        while value:
            pivot = value.bit_length() - 1
            if pivot not in basis:
                return None
            row, other = basis[pivot]
            value ^= row
            frame = frame ^ other
        return [{"tick": t, "qubit": q, "pauli": p} for t, q, p in sorted(frame)]

    def _pauli_trace(self, faults):
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

    def _validate_faults(self, faults):
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

    def simulate_faults(self, faults):
        self._validate_faults(faults)
        injected = self._fault_circuit(faults)
        syndrome, observable = self._sample(injected)
        result = decode(self.config["detectors"], self.config["edges"], syndrome)
        indices = [i for i in range(self.clean.num_detectors) if syndrome >> i & 1]
        detectors = self.layout()["detectors"]
        trace = []
        frames = self._pauli_trace(faults)
        for tick, segment in enumerate(self._segments()):
            trace.append(
                {
                    "tick": tick,
                    "operations": str(segment),
                    "pauli_frame": frames[tick],
                    "faults": [f for f in faults if f["tick"] <= tick],
                    "detector_indices": [
                        i for i in indices if detectors[i]["available_tick"] <= tick
                    ],
                }
            )
        hardware = self.decoder(syndrome) if self.decoder is not None else None
        if self.decoder is not None and (
            not isinstance(hardware, dict)
            or type(hardware.get("prediction")) is not int
            or hardware["prediction"] not in (0, 1)
            or type(hardware.get("cycles")) is not int
            or hardware["cycles"] <= 0
        ):
            raise OSError("Invalid FPGA decoder result")
        reference_prediction = result["prediction"]
        if hardware:
            result["prediction"] = hardware["prediction"]
        correction = self._correction(faults, syndrome, result["prediction"])

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
            correction_frame=(
                self._pauli_trace(correction)[-1] if correction is not None else {}
            ),
            residual_syndrome=rs,
            residual_observable=ro,
            detector_indices=indices,
            trace=trace,
            source="FPGA" if hardware else "Software",
            hardware=hardware,
            reference_prediction=reference_prediction,
            host_frame=result["prediction"],
            logical_success=observable == result["prediction"] and not result["error"],
            injected_circuit=str(injected),
        )

    @staticmethod
    def _sample(circuit):
        """Sample a deterministic fault circuit and pack detector and observable bits."""
        bits, obs = circuit.compile_detector_sampler(seed=0).sample(
            1, separate_observables=True
        )
        return sum(int(b) << i for i, b in enumerate(bits[0])), int(obs[0, 0])

    def layout(self):
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
            {
                "id": tick,
                "operations": [
                    {
                        "name": op.name,
                        "targets": [
                            t.value for t in op.targets_copy() if t.is_qubit_target
                        ],
                    }
                    for op in segment
                    if op.name in ("R", "H", "CX", "MR", "M")
                ],
            }
            for tick, segment in enumerate(self._segments())
        ]
        return {
            "source": "FPGA" if self.decoder else "Software",
            "ticks": ticks,
            "data": [{"id": q, "coords": coords[q]} for q in data],
            "checks": [
                {
                    "id": q,
                    "coords": coords[q],
                    "basis": "X" if q in xchecks else "Z",
                    "support": sorted(s),
                }
                for q, s in support.items()
            ],
            "detectors": [
                {"id": d, "coords": c, "available_tick": availability[d]}
                for d, c in self.clean.get_detector_coordinates().items()
            ],
            "supported_circuits": [
                {
                    "circuit": "surface_code:rotated_memory_z",
                    "distance": self.distance,
                    "rounds": self.rounds,
                    "graph": "Compiled on Run",
                    "detectors": self.clean.num_detectors,
                    "observables": 1,
                    "limitation": "Host representative correction; runtime graph loading",
                }
            ],
            "run_defaults": {
                "circuit": "surface_code:rotated_memory_z",
                "distance": 3,
                "rounds": 3,
                "noise": dict.fromkeys(
                    (
                        "after_clifford_depolarization",
                        "before_round_data_depolarization",
                        "before_measure_flip_probability",
                        "after_reset_flip_probability",
                    ),
                    0.001,
                ),
                "seed": 1,
                "faults": [],
            },
            "injection": "Before selected tick operations",
            "code": f"Rotated surface code · d={self.distance} · Z memory · {self.rounds} rounds",
            "edges": self.config["edges"],
        }
