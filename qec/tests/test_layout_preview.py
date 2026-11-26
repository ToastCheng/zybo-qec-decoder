"""Tests for serial-free circuit layout previews, qubit partitioning, and detector grids."""

import pytest
import stim

from qec.surface import engine
from qec.surface.encoded import examples


def test_encoded_previews_partition_actual_qubits_without_running(monkeypatch):
    """Check that encoded layout previews derive data qubits, check supports, and bases without simulation or serial I/O."""
    def forbidden(*args, **kwargs):
        pytest.fail("preview attempted simulation or serial access")

    monkeypatch.setattr(engine, "GraphDecoder", forbidden)
    monkeypatch.setattr(engine.CircuitExperiment, "run", forbidden)
    monkeypatch.setattr(engine.Lab, "run", forbidden)
    preview = engine.EditorLab("/not/a/serial/device").layout()
    for entry, count in zip(preview["examples"], (34, 102)):
        layout = entry["layout"]
        assert layout["mapping_verified"] is True
        assert layout["encoded_example"] == entry["id"]
        assert layout["logical_circuit"] == entry["logical_circuit"]
        circuit = stim.Circuit(entry["circuit"])
        used = {
            t.qubit_value
            for op in circuit.flattened()
            for t in op.targets_copy()
            if t.is_qubit_target or t.is_x_target or t.is_y_target or t.is_z_target
        }
        data = {q["id"] for q in layout["data"]}
        checks = {q["id"] for q in layout["checks"]}
        assert len(data) == count // 17 * 9
        assert len(checks) == count // 17 * 8
        assert not data & checks
        assert data | checks == used == set(range(count))
        assert len(layout["data"]) + len(layout["checks"]) == count
        # Inspect the first extraction round directly to cross-check the layout metadata.
        first_round = []
        for op in circuit.flattened():
            if op.name == "MR":
                break
            first_round.append(op)
        hadamards = {
            t.value for op in first_round if op.name == "H" for t in op.targets_copy()
        }
        pairs = [
            (a.value, b.value)
            for op in first_round
            if op.name == "CX"
            for a, b in zip(op.targets_copy()[::2], op.targets_copy()[1::2])
        ]
        for check in layout["checks"]:
            q = check["id"]
            neighbors = {b if a == q else a for a, b in pairs if q in (a, b)}
            assert check["support"] == sorted(neighbors)
            assert neighbors <= data
            assert len(neighbors) in (2, 4)
            assert check["basis"] == ("X" if q in hadamards else "Z")
            assert check["coords"] == circuit.get_final_qubit_coordinates()[q]


def assert_detector_grid(layout):
    """Assert that a layout's detector grid has unique cells, ordered round boundaries, and valid tick timings."""
    rows = {row["id"]: row for row in layout["rows"]}
    boundaries = {boundary["id"]: boundary for boundary in layout["boundaries"]}
    assert len(rows) == len(layout["rows"])
    assert list(boundaries) == list(range(len(boundaries)))
    assert [b["label"] for b in boundaries.values()] == [
        f"r{i}" for i in range(len(boundaries))
    ]
    cells = set()
    for detector in layout["detectors"]:
        assert detector["row"] in rows
        assert detector["boundary"] in boundaries
        assert (
            detector["available_tick"]
            <= boundaries[detector["boundary"]]["available_tick"]
        )
        cell = (detector["row"], detector["boundary"])
        assert cell not in cells
        cells.add(cell)
    assert len(cells) == len(layout["detectors"])


