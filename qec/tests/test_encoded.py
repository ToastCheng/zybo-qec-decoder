"""Executable contracts for the two protected, fixed logical experiments."""

import importlib.util

import pytest
import stim


def _prefix_before_interpatch_cx(circuit, occurrence):
    prefix = stim.Circuit()
    seen = 0
    for instruction in circuit.without_noise():
        targets = instruction.targets_copy()
        if instruction.name == "CX" and any(
            a.value // 17 != b.value // 17 for a, b in zip(targets[::2], targets[1::2])
        ):
            seen += 1
            if seen == occurrence:
                return prefix
        prefix.append(instruction)
    raise AssertionError("missing encoded interpatch CX")


def _logical_product(basis, patches):
    # Dense data positions of Stim's left-column X and top-row Z strings.
    support = (0, 4, 11) if basis == "X" else (0, 2, 3)
    return "*".join(f"{basis}{17 * p + d}" for p in patches for d in support)


def test_intermediate_encoded_bell_and_ghz_correlations():
    from qec.surface.encoded import examples

    bell, echo = examples()
    bell_prefix = _prefix_before_interpatch_cx(stim.Circuit(bell["circuit"]), 2)
    bell_prefix += stim.Circuit(
        "MPP " + _logical_product("X", (0, 1)) + " " + _logical_product("Z", (0, 1))
    )
    assert not bell_prefix.compile_sampler(seed=9).sample(128)[:, -2:].any()

    echo_prefix = _prefix_before_interpatch_cx(stim.Circuit(echo["circuit"]), 5)
    correlations = []
    for group in ((0, 1, 2), (3, 4, 5)):
        correlations += [_logical_product("X", group)]
        correlations += [
            _logical_product("Z", group[:2]),
            _logical_product("Z", group[1:]),
        ]
    echo_prefix += stim.Circuit("MPP " + " ".join(correlations))
    assert not echo_prefix.compile_sampler(seed=10).sample(128)[:, -6:].any()


@pytest.mark.parametrize("noise_model", ["phenomenological", "circuit_level"])
def test_every_single_fault_has_unique_correctable_signature(noise_model):
    from qec.surface.encoded import examples

    for entry in examples(noise_model=noise_model):
        circuit = stim.Circuit(entry["circuit"])
        signatures = {}
        raw_dem = circuit.detector_error_model(decompose_errors=False)
        for instruction in raw_dem.flattened():
            if instruction.type != "error":
                continue
            targets = instruction.targets_copy()
            detectors = tuple(t.val for t in targets if t.is_relative_detector_id())
            mask = sum(1 << t.val for t in targets if t.is_logical_observable_id())
            assert detectors or not mask, "undetected single-fault logical error"
            assert signatures.setdefault(detectors, mask) == mask, (
                "two single faults have identical syndrome but different logical effects"
            )
        assert len(signatures) > (300 if noise_model == "phenomenological" else 1000)
        # Graphlike distance is a diagnostic, not certification of a hypergraph
        # decoder. The raw-signature injectivity above is the single-fault check.
        assert len(circuit.shortest_graphlike_error()) == 3


@pytest.mark.parametrize("noise", [-0.001, 0.751])
def test_invalid_noise_rejected(noise):
    from qec.surface.encoded import examples

    with pytest.raises(ValueError, match="noise"):
        examples(noise=noise)


def test_checked_in_encoded_files_match_generator():
    from pathlib import Path

    from qec.surface.encoded import examples

    directory = Path(__file__).parents[1] / "examples"
    for entry in examples():
        assert stim.Circuit(
            (directory / (entry["id"] + ".stim")).read_text()
        ) == stim.Circuit(entry["circuit"])


def test_zero_noise_keeps_same_ideal_circuit_and_no_faults():
    from qec.surface.encoded import examples

    for quiet, noisy in zip(examples(noise=0), examples(noise=0.001)):
        c, reference = stim.Circuit(quiet["circuit"]), stim.Circuit(noisy["circuit"])
        assert c.without_noise() == reference.without_noise()
        assert c.detector_error_model().num_errors == 0


def test_encoded_bell_uses_two_complete_patches():
    assert importlib.util.find_spec("qec.surface.encoded") is not None, (
        "missing encoded surface-code experiment generator"
    )
    import stim

    from qec.surface.encoded import examples

    bell = examples()[0]
    circuit = stim.Circuit(bell["circuit"])
    assert circuit.num_qubits == 34
    assert len(circuit.get_final_qubit_coordinates()) == 34
    assert circuit.num_observables == 2
    assert circuit.num_detectors >= 80
    assert not any(i.name == "MPP" for i in circuit.flattened())
    circuit.without_noise().detector_error_model()
    dets, obs = (
        circuit.without_noise()
        .compile_detector_sampler(seed=17)
        .sample(128, separate_observables=True)
    )
    assert not dets.any()
    assert not obs.any()


def test_echo_protects_all_six_logical_qubits():
    import stim

    from qec.surface.encoded import examples

    entries = examples()
    assert len(entries) == 2, "missing protected six-logical-qubit echo"
    echo = entries[1]
    circuit = stim.Circuit(echo["circuit"])
    assert circuit.num_qubits == 102
    assert len(circuit.get_final_qubit_coordinates()) == 102
    assert circuit.num_observables == 6
    assert "S" not in {i.name for i in circuit.flattened()}
    assert echo["logical_circuit"].count("CX") == 4
    circuit.without_noise().detector_error_model()
    dets, obs = (
        circuit.without_noise()
        .compile_detector_sampler(seed=29)
        .sample(128, separate_observables=True)
    )
    assert not dets.any()
    assert not obs.any()


