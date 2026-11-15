import pytest
import stim

from qec.surface.model import Lab

NOISE_KEYS = (
    "after_clifford_depolarization",
    "before_round_data_depolarization",
    "before_measure_flip_probability",
    "after_reset_flip_probability",
)


def settings(p=0.1, seed=17):
    return {
        "circuit": "surface_code:rotated_memory_z",
        "distance": 3,
        "rounds": 3,
        "noise": dict.fromkeys(NOISE_KEYS, p),
        "seed": seed,
        "faults": [],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("circuit", "surface_code:rotated_memory_x"),
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


def test_zero_max_noise_different_seeds_and_explicit_faults():
    lab = Lab()
    zero = lab.run(settings(0, 0))
    assert zero["syndrome"] == zero["observable"] == 0
    assert zero["sampled_noise"]["events"] == []
    request = settings(0)
    request["faults"] = [{"tick": 9, "qubit": 10, "pauli": "X"}]
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
        raise OSError("serial timeout")

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
