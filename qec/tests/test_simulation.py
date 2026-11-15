import importlib
from pathlib import Path

import pytest
import stim

ROOT = Path(__file__).resolve().parents[2]


def test_added_noise_preserves_base_and_zero_requires_explicit_reference():
    lab = api().CircuitExperiment()
    text = "R 0\nH 0\nH 0\nTICK\nM 0\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(0) rec[-1]"
    cfg = settings(text)
    with pytest.raises(ValueError, match="reference"):
        lab.run(cfg)
    cfg["reference"] = text.replace("TICK", "X_ERROR(0.1) 0\nTICK")
    result = lab.run(cfg)
    assert result["syndrome"] == result["observable_truth"] == 0
    cfg["added_noise"] = 0.25
    result = lab.run(cfg)
    assert result["compiled"]["circuit"].count("DEPOLARIZE1(0.25)") == 2
    assert result["compiled"]["circuit"] == result["compiled"]["reference_circuit"]
    noisy = settings(text.replace("TICK", "X_ERROR(0.1) 0\nTICK"))
    noisy["added_noise"] = 0.75
    assert "X_ERROR(0.1)" in lab.run(noisy)["compiled"]["circuit"]
    for key, value in [
        ("seed", True),
        ("seed", -1),
        ("added_noise", float("nan")),
        ("added_noise", 0.76),
    ]:
        bad = dict(noisy, **{key: value})
        with pytest.raises(ValueError):
            lab.run(bad)


def test_fake_serial_orchestration_not_physical_hardware(monkeypatch):
    from types import SimpleNamespace

    module = api()
    events = []

    class Fake:
        def __init__(self, port):
            events.append(("open", port))
            self.transactions = [{"opcode": 1, "tx": b"abc", "rx": b"def"}]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            events.append("close")

        def identity(self):
            events.append("identity")
            return SimpleNamespace(
                max_detectors=128,
                max_edges=512,
                max_observables=32,
                words=(2, 128, 512, 32),
            )

        def load_graph(self, n, edges, obs):
            events.append(("load", n, obs))
            return self.identity()

        def decode(self, syndrome):
            events.append(("decode", syndrome))
            return SimpleNamespace(prediction=2, cycles=987, decode_error=False)

    monkeypatch.setattr(module, "GraphDecoder", Fake, raising=False)
    lab = module.CircuitExperiment(serial_port="FAKE-NOT-A-BOARD")
    cfg = settings((ROOT / "qec/examples/phase_bell.stim").read_text())
    assert lab.validate(cfg)["counts"]["qubits"] == 2
    assert events == []
    with pytest.raises(ValueError):
        lab.run(settings("NOT_A_GATE 0"))
    assert events == []
    result = lab.run(cfg)
    assert result["source"] == "FPGA"
    assert (result["prediction"], result["cycles"]) == (2, 987)
    assert result["transactions"][0]["tx_hex"] == "616263"
    assert events[-1] == "close"
    assert sum(isinstance(e, tuple) and e[0] == "load" for e in events) == 1
    lab.run(cfg)
    assert sum(isinstance(e, tuple) and e[0] == "open" for e in events) == 2

    def broken(self, syndrome):
        raise OSError("fake wire failure")

    monkeypatch.setattr(Fake, "decode", broken)
    with pytest.raises(OSError, match="fake wire failure"):
        lab.run(cfg)
    assert events[-1] == "close"


def test_compile_worker_timeout_is_reported(monkeypatch):
    import subprocess

    module = api()

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("compile", 15)

    monkeypatch.setattr(module.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="timeout"):
        module.CircuitExperiment().validate(settings("R 0"))


def api():
    assert importlib.util.find_spec("qec.surface.simulation"), (
        "runtime web entry point missing"
    )
    return importlib.import_module("qec.surface.simulation")


def settings(text):
    return {"circuit": text, "reference": None, "seed": 123, "added_noise": 0.0}


