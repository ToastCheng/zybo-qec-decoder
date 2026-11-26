"""Tests for fault injection, tick traces, and layout generation in `qec.surface.model.Lab`."""

import importlib.util
import random

import pytest
import stim


def lab():
    """Build the default `Lab` instance after confirming the web module is present."""
    assert importlib.util.find_spec("qec.surface.web") is not None, (
        "interactive lab is missing"
    )
    from qec.surface.model import Lab

    return Lab()


def test_tick_faults_replay_real_circuit_without_future_detectors():
    """Faults appear at their injected ticks and detectors stay hidden until their available tick."""
    model = lab()
    layout = model.layout()
    assert "ticks" in layout, "circuit TICK replay is missing"
    assert len(layout["ticks"]) == str(model.clean).count("TICK") + 1
    faults = [
        {"tick": 9, "qubit": 10, "pauli": "X"},
        {"tick": 16, "qubit": 10, "pauli": "Z"},
    ]
    result = model.simulate_faults(faults)
    assert model._sample(stim.Circuit(result["injected_circuit"])) == (
        result["syndrome"],
        result["observable"],
    )
    assert len(result["trace"]) == len(layout["ticks"])
    assert not result["trace"][8]["faults"]
    assert result["trace"][9]["faults"] == faults[:1]
    for tick, frame in enumerate(result["trace"]):
        assert all(
            layout["detectors"][i]["available_tick"] <= tick
            for i in frame["detector_indices"]
        )
    assert result["trace"][-1]["detector_indices"] == result["detector_indices"]
    assert result["source"] == "Software"
    assert result["host_frame"] == result["prediction"]


def test_fpga_prediction_drives_host_frame_and_failure_never_falls_back():
    """FPGA predictions drive the host frame, while board I/O errors propagate without fallback."""
    from qec.surface.model import Lab

    calls = []

    def board(syndrome):
        calls.append(syndrome)
        return {"prediction": 1, "cycles": 1234, "tx_hex": "d4", "rx_hex": "4d"}

    model = Lab(decoder=board)
    result = model.simulate_faults([])
    assert calls == [0]
    assert result["source"] == "FPGA"
    assert result["prediction"] == result["host_frame"] == 1
    assert result["logical_success"] is False
    assert result["hardware"]["cycles"] == 1234
    assert result["reference_prediction"] == 0

    def broken(syndrome):
        raise OSError("timeout")

    with pytest.raises(IOError, match="timeout"):
        Lab(decoder=broken).simulate_faults([])


def test_tick_correction_is_independently_replayed_and_frames_propagate():
    """Injected faults propagate through Pauli frames, replay cleanly after correction, and reject bad inputs."""
    model = lab()
    fault = {"tick": 8, "qubit": 10, "pauli": "X"}
    result = model.simulate_faults([fault])
    assert result["trace"][7]["pauli_frame"] == {}
    assert result["trace"][8]["pauli_frame"]["10"] == "X"
    assert result["correction"] is not None
    assert model._sample(stim.Circuit(result["corrected_circuit"])) == (
        0,
        result["observable"] ^ result["prediction"],
    )
    assert result["residual_syndrome"] == 0
    assert result["residual_observable"] == result["observable"] ^ result["host_frame"]
    late = model.simulate_faults([dict(fault, tick=21)])
    assert late["syndrome"] != result["syndrome"]
    for tick in range(len(model.layout()["ticks"])):
        r = model.simulate_faults([dict(fault, tick=tick)])
        assert model._sample(stim.Circuit(r["injected_circuit"])) == (
            r["syndrome"],
            r["observable"],
        )
        if r["correction"] is not None:
            assert r["residual_syndrome"] == 0
    for faults in [
        None,
        {},
        [{"tick": -1, "qubit": 10, "pauli": "X"}],
        [{"tick": True, "qubit": 10, "pauli": "X"}],
        [{"tick": 22, "qubit": 10, "pauli": "X"}],
        [{"tick": 8, "qubit": 2, "pauli": "X"}],
        [fault] * 65,
    ]:
        with pytest.raises(ValueError):
            model.simulate_faults(faults)


def test_cli_accepts_explicit_serial_source():
    """Layout source reflects the configured decoder and the web CLI accepts `--serial-port`."""
    import subprocess

    from qec.surface.model import Lab

    assert Lab().layout()["source"] == "Software"
    assert Lab(decoder=lambda s: None).layout()["source"] == "FPGA"
    completed = subprocess.run(
        ["qec/.venv/bin/python", "-m", "qec.surface.web", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "--serial-port" in completed.stdout


def test_multitime_replay_and_zero_syndrome_logical_chain():
    """Multi-tick faults compose by XOR, undetectable logical chains fail, and internal caches stay bounded."""
    model = lab()
    result = model.simulate_faults(
        [{"tick": 8, "qubit": q, "pauli": "X"} for q in [1, 8, 15]]
    )
    assert result["syndrome"] == 0 and result["observable"] == 1
    assert result["logical_success"] is False
    rng = random.Random(2)
    qubits = [q["id"] for q in model.layout()["data"]]
    for _ in range(40):
        faults = [
            {
                "tick": rng.randrange(22),
                "qubit": rng.choice(qubits),
                "pauli": rng.choice("XYZ"),
            }
            for _ in range(rng.randrange(1, 8))
        ]
        result = model.simulate_faults(faults)
        expected_s = expected_o = 0
        for fault in faults:
            s, o = model._sample(model._fault_circuit([fault]))
            expected_s ^= s
            expected_o ^= o
        assert (result["syndrome"], result["observable"]) == (expected_s, expected_o)
        if result["correction"] is not None:
            assert result["residual_syndrome"] == 0
            assert result["residual_observable"] == expected_o ^ result["prediction"]
    assert model._basis.cache_info().currsize <= 8
    assert model._signature.cache_info().currsize <= 512


def test_configured_hardware_cannot_silently_become_simulated():
    """Invalid FPGA responses raise an I/O error rather than falling back to software simulation."""
    from qec.surface.model import Lab

    for invalid in [
        None,
        {},
        {"prediction": 2, "cycles": 1},
        {"prediction": 0, "cycles": 0},
    ]:
        with pytest.raises(IOError, match="FPGA"):
            Lab(decoder=lambda s, invalid=invalid: invalid).simulate_faults([])


def test_layout_is_derived_from_stim():
    """Default lattice coordinates, check supports, and detector time slices match the Stim circuit."""
    model = lab().layout()
    assert model["injection"] == "Before selected tick operations"
    assert len(model["data"]) == 9
    assert len(model["checks"]) == 8
    assert len(model["detectors"]) == 24
    assert next(q for q in model["data"] if q["id"] == 1)["coords"] == [1, 1]
    assert next(q for q in model["checks"] if q["id"] == 9)["support"] == [1, 3, 8, 10]
    assert next(q for q in model["checks"] if q["id"] == 9)["basis"] == "Z"
    assert {d["coords"][2] for d in model["detectors"]} == {0, 1, 2, 3}
