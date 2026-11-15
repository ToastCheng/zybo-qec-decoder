"""CLI controls for the single-window example's sampling batch."""

import json
from pathlib import Path
import subprocess
import sys

import pytest
import stim

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("seed,shots", [(0, 1), (1, 64), (20261107, 256)])
def test_seed_and_shots_match_stim_samples(seed, shots):
    command = [
        sys.executable,
        "-m",
        "qec.surface.example",
        "--seed",
        str(seed),
        "--shots",
        str(shots),
    ]
    first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert first.returncode == 0, first.stderr
    second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    window = json.loads(first.stdout)
    config = json.loads((ROOT / "qec/surface/graphs/d3_z_r3.json").read_text())
    detectors, observables = (
        stim.Circuit(config["circuit"])
        .compile_detector_sampler(seed=seed)
        .sample(shots, separate_observables=True)
    )
    index = next((i for i, row in enumerate(detectors) if row.any()), 0)
    assert window["shot"] == index
    assert window["syndrome"] == sum(
        int(bit) << i for i, bit in enumerate(detectors[index])
    )
    assert window["observable"] == int(observables[index, 0])
    assert window["residual"] == 0


@pytest.mark.parametrize(
    "arguments",
    [("--shots", "0"), ("--shots", "-1"), ("--seed", "-1"), ("--seed", str(1 << 64))],
)
def test_invalid_sampling_arguments(arguments):
    run = subprocess.run(
        [sys.executable, "-m", "qec.surface.example", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert run.returncode == 2
    assert "unrecognized arguments" not in run.stderr
    assert (
        "--shots must be positive"
        if arguments[0] == "--shots"
        else "--seed must fit an unsigned 64-bit integer"
    ) in run.stderr


def test_default_seed_is_unset(monkeypatch, capsys):
    import qec.surface.example as example

    seeds = []
    original = stim.Circuit

    class CircuitSpy(original):
        def compile_detector_sampler(self, *, seed=None, **kwargs):
            seeds.append(seed)
            return super().compile_detector_sampler(seed=seed, **kwargs)

    monkeypatch.setattr(stim, "Circuit", CircuitSpy)
    monkeypatch.setattr(sys, "argv", ["example", "--shots", "1"])
    monkeypatch.chdir(ROOT)
    example.main()
    assert seeds == [None]
    window = json.loads(capsys.readouterr().out)
    assert window["shot"] == 0
