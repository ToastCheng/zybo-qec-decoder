import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pymatching
import pytest
import stim


@pytest.mark.parametrize(
    "name,qubits,detectors,edges",
    [
        ("phase_bell", 2, 2, 2),
        ("two_repetition_echo", 6, 4, 6),
    ],
)
def test_examples_real_stim_and_matching(name, qubits, detectors, edges):
    from qec.surface.circuit import compile_circuit

    text = (Path(__file__).parent / "fixtures" / ("bare_" + name + ".stim")).read_text()
    b = compile_circuit(text)
    assert b["counts"]["qubits"] == qubits
    assert b["counts"]["detectors"] == detectors
    assert b["counts"]["edges"] == edges
    assert b["counts"]["observables"] == 2
    d0, o0 = (
        stim.Circuit(b["ideal"])
        .compile_detector_sampler(seed=5)
        .sample(100, separate_observables=True)
    )
    assert not d0.any() and not o0.any()
    d, o = (
        stim.Circuit(text)
        .compile_detector_sampler(seed=5)
        .sample(1000, separate_observables=True)
    )
    matcher = pymatching.Matching.from_detector_error_model(
        stim.DetectorErrorModel(b["dem"])
    )
    predicted = matcher.decode_batch(d)
    assert predicted.shape == o.shape == (1000, 2)
    assert d.any() and o.any()
    if name == "phase_bell":
        assert np.array_equal(predicted, o)


def test_reference_required_and_compatible():
    from qec.surface.circuit import compile_circuit

    ideal = str(stim.Circuit(basic()).without_noise())
    with pytest.raises(ValueError, match="reference"):
        compile_circuit(ideal)
    bundle = compile_circuit(ideal, reference_text=basic())
    assert bundle["edges"] == [[0, 1, 3]]
    assert "error" not in bundle["dem"]
    assert "error" in bundle["reference_dem"]
    with pytest.raises(ValueError, match="compatible"):
        compile_circuit(ideal, reference_text=basic().replace("S 0", "H 0"))


def test_preflight_rejects_before_stim_parse(monkeypatch):
    from qec.surface import circuit as rc

    limits = rc.Capacities()

    def forbidden(*args, **kwargs):
        pytest.fail("Stim parsed rejected resource input")

    monkeypatch.setattr(rc.stim, "Circuit", forbidden)
    for text, cap in [
        ("R 999999999", limits),
        ("REPEAT 999999999 { R 0 }", limits),
        ("REPEAT 100 { REPEAT 100 { M 0 } }", replace(limits, max_instructions=50)),
        ("R 0\n" * 100, replace(limits, max_bytes=20)),
        ("{" * 100, limits),
        ("OBSERVABLE_INCLUDE(99999999) rec[-1]", limits),
        ("M 0\n" * 100, replace(limits, max_targets=20)),
    ]:
        with pytest.raises(ValueError, match="resource|preflight"):
            rc.compile_circuit(text, capacities=cap)


@pytest.mark.parametrize(
    "circuit",
    [
        "R 0\nH 0\nM 0\nDETECTOR rec[-1]",
        "R 0\nH 0\nM 0\nOBSERVABLE_INCLUDE(0) rec[-1]",
    ],
)
def test_nondeterministic_annotations_rejected(circuit):
    from qec.surface.circuit import compile_circuit

    with pytest.raises(ValueError, match="deterministic"):
        compile_circuit(circuit)


@pytest.mark.parametrize(
    "circuit, message",
    [
        ("R 0\nX_ERROR(0.1) 0\nM 0\nOBSERVABLE_INCLUDE(0) rec[-1]", "detectorless"),
        (
            "R 0 1\nX_ERROR(0.1) 0\nX_ERROR(0.1) 1\nM 0 1\nDETECTOR rec[-1] rec[-2]\nOBSERVABLE_INCLUDE(0) rec[-1]",
            "ambiguous",
        ),
        (
            "R 0 1 2\nCORRELATED_ERROR(0.1) X0 X1 X2\nM 0 1 2\nDETECTOR rec[-1]\nDETECTOR rec[-2]\nDETECTOR rec[-3]",
            "graphlike|decompos",
        ),
    ],
)
def test_unrepresentable_noise_rejected(circuit, message):
    from qec.surface.circuit import compile_circuit

    with pytest.raises(ValueError, match=message):
        compile_circuit(circuit)


def test_capacity_and_zero_probability_terms():
    from qec.surface.circuit import Capacities, compile_circuit

    with pytest.raises(ValueError, match="resource"):
        compile_circuit(basic(), capacities=replace(Capacities(), max_observables=1))

    circuit = "R 0 1\nX_ERROR(0) 1\nX_ERROR(0.1) 0\nM 0 1\nDETECTOR rec[-1] rec[-2]\nOBSERVABLE_INCLUDE(0) rec[-2]"
    assert compile_circuit(circuit)["edges"] == [[0, 1, 1]]


