"""Presentation regressions; fixture values are not benchmark evidence."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark_accuracy', ROOT / 'scripts/benchmark_accuracy.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def test_accuracy_plot_has_four_named_curves_per_memory_panel(tmp_path):
    rows = [dict(basis=basis, distance=distance, p=p, decoder=decoder,
                 failure_probability=.01, ci_low=.005, ci_high=.02, shots=100)
            for basis in ('X', 'Z') for distance in (3, 5)
            for decoder in ('UF', 'MWPM') for p in (.001, .004)]
    benchmark.plot_results(rows, tmp_path)
    svg = (tmp_path / 'benchmark-accuracy.svg').read_text()
    for label in ('Matching d=3', 'Matching d=5', 'UF d=3', 'UF d=5'):
        assert svg.count('>' + label + '</text>') == 2
    assert 'software experiment' in svg
    assert 'PyMatching' in svg


def test_readme_export_preserves_all_four_accuracy_curves(tmp_path, monkeypatch):
    output = tmp_path / 'smoke'
    monkeypatch.setattr(benchmark.sys, 'argv', [
        'benchmark_accuracy.py', '--output', str(output), '--shots', '2',
        '--batch-size', '2', '--p', '.001', '--readme-png', str(tmp_path / 'readme.png'),
    ])
    benchmark.main()
    svg = (output / 'readme/benchmark-accuracy.svg').read_text()
    for label in ('Matching d=3', 'Matching d=5', 'UF d=3', 'UF d=5'):
        assert svg.count('>' + label + '</text>') == 2
    assert (tmp_path / 'readme.png').read_bytes() == (output / 'readme/benchmark-accuracy.png').read_bytes()
