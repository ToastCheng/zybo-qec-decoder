"""Configurable single-shot Stim runs, independently replayed without resampling."""

import copy
import json
import threading
import urllib.error
import urllib.request

import pytest
import stim

from qec.surface.web import Lab

NOISE_KEYS = (
    "after_clifford_depolarization",
    "before_round_data_depolarization",
    "before_measure_flip_probability",
    "after_reset_flip_probability",
)


def settings(p=0.1, seed=17):
    return dict(
        circuit="surface_code:rotated_memory_z",
        distance=3,
        rounds=3,
        noise=dict.fromkeys(NOISE_KEYS, p),
        seed=seed,
        faults=[],
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("circuit", "surface_code:rotated_memory_x"),
        ("distance", 5),
        ("rounds", 4),
        ("distance", 3.0),
        ("rounds", True),
        ("seed", True),
        ("seed", -1),
        ("seed", 2**53),
        ("seed", 1.5),
        ("seed", "1"),
        ("faults", None),
        ("faults", [{"tick": 99, "qubit": 1, "pauli": "X"}]),
        ("faults", [{"tick": 1, "qubit": 2, "pauli": "X"}]),
    ],
)
def test_invalid_settings_rejected_before_decoder(field, value):
    calls = []
    lab = Lab(decoder=lambda syndrome: calls.append(syndrome))
    request = settings()
    request[field] = value
    with pytest.raises(ValueError):
        lab.run(request)
    assert calls == []


@pytest.mark.parametrize(
    "value", [-0.1, 0.75001, float("nan"), float("inf"), True, "0.1", None]
)
@pytest.mark.parametrize("key", NOISE_KEYS)
def test_invalid_noise_rejected_before_decoder(key, value):
    calls = []
    request = settings()
    request["noise"][key] = value
    with pytest.raises(ValueError):
        Lab(decoder=lambda s: calls.append(s)).run(request)
    assert calls == []


