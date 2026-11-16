"""Fixed d=3 rotated-surface-code experiments, not a logical compiler.

Each patch has nine data and eight reusable extraction ancillas. Interpatch
CNOTs assume nonlocal, pairwise data-data couplers; they are not lattice surgery.
The four-layer hook-safe extraction schedule is Stim's rotated-memory schedule.
No S gadget is claimed: the Bell experiment is the ordinary (XX, ZZ) Bell state.
"""

import stim

# Stim's d=3 rotated layout, reindexed densely to 0..16 within each patch.
_SITES = (1, 2, 3, 5, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 25)
_DATA = (1, 3, 5, 8, 10, 12, 15, 17, 19)
_ANC = (2, 9, 11, 13, 14, 16, 18, 25)
_X_ANC = (2, 11, 16, 25)
_LAYERS = (
    (2, 3, 16, 17, 11, 12, 15, 14, 10, 9, 19, 18),
    (2, 1, 16, 15, 11, 10, 8, 14, 3, 9, 12, 18),
    (16, 10, 11, 5, 25, 19, 8, 9, 17, 18, 12, 13),
    (16, 8, 11, 3, 25, 17, 1, 9, 10, 18, 5, 13),
)


class _Experiment:
    def __init__(self, bases, noise, noise_model):
        if not 0 <= noise <= 0.75:
            raise ValueError("noise must be in [0, 0.75]")
        if noise_model not in ("phenomenological", "circuit_level"):
            raise ValueError("unknown noise_model")
        self.bases = bases
        self.noise = noise
        self.noise_model = noise_model
        self.gate_noise = noise if noise_model == "circuit_level" else 0
        self.circuit = stim.Circuit()
        self.records = 0
        self.time = 0
        self.previous = {}
        self.supports = {a: [] for a in _ANC}
        for layer in _LAYERS:
            for c, t in zip(layer[::2], layer[1::2]):
                a, d = (c, t) if c in _ANC else (t, c)
                self.supports[a].append(d)
        for patch, basis in enumerate(bases):
            for site in _SITES:
                # Same integer-lattice coordinates as Stim, tiled with a gap.
                x = site % 7
                y = 2 * (site // 7) + (site in _DATA)
                self.circuit.append(
                    "QUBIT_COORDS", [self.q(patch, site)], [x + 8 * patch, y]
                )
            data = [self.q(patch, s) for s in _DATA]
            anc = [self.q(patch, s) for s in _ANC]
            self.circuit.append("RX" if basis == "X" else "R", data)
            self.circuit.append("R", anc)
            if self.gate_noise:
                self.circuit.append(
                    "Z_ERROR" if basis == "X" else "X_ERROR", data, noise
                )
                self.circuit.append("X_ERROR", anc, noise)
            for a in _ANC:
                # The complementary checks are initially random, not detectors.
                self.previous[patch, a] = set() if self.basis(a) == basis else None
        self.circuit.append("TICK")

    @staticmethod
    def q(patch, site):
        return 17 * patch + _SITES.index(site)

    @staticmethod
    def basis(ancilla):
        return "X" if ancilla in _X_ANC else "Z"

    def detector(self, patch, ancilla, records):
        targets = [stim.target_rec(r - self.records) for r in sorted(records)]
        self.circuit.append(
            "DETECTOR",
            targets,
            [ancilla % 7 + 8 * patch, 2 * (ancilla // 7), self.time],
        )

    def extract(self, rounds=3):
        """Measure all eight checks, comparing to propagated previous signs."""
        for round_index in range(rounds):
            data = [self.q(p, d) for p in range(len(self.bases)) for d in _DATA]
            if self.noise_model == "phenomenological":
                # Separate CSS channels: Y is a two-fault event, not a single fault.
                self.circuit.append("X_ERROR", data, self.noise)
                self.circuit.append("Z_ERROR", data, self.noise)
            xs = [self.q(p, a) for p in range(len(self.bases)) for a in _X_ANC]
            self.circuit.append("H", xs)
            if self.gate_noise:
                self.circuit.append("DEPOLARIZE1", xs, self.gate_noise)
            self.circuit.append("TICK")
            for layer in _LAYERS:
                pairs = [self.q(p, s) for p in range(len(self.bases)) for s in layer]
                self.circuit.append("CX", pairs)
                if self.gate_noise:
                    self.circuit.append("DEPOLARIZE2", pairs, self.gate_noise)
                self.circuit.append("TICK")
            self.circuit.append("H", xs)
            if self.gate_noise:
                self.circuit.append("DEPOLARIZE1", xs, self.gate_noise)
            self.circuit.append("TICK")
            for patch in range(len(self.bases)):
                # Final check records must be exact before their CX fan-out.
                measurement_noise = (
                    self.noise if self.gate_noise or round_index < rounds - 1 else 0
                )
                self.circuit.append(
                    "MR", [self.q(patch, a) for a in _ANC], measurement_noise
                )
                start = self.records
                self.records += len(_ANC)
                for offset, a in enumerate(_ANC):
                    current = {start + offset}
                    previous = self.previous[patch, a]
                    if previous is not None:
                        self.detector(patch, a, current ^ previous)
                    self.previous[patch, a] = current
                if self.gate_noise:
                    self.circuit.append(
                        "X_ERROR", [self.q(patch, a) for a in _ANC], self.gate_noise
                    )
            if self.gate_noise:
                self.circuit.append("DEPOLARIZE1", data, self.gate_noise)
            self.circuit.append("TICK")
            self.time += 1

    def cx(self, control, target):
        pairs = [self.q(p, d) for d in _DATA for p in (control, target)]
        self.circuit.append("CX", pairs)
        if self.gate_noise:
            self.circuit.append("DEPOLARIZE2", pairs, self.gate_noise)
        # Individual check signs transform exactly like logical Paulis. Comparing
        # each patch only to itself here would produce nondeterministic checks.
        for a in _ANC:
            destination, source = (
                (control, target) if self.basis(a) == "X" else (target, control)
            )
            self.previous[destination, a] = (
                self.previous[destination, a] ^ self.previous[source, a]
            )
        self.circuit.append("TICK")

    def readout(self):
        for patch, basis in enumerate(self.bases):
            self.circuit.append(
                "MX" if basis == "X" else "M",
                [self.q(patch, d) for d in _DATA],
                self.noise,
            )
            data_records = {d: self.records + k for k, d in enumerate(_DATA)}
            self.records += len(_DATA)
            for a in _ANC:
                if self.basis(a) == basis:
                    self.detector(
                        patch,
                        a,
                        {data_records[d] for d in self.supports[a]}
                        ^ self.previous[patch, a],
                    )
            # X logical: left column; Z logical: top row in this orientation.
            logical = (1, 8, 15) if basis == "X" else (1, 3, 5)
            self.circuit.append(
                "OBSERVABLE_INCLUDE",
                [stim.target_rec(data_records[d] - self.records) for d in logical],
                patch,
            )
        return self.circuit


def examples(noise=0.001, noise_model="phenomenological"):
    """Return editor records: id, label, physical circuit, logical Stim metadata.

    A zero-noise request stays noiseless; callers needing a graph must explicitly
    request a compatible noisy reference, e.g. examples(noise=0.001).
    """
    bell = _Experiment(("X", "Z"), noise, noise_model)
    bell.extract()
    bell.cx(0, 1)
    bell.extract()
    # Destructive encoded Bell analyzer: CX then separate X/Z readouts.
    # These outcomes are the pre-analyzer commuting logical XX and ZZ parities.
    bell.cx(0, 1)
    bell.extract()
    echo = _Experiment(("X", "Z", "Z", "X", "Z", "Z"), noise, noise_model)
    echo.extract()
    for pairs in (
        ((0, 1), (3, 4)),
        ((1, 2), (4, 5)),
        ((1, 2), (4, 5)),
        ((0, 1), (3, 4)),
    ):
        for control, target in pairs:
            echo.cx(control, target)
        echo.extract()
    compatible = noise_model == "phenomenological"
    metadata = {
        "decoder_compatible": compatible,
        "noise_model_id": noise_model,
        "decoder_limitation": (
            "Graph compatible only under the restricted phenomenological model; unweighted decoding, not hardware fidelity."
            if compatible
            else "Correlated circuit-level CNOT faults are unsupported by the graph-only decoder."
        ),
        "noise_model": (
            "Restricted phenomenological CSS noise: independent X_ERROR(p) and Z_ERROR(p) on all data "
            "before every full extraction round. Measurement-result flips on rounds 1/2 and final readout. "
            "Round 3 results, resets, extraction gates and transversal CX are perfect. No storage faults "
            "between final extraction and CX. Not circuit-level depolarization or a hardware error model."
            if compatible
            else "Circuit-level depolarizing gates and data-idle noise; reset and measurement flips."
        ),
    }
    return [
        {
            "id": "phase_bell",
            "label": "Encoded Bell · 2 × d3 surface patches (34 qubits)",
            **metadata,
            "coupling_assumption": "Nonlocal pairwise transversal interpatch CX.",
            "circuit": str(bell.readout()),
            "semantic_adaptation": "Ordinary Bell with XX/ZZ correlations, not phase Bell with YX/ZZ; no encoded S gadget.",
            "logical_circuit": "R 0 1\nH 0\nCX 0 1\nTICK\nMPP X0*X1 Z0*Z1",
        },
        {
            "id": "two_repetition_echo",
            "label": "Encoded echo · 6 × d3 surface patches (102 qubits)",
            **metadata,
            "coupling_assumption": "Nonlocal pairwise transversal interpatch CX.",
            "circuit": str(echo.readout()),
            "semantic_adaptation": "S/S_DAG pair removed: final ideal echo is still identity, but intermediate GHZ phase is +1, not +i. Six patch observables replace two bare group observables.",
            "logical_circuit": "R 0 1 2 3 4 5\nH 0 3\nCX 0 1 3 4\nTICK\nCX 1 2 4 5\nTICK\nCX 1 2 4 5\nTICK\nCX 0 1 3 4\nMX 0 3\nM 1 2 4 5",
        },
    ]