def test_arbitrary_circuit_real_single_shot_reproducible_trace():
    text = """R 0 1 2
H 0
TICK
H 0
X_ERROR(1) 0 2
M 0 1 2
DETECTOR rec[-3]
DETECTOR rec[-1]
OBSERVABLE_INCLUDE(0) rec[-3]
OBSERVABLE_INCLUDE(1) rec[-1]
"""
    lab = api().CircuitExperiment()
    result = lab.run(settings(text))
    assert result == lab.run(settings(text))
    assert result["source"] == "Software"
    assert result["compiled"]["counts"]["qubits"] == 3
    assert result["syndrome"] == result["observable_truth"] == result["prediction"] == 3
    assert result["cycles"] is None
    assert len(result["trace"]) == 2
    assert result["trace"][-1]["detectors"] == [True, True]
    assert result["trace"][-1]["paulis"][0] == "X"
    assert result["trace"][0]["detectors"] == []
    other = (ROOT / "qec/examples/phase_bell.stim").read_text()
    assert lab.run(settings(other))["compiled"]["counts"]["qubits"] == 2


@pytest.mark.parametrize("name", ["phase_bell", "two_repetition_echo"])
def test_checked_in_examples_execute_real_stim_and_software(name):
    result = (
        api()
        .CircuitExperiment()
        .run(settings((ROOT / f"qec/examples/{name}.stim").read_text()))
    )
    assert result["source"] == "Software"
    assert result["compiled"]["counts"]["observables"] == 2
    assert result["trace"][-1]["detectors"] == [
        bool(result["syndrome"] // (2**i) % 2)
        for i in range(result["compiled"]["counts"]["detectors"])
    ]
    assert result["transactions"] == []


def test_generic_gate_noise_and_feedback_rejected_before_insertion():
    module = api()
    cfg = settings("R 0 1\nS 0\nSQRT_X 1\nCX 0 1\nSPP Z0*Z1\nX_ERROR(0.1) 0\nM 0 1")
    cfg["added_noise"] = 0.02
    circuit, reference = module._prepare(cfg)
    noisy = stim.Circuit(circuit)
    assert reference is None
    assert "X_ERROR(0.1)" in circuit
    assert circuit.count("DEPOLARIZE1(0.02)") == 3
    assert "DEPOLARIZE2(0.02) 0 1" in circuit
    assert noisy.without_noise() == stim.Circuit(cfg["circuit"]).without_noise()
    cfg["circuit"] = "R 0 1\nM 0\nCX rec[-1] 1"
    with pytest.raises(ValueError, match="feedback"):
        module._prepare(cfg)


def test_diagram_metadata_uses_stim_targets_not_text_guessing():
    result = (
        api()
        .CircuitExperiment()
        .run(
            settings(
                "R 0 1023\nH 0\nS 0\nCX 0 1023\nSPP Z0*Z1023\nTICK\nR 0 1023\nX_ERROR(1) 1023\nM 0 1023\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]"
            )
        )
    )
    ops = result["trace"][0]["diagram"]
    assert [op["name"] for op in ops] == ["R", "H", "S", "CX", "SPP"]
    assert ops[3]["kind"] == "pair"
    assert ops[3]["targets"] == [{"qubit": 0}, {"qubit": 1023}]
    assert ops[4]["targets"] == [
        {"qubit": 0, "pauli": "Z"},
        {"combiner": True},
        {"qubit": 1023, "pauli": "Z"},
    ]
    assert result["trace"][1]["diagram"][-2]["targets"] == [{"record": -1}]
    assert result["compiled"]["counts"]["qubits"] == 1024


def test_uint32_observable_from_real_simulation():
    result = (
        api()
        .CircuitExperiment()
        .run(
            settings(
                "R 0\nX_ERROR(1) 0\nM 0\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]"
            )
        )
    )
    assert result["observable_truth"] == result["prediction"] == 2147483648