def test_http_run_accepts_full_fault_list_and_rejects_invalid_before_io():
    from qec.surface.web import make_server

    calls = []

    def board(syndrome):
        calls.append(syndrome)
        return dict(prediction=1, cycles=640)

    server = make_server(port=0, decoder=board)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"

    def post(body):
        request = urllib.request.Request(
            root + "/api/run", data=json.dumps(body, indent=2).encode()
        )
        return urllib.request.urlopen(request)

    try:
        bad = settings()
        bad["distance"] = 5
        with pytest.raises(urllib.error.HTTPError) as error:
            post(bad)
        assert error.value.code == 400
        assert calls == []
        request = settings(0, 2**53 - 1)
        request["faults"] = [dict(tick=9, qubit=10, pauli="X")] * 64
        assert len(json.dumps(request, indent=2).encode()) > 4096
        with post(request) as response:
            result = json.load(response)
        assert calls == [result["syndrome"]]
        assert result["prediction"] == result["host_frame"] == 1
        assert result["source"] == "FPGA"
        assert result["hardware"] == dict(prediction=1, cycles=640)
        assert result["logical_success"] is False
        with urllib.request.urlopen(root + "/api/layout") as response:
            layout = json.load(response)
        assert layout["supported_circuits"][0]["circuit"] == request["circuit"]
        assert layout["run_defaults"]["noise"] == dict.fromkeys(NOISE_KEYS, 0.001)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_schema_rejection_and_http_recovery():
    from qec.surface.web import make_server

    calls = []

    def board(syndrome):
        calls.append(syndrome)
        raise IOError("serial timeout")

    server = make_server(port=0, decoder=board)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    bad_bodies = [None, [], {}, dict(settings(), extra=1)]
    for key in ("noise", "faults", "seed"):
        request = copy.deepcopy(settings())
        del request[key]
        bad_bodies.append(request)
    for noise in ({}, {"unexpected": 0}, []):
        request = settings()
        request["noise"] = noise
        bad_bodies.append(request)
    try:
        for body in bad_bodies:
            req = urllib.request.Request(
                root + "/api/run", data=json.dumps(body).encode()
            )
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            assert error.value.code == 400
        assert calls == []
        for data, expected in (
            (b"x" * 16385, 413),
            (json.dumps(settings(0)).encode(), 503),
        ):
            req = urllib.request.Request(root + "/api/run", data=data)
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(req)
            assert error.value.code == expected
        assert calls == [0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_zero_max_noise_different_seeds_and_explicit_faults():
    lab = Lab()
    zero = lab.run(settings(0, 0))
    assert zero["syndrome"] == zero["observable"] == 0
    assert zero["sampled_noise"]["events"] == []
    request = settings(0)
    request["faults"] = [dict(tick=9, qubit=10, pauli="X")]
    shot = lab.run(request)
    legacy = lab.simulate_faults(request["faults"])
    assert (shot["syndrome"], shot["observable"]) == (
        legacy["syndrome"],
        legacy["observable"],
    )
    shots = [lab.run(settings(0.75, seed)) for seed in range(4)]
    assert len({s["sampled_circuit"] for s in shots}) == 4
    assert len({(s["syndrome"], s["observable"]) for s in shots}) > 1
    for shot in shots:
        assert lab._sample(stim.Circuit(shot["sampled_circuit"])) == (
            shot["syndrome"],
            shot["observable"],
        )
        if shot["correction"] is not None:
            assert lab._sample(stim.Circuit(shot["corrected_circuit"])) == (
                0,
                shot["observable"] ^ shot["prediction"],
            )


@pytest.mark.parametrize(
    "reply",
    [None, {}, {"prediction": True, "cycles": 1}, {"prediction": 0, "cycles": 0}],
)
def test_invalid_hardware_reply_has_no_fallback(reply):
    with pytest.raises(OSError, match="Invalid FPGA"):
        Lab(decoder=lambda syndrome: reply).run(settings(0))


def test_hardware_failure_has_no_fallback():
    def board(syndrome):
        raise IOError("serial timeout")

    with pytest.raises(OSError, match="serial timeout"):
        Lab(decoder=board).run(settings(0))


def test_run_samples_one_reproducible_shot_and_exports_exact_noise_replay():
    lab = Lab()
    request = settings()
    result = lab.run(request)
    assert result == lab.run(request)
    assert result["settings"] == request
    assert "DEPOLARIZE2(0.1)" in result["injected_circuit"]
    assert result["sampled_noise"]["events"]
    assert result["sampled_noise"]["stim_version"] == stim.__version__
    frozen = stim.Circuit(result["sampled_circuit"])
    assert lab._sample(frozen) == (result["syndrome"], result["observable"])
    replay = stim.FlipSimulator(
        batch_size=1,
        num_qubits=frozen.num_qubits,
        disable_stabilizer_randomization=True,
        seed=999,
    )
    tick = 0
    for op in frozen:
        if op.name == "TICK":
            frame = replay.peek_pauli_flips(instance_index=0)
            assert result["trace"][tick]["pauli_frame"] == {
                str(q): "_XYZ"[frame[q]] for q in range(len(frame)) if frame[q]
            }
            tick += 1
        replay.do(op)
    frame = replay.peek_pauli_flips(instance_index=0)
    assert result["trace"][tick]["pauli_frame"] == {
        str(q): "_XYZ"[frame[q]] for q in range(len(frame)) if frame[q]
    }
    assert result["trace"][-1]["detector_indices"] == result["detector_indices"]
    assert result["logical_success"] == (
        result["observable"] == result["prediction"] and not result["error"]
    )
    if result["correction"] is not None:
        assert lab._sample(stim.Circuit(result["corrected_circuit"])) == (
            0,
            result["observable"] ^ result["prediction"],
        )
    else:
        assert result["correction_status"] == "unavailable"
        assert result["residual_syndrome"] is None
        assert result["residual_observable"] is None


@pytest.mark.parametrize("path", ["/", "/api/layout", "/api/run", "/api/simulate"])
def test_rebinding_host_rejected_before_assets_or_decoder(path):
    from http.client import HTTPConnection
    from qec.surface.web import make_server

    calls = []
    server = make_server(0, decoder=lambda s: calls.append(s))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port)
    try:
        post = path in ("/api/run", "/api/simulate")
        connection.request(
            "POST" if post else "GET",
            path,
            body=json.dumps(settings(0)) if path == "/api/run" else '{"faults":[]}',
            headers={
                "Host": "rebind.attacker.test",
                "Origin": "http://rebind.attacker.test",
            },
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 403
        assert calls == []
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join()
