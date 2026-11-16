"""Replay custom-circuit injections without replacing the decoder graph."""

import pytest
import stim

from qec.surface.simulation import CircuitExperiment


def settings(faults):
    return {
        "circuit": "R 0\nTICK\nX_ERROR(0.01) 0\nM 0\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(0) rec[-1]",
        "reference": None,
        "seed": 1,
        "added_noise": 0,
        "faults": faults,
    }


def test_custom_injection_uses_same_shot_and_preserves_graph():
    lab = CircuitExperiment()
    base = lab.run(settings([]))
    result = lab.run(settings([{"tick": 1, "qubit": 0, "pauli": "X"}]))
    assert result["compiled"]["edges"] == base["compiled"]["edges"]
    assert result["syndrome"] == result["observable_truth"] == 1
    assert result["prediction"] == 1
    assert result["trace"][0]["paulis"] == "_"
    assert result["trace"][1]["paulis"] == "X"
    assert "X_ERROR(1) 0" in result["injected_circuit"]
    frozen = stim.Circuit(result["injected_circuit"])
    assert frozen.num_detectors == 1


@pytest.mark.parametrize(
    "faults",
    [
        None,
        [{}],
        [{"tick": True, "qubit": 0, "pauli": "X"}],
        [{"tick": 2, "qubit": 0, "pauli": "X"}],
        [{"tick": 1, "qubit": 1, "pauli": "X"}],
        [{"tick": 1, "qubit": 0, "pauli": "A"}],
        [{"tick": 1, "qubit": 0, "pauli": "X"}] * 65,
    ],
)
def test_custom_fault_validation_precedes_hardware(faults, monkeypatch):
    def no_serial(*args, **kwargs):
        pytest.fail("Invalid injection must not open serial")

    monkeypatch.setattr("qec.surface.simulation.GraphDecoder", no_serial)
    with pytest.raises(ValueError, match="fault"):
        CircuitExperiment("NOT-A-BOARD").run(settings(faults))