def test_reference_cannot_drop_actual_faults():
    from qec.surface.circuit import compile_circuit

    actual = "R 0 1\nX_ERROR(0.1) 0 1\nM 0 1\nDETECTOR rec[-2]\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(0) rec[-2]"
    reference = actual.replace("X_ERROR(0.1) 0 1", "X_ERROR(0.1) 0")
    with pytest.raises(ValueError, match="reference.*cover"):
        compile_circuit(actual, reference_text=reference)


def test_repeat_detector_order_and_shifted_coordinates():
    from qec.surface.circuit import compile_circuit

    text = """R 0
REPEAT 3 {
X_ERROR(0.01) 0
M 0
DETECTOR(0, 0) rec[-1]
R 0
SHIFT_COORDS(0, 1)
TICK
}
OBSERVABLE_INCLUDE(0) rec[-1]
"""
    b = compile_circuit(text)
    assert [d["measurements"] for d in b["detectors"]] == [[0], [1], [2]]
    assert [d["coordinates"] for d in b["detectors"]] == [[0, 0], [0, 1], [0, 2]]
    assert [d["tick"] for d in b["detectors"]] == [0, 1, 2]
    assert b["edges"] == [[0, 3, 0], [1, 3, 0], [2, 3, 1]]


def test_real_decomposition_archived_and_multibit_32():
    from qec.surface.circuit import compile_circuit

    text = """R 0 1 2 3
X_ERROR(0.01) 0 1 2 3
CORRELATED_ERROR(0.02) X0 X1 X2 X3
M 0 1 2 3
DETECTOR rec[-4]
DETECTOR rec[-3]
DETECTOR rec[-2]
DETECTOR rec[-1]
OBSERVABLE_INCLUDE(31) rec[-4]
"""
    b = compile_circuit(text)
    assert "^" in b["dem"]
    assert b["counts"]["observables"] == 32
    assert b["edges"][0] == [0, 4, 1 << 31]
    assert b["sha256"]["circuit"] != b["sha256"]["ideal"]


@pytest.mark.parametrize(
    "text",
    [
        "R 0\nM 0\nCX rec[-1] 0",
        "R 0\nCX sweep[0] 0",
    ],
)
def test_feedback_not_claimed(text):
    from qec.surface.circuit import compile_circuit

    with pytest.raises(ValueError, match="unsupported"):
        compile_circuit(text)


def test_record_lookback_is_not_a_physical_qubit_index():
    from qec.surface.circuit import compile_circuit

    text = (
        "R 0\nX_ERROR(0.1) 0\nM 0\nMPAD "
        + "0 " * 2048
        + "\nDETECTOR rec[-2049]\nOBSERVABLE_INCLUDE(0) rec[-2049]"
    )
    b = compile_circuit(text)
    assert b["counts"]["qubits"] == 1
    assert b["detectors"][0]["measurements"] == [0]


def test_expanded_target_budget_catches_mpp_products(monkeypatch):
    from qec.surface import circuit as rc

    def forbidden(*args, **kwargs):
        pytest.fail("expanded MPP targets reached Stim")

    monkeypatch.setattr(rc.stim, "Circuit", forbidden)
    with pytest.raises(ValueError, match="resource"):
        rc.compile_circuit(
            "MPP " + "*".join("X0" for _ in range(50)),
            capacities=replace(rc.Capacities(), max_targets=20),
        )


def basic():
    return """QUBIT_COORDS(0, 0) 0
R 0 1
H 0
S 0
CX 0 1
CX 0 1
S_DAG 0
H 0
TICK
X_ERROR(0.01) 0
M 0 1
DETECTOR(0, 0) rec[-2]
OBSERVABLE_INCLUDE(0) rec[-2]
OBSERVABLE_INCLUDE(1) rec[-2]
"""


def test_general_composition_preserves_multibit_mask_and_metadata():
    from qec.surface.circuit import compile_circuit

    bundle = compile_circuit(basic())
    assert bundle["edges"] == [[0, 1, 3]]
    assert bundle["counts"]["qubits"] == 2
    assert bundle["counts"]["observables"] == 2
    assert bundle["detectors"][0]["measurements"] == [0]
    assert bundle["detectors"][0]["tick"] == 1
    assert bundle["layout"]["qubits"] == {"0": [0.0, 0.0]}
    assert bundle["operations"][0]["stim"] == "QUBIT_COORDS(0, 0) 0"
    assert bundle["operations"][-4]["measurement_start"] == 0
    assert bundle["operations"][-4]["measurement_count"] == 2
    assert bundle["stim_version"] == stim.__version__
    assert "S 0" in bundle["ideal"]
    assert json.loads(json.dumps(bundle)) == bundle
    assert len(bundle["sha256"]["graph"]) == 64
