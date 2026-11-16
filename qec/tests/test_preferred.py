from pathlib import Path

import pytest

from qec.surface.engine import EditorLab

ROOT = Path(__file__).resolve().parents[2]


def test_general_layout_preserves_gate_target_order():
    cfg = {
        "circuit": "R 0 1\nCX 1 0\nTICK\nX_ERROR(1) 0\nM 0 1\nDETECTOR rec[-2]",
        "reference": None,
        "seed": 1,
        "added_noise": 0,
    }
    response = EditorLab().circuit_run(cfg)
    operations = response["layout"]["ticks"][0]["operations"]
    assert next(op for op in operations if op["name"] == "CX")["targets"] == [1, 0]


def test_memory_signature_cache_tracks_generated_circuit():
    from qec.surface.model import Lab

    model = Lab()
    model._signature(8, 1, "X")
    model.configure("surface_code:rotated_memory_z", 3, 4)
    s, o = model._sample(model._fault_circuit([{"tick": 8, "qubit": 1, "pauli": "X"}]))
    assert model._signature(8, 1, "X") == s | (o << model.clean.num_detectors)


@pytest.mark.parametrize("logical", ["M(0.1) 0", "MR(0.1) 0"])
def test_logical_display_rejects_measurement_noise(logical):
    settings = {
        "circuit": "R 0\nX_ERROR(1) 0\nM 0\nDETECTOR rec[-1]",
        "reference": None,
        "seed": 1,
        "added_noise": 0,
        "logical_circuit": logical,
    }
    with pytest.raises(ValueError, match="noiseless"):
        EditorLab().circuit_run(settings)


def test_optional_logical_clifford_metadata_and_rejection_before_serial():
    text = "R 0\nX_ERROR(1) 0\nM 0\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]"
    settings = {
        "circuit": text,
        "reference": None,
        "seed": 1,
        "added_noise": 0,
        "logical_circuit": "R 0 1\nH 0\nCX 0 1\nTICK\nM 0 1",
    }
    response = EditorLab().circuit_run(settings)
    assert response["result"]["prediction"] == 2147483648
    assert response["layout"]["logical_circuit"] == settings["logical_circuit"]
    assert response["layout"]["mapping_verified"] is False
    assert response["experiment"]["compiled"]["logical_mapping_verified"] is False
    for logical in ["T 0", "X_ERROR(0.1) 0", "M 0\nCX rec[-1] 1", 12]:
        with pytest.raises(ValueError):
            EditorLab("/not/a/serial/device").circuit_run(
                dict(settings, logical_circuit=logical)
            )


def test_editor_layout_and_real_memory_run():
    lab = EditorLab()
    layout = lab.layout()
    assert layout["protocol"] == "graph-v2"
    assert layout["source"] == "Software"
    assert len(layout["data"]) == 9
    settings = layout["run_defaults"]
    settings["faults"] = [{"tick": 8, "qubit": 1, "pauli": "X"}]
    result = lab.run(settings)
    assert result["hardware"] is None
    assert result["experiment"]["compiled"]["counts"]["detectors"] == 24
    assert result["sampled_circuit"]
    assert result["residual_syndrome"] == 0


@pytest.mark.parametrize("name,qubits", [("phase_bell", 2), ("two_repetition_echo", 6)])
def test_general_editor_layout(name, qubits):
    response = EditorLab().circuit_run(
        {
            "circuit": (ROOT / f"qec/tests/fixtures/bare_{name}.stim").read_text(),
            "reference": None,
            "seed": 1,
            "added_noise": 0,
        }
    )
    assert response["layout"]["kind"] == "circuit"
    assert len(response["layout"]["data"]) == qubits
    assert response["result"]["correction"] is None
    assert (
        response["result"]["trace"][-1]["detector_indices"]
        == response["result"]["detector_indices"]
    )