def test_default_raw_faults_exactly_match_compiled_graph():
    import numpy as np
    import pymatching

    from qec.surface.circuit import Capacities, compile_circuit
    from qec.surface.decoder import decode
    from qec.surface.encoded import examples

    entries = examples()
    assert [e["id"] for e in entries] == ["phase_bell", "two_repetition_echo"]
    for entry in entries:
        assert entry["decoder_compatible"] is True
        assert entry["noise_model_id"] == "phenomenological"
        circuit = stim.Circuit(entry["circuit"])
        compiled = compile_circuit(
            entry["circuit"], capacities=Capacities(max_detectors=1024, max_edges=8192)
        )
        graph = {tuple(edge) for edge in compiled["edges"]}
        raw = circuit.detector_error_model(decompose_errors=False)
        matching = pymatching.Matching()
        for a, b, mask in graph:
            faults = {i for i in range(circuit.num_observables) if mask >> i & 1}
            if b == circuit.num_detectors:
                matching.add_boundary_edge(a, fault_ids=faults, weight=1)
            else:
                matching.add_edge(a, b, fault_ids=faults, weight=1)
        matching.ensure_num_fault_ids(circuit.num_observables)
        raw_edges = set()
        for op in raw.flattened():
            if op.type != "error":
                continue
            targets = op.targets_copy()
            assert not any(t.is_separator() for t in targets)
            ds = sorted(t.val for t in targets if t.is_relative_detector_id())
            mask = sum(1 << t.val for t in targets if t.is_logical_observable_id())
            assert 1 <= len(ds) <= 2
            edge = tuple(ds + ([circuit.num_detectors] if len(ds) == 1 else [])) + (
                mask,
            )
            raw_edges.add(edge)
            syndrome = np.zeros(circuit.num_detectors, dtype=np.uint8)
            syndrome[ds] = 1
            prediction = matching.decode(syndrome)
            assert sum(int(bit) << i for i, bit in enumerate(prediction)) == mask
            syndrome_mask = sum(1 << detector for detector in ds)
            uf = decode(circuit.num_detectors, compiled["edges"], syndrome_mask)
            assert not uf["error"] and uf["prediction"] == mask
        assert graph == raw_edges


def test_circuit_level_mode_remains_explicit_and_fails_closed():
    from qec.surface.circuit import Capacities, compile_circuit
    from qec.surface.encoded import examples

    for entry in examples(noise_model="circuit_level"):
        assert entry["decoder_compatible"] is False
        assert entry["noise_model_id"] == "circuit_level"
        with pytest.raises(ValueError, match="detectorless logical component"):
            compile_circuit(
                entry["circuit"],
                capacities=Capacities(max_detectors=1024, max_edges=8192),
            )


def test_phenomenological_noise_scope_and_perfect_gate_boundaries():
    from qec.surface.encoded import examples

    for entry in examples():
        circuit = stim.Circuit(entry["circuit"])
        assert not {"DEPOLARIZE1", "DEPOLARIZE2"} & {op.name for op in circuit}
        for patch in range(circuit.num_qubits // 17):
            measurements = [
                op
                for op in circuit
                if op.name == "MR" and op.targets_copy()[0].value // 17 == patch
            ]
            assert len(measurements) % 3 == 0
            assert [op.gate_args_copy()[0] for op in measurements] == [
                0.001,
                0.001,
                0.0,
            ] * (len(measurements) // 3)


def test_unknown_noise_model_is_rejected():
    from qec.surface.encoded import examples

    with pytest.raises(ValueError, match="noise_model"):
        examples(noise_model="invented")


def test_noisy_final_check_records_would_break_raw_graphlikeness():
    """Guard the physical reason for the explicitly perfect boundary records."""
    from qec.surface.encoded import examples

    bell = stim.Circuit(examples()[0]["circuit"])
    extended = stim.Circuit()
    for op in bell:
        if op.name == "MR":
            extended.append("MR", op.targets_copy(), 0.001)
        else:
            extended.append(op)
    raw = extended.detector_error_model(decompose_errors=False)
    assert any(
        sum(t.is_relative_detector_id() for t in op.targets_copy()) > 2
        for op in raw.flattened()
        if op.type == "error"
    )


def test_default_examples_execute_real_editor_simulation_path():
    from qec.surface.encoded import examples
    from qec.surface.simulation import CircuitExperiment

    for entry in examples():
        result = CircuitExperiment().run(
            {
                "circuit": entry["circuit"],
                "reference": None,
                "seed": 42,
                "added_noise": 0,
                "logical_circuit": entry["logical_circuit"],
            }
        )
        assert result["source"] == "Software"
        assert result["prediction"] == result["observable_truth"]
        assert result["compiled"]["counts"]["qubits"] in (34, 102)
        assert len(result["trace"]) == result["compiled"]["counts"]["ticks"] + 1


def test_patch_extraction_uses_surface_geometry():
    import stim

    from qec.surface.encoded import examples

    for entry in examples():
        circuit = stim.Circuit(entry["circuit"])
        coords = circuit.get_final_qubit_coordinates()
        for instruction in circuit:
            if instruction.name != "CX":
                continue
            targets = instruction.targets_copy()
            for c, t in zip(targets[::2], targets[1::2]):
                if c.value // 17 != t.value // 17:
                    continue  # Explicitly nonlocal transversal interpatch gate.
                a, b = coords[c.value], coords[t.value]
                assert abs(a[0] - b[0]) == abs(a[1] - b[1]) == 1
