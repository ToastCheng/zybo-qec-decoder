"""Noise selection changes the sampled circuit without changing the board graph."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import stim

ROOT = Path(__file__).resolve().parents[2]


def run_example(*arguments):
    return subprocess.run([sys.executable, '-m', 'qec.surface.example', *arguments],
                          cwd=ROOT, text=True, capture_output=True, timeout=20)


@pytest.mark.parametrize('noise', ['0', '0.01', '0.75'])
def test_noise_controls_circuit_and_samples(noise):
    circuit_run = run_example('--noise', noise, '--circuit')
    assert circuit_run.returncode == 0, circuit_run.stderr
    circuit = stim.Circuit(circuit_run.stdout)
    assert circuit.num_detectors == 24
    assert circuit.num_observables == 1
    noisy = run_example('--noise', noise, '--seed', '123', '--shots', '64')
    assert noisy.returncode == 0, noisy.stderr
    window = json.loads(noisy.stdout)
    det, obs = circuit.compile_detector_sampler(seed=123).sample(64, separate_observables=True)
    index = next((i for i, row in enumerate(det) if row.any()), 0)
    assert window['shot'] == index
    assert window['syndrome'] == sum(int(bit) << i for i, bit in enumerate(det[index]))
    assert window['observable'] == int(obs[index, 0])
    assert window['residual'] == 0
    if noise == '0':
        assert not det.any() and not obs.any()
        assert window['prediction'] == window['pymatching'] == 0
    else:
        assert f'DEPOLARIZE2({noise})' in str(circuit)
        assert f'DEPOLARIZE1({noise})' in str(circuit)
        assert f'X_ERROR({noise})' in str(circuit)


@pytest.mark.parametrize('noise', ['-0.01', '0.750001', '0.8', '1', '1.01', 'nan', 'inf'])
@pytest.mark.parametrize('arguments', [(), ('--circuit',)])
def test_invalid_noise_is_a_cli_error(noise, arguments):
    result = run_example('--noise', noise, *arguments)
    assert result.returncode == 2
    assert '--noise must be between 0 and 0.75 (inclusive)' in result.stderr


def test_default_noise_preserves_committed_circuit():
    result = run_example('--noise', '0.001', '--circuit')
    assert result.returncode == 0, result.stderr
    config = json.loads((ROOT / 'qec/surface/graphs/d3_z_r3.json').read_text())
    assert str(stim.Circuit(result.stdout)) == str(stim.Circuit(config['circuit']))
