"""Initial circuit inputs are generated without serial access."""

import stim

from qec.surface.engine import EditorLab


def test_known_encoded_example_has_verified_logical_metadata(monkeypatch):
    from qec.surface import encoded

    entry = {
        "id": "test-encoding",
        "label": "Test mapping identity",
        "circuit": "R 0\nX_ERROR(0.01) 0\nM 0\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(0) rec[-1]",
        "logical_circuit": "R 0\nM 0",
    }
    monkeypatch.setattr(encoded, "examples", lambda: [entry])
    result = EditorLab().circuit_run(
        {
            "circuit": entry["circuit"],
            "logical_circuit": entry["logical_circuit"],
            "reference": None,
            "seed": 1,
            "added_noise": 0,
        }
    )
    assert result["layout"]["mapping_verified"] is True
    assert result["layout"]["encoded_example"] == entry["id"]
    result = EditorLab().circuit_run(
        {
            "circuit": entry["circuit"],
            "logical_circuit": "R 0\nH 0\nM 0",
            "reference": None,
            "seed": 1,
            "added_noise": 0,
        }
    )
    assert result["layout"]["mapping_verified"] is False


def test_memory_layout_supplies_editable_base_and_reference(monkeypatch):
    def no_serial(*args, **kwargs):
        raise AssertionError("Opening the circuit editor must not open serial")

    monkeypatch.setattr("qec.surface.engine.GraphDecoder", no_serial)
    layout = EditorLab("NOT-A-BOARD").layout()
    circuit = stim.Circuit(layout["circuit"])
    assert circuit.num_detectors == 24
    assert circuit.num_ticks == 21
    assert circuit.without_noise() == circuit
    assert stim.Circuit(layout["reference_circuit"]).without_noise() == circuit
    assert sorted(entry["id"] for entry in layout["examples"]) == [
        "phase_bell",
        "two_repetition_echo",
    ]
    for entry in layout["examples"]:
        assert entry["label"]
        assert stim.Circuit(entry["circuit"]).num_qubits in (34, 102)
    assert sorted(
        {(int(d["coords"][2]), d["available_tick"]) for d in layout["detectors"]}
    ) == [(0, 7), (1, 14), (2, 21), (3, 21)]