def test_preview_detector_grid_uses_coordinate_time_not_gate_tick():
    """Check that preset detectors group into rounds by coordinate time even when rounds share a gate TICK."""
    preview = engine.EditorLab().layout()
    for layout in [preview] + [entry["layout"] for entry in preview["examples"]]:
        assert_detector_grid(layout)
        by_time = {}
        for detector in layout["detectors"]:
            time = tuple(detector["coords"][2:])
            by_time.setdefault(time, set()).add(detector["boundary"])
            check = next(
                q for q in layout["checks"] if q["coords"][:2] == detector["coords"][:2]
            )
            assert detector["row"] == str(check["id"])
            row = next(row for row in layout["rows"] if row["id"] == detector["row"])
            assert row["label"] == f"{check['basis']}{check['id']}"
        assert all(len(indices) == 1 for indices in by_time.values())
        assert len({next(iter(indices)) for indices in by_time.values()}) == len(
            by_time
        )
        assert len(layout["boundaries"]) == len(by_time)
    assert preview["kind"] == "memory"
    assert preview["mapping_verified"] is True
    assert preview["checks"] == engine.Lab().layout()["checks"]
    # Final ancilla and data readouts share a TICK but have distinct detector time coordinates.
    assert (
        preview["boundaries"][-1]["available_tick"]
        == preview["boundaries"][-2]["available_tick"]
    )
    assert preview["boundaries"][-1]["id"] != preview["boundaries"][-2]["id"]


def test_custom_detector_grid_uses_spatial_coordinates_or_detector_identity():
    """Check that custom circuits group rows by spatial coordinates and fall back to detector IDs when omitted."""
    circuit = stim.Circuit("""
        R 0
        M 0
        DETECTOR(8, 9, 2) rec[-1]
        DETECTOR(8, 9, 3) rec[-1]
        TICK
        DETECTOR(10, 9, 3) rec[-1]
        DETECTOR rec[-1]
    """)
    layout = engine._layout(circuit, "Software")
    assert_detector_grid(layout)
    assert layout["checks"] == []
    a, b, c, d = layout["detectors"]
    assert a["row"] == b["row"] != c["row"]
    assert a["boundary"] != b["boundary"] == c["boundary"]
    assert d["row"] == "D3"
    assert a["available_tick"] == b["available_tick"]


def test_physical_layout_keeps_typed_targets_without_inventing_qubits():
    """Check that record lookbacks and MPP Pauli targets preserve their types without creating extra qubits."""
    circuit = stim.Circuit("R 0 2\nM 0\nCX rec[-1] 2\nMPP X0*Z2\nDETECTOR rec[-1]")
    layout = engine._layout(circuit, "Software")
    assert [q["id"] for q in layout["data"]] == [0, 2]
    operations = layout["ticks"][0]["operations"]
    feedback = next(op for op in operations if op["name"] == "CX")
    assert feedback["targets"] == [2]
    assert feedback["typed_targets"] == [
        {"type": "rec", "value": -1},
        {"type": "qubit", "value": 2},
    ]
    mpp = next(op for op in operations if op["name"] == "MPP")
    assert mpp["typed_targets"] == [
        {"type": "X", "value": 0},
        {"type": "combiner"},
        {"type": "Z", "value": 2},
    ]


@pytest.mark.parametrize("index", [0, 1])
def test_run_reuses_preview_geometry_and_detector_grid(index):
    """Check that running an encoded preset returns the same geometry and detector grid as its preview."""
    lab = engine.EditorLab()
    entry = lab.layout()["examples"][index]
    response = lab.circuit_run(
        {
            "circuit": entry["circuit"],
            "logical_circuit": entry["logical_circuit"],
            "reference": None,
            "seed": 1,
            "added_noise": 0,
        }
    )
    for field in (
        "data",
        "checks",
        "rows",
        "boundaries",
        "detectors",
        "mapping_verified",
    ):
        assert response["layout"][field] == entry["layout"][field]
    assert_detector_grid(response["layout"])


def test_memory_run_keeps_preview_grid_and_semantics():
    """Check that running the default memory circuit preserves the preview layout kind and detector grid."""
    lab = engine.EditorLab()
    preview = lab.layout()
    result = lab.run(preview["run_defaults"])
    assert result["layout"]["kind"] == "memory"
    for field in ("data", "checks", "rows", "boundaries", "detectors"):
        assert result["layout"][field] == preview[field]


def test_unknown_geometry_does_not_inherit_verified_surface_mapping():
    """Ensure mapping_verified and check geometry are cleared when logical_circuit does not match the preset."""
    entry = examples()[0]
    layout = engine._layout(stim.Circuit(entry["circuit"]), "Software", "R 0")
    assert layout["mapping_verified"] is False
    assert layout["checks"] == []
