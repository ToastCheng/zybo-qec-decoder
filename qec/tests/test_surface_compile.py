"""Restricted logical compiler contract (TQEC is an optional dependency)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
OPTIONAL = pytest.mark.skipif(importlib.util.find_spec('tqec') is None,
                              reason='optional pinned TQEC compiler dependency is not installed')


@OPTIONAL
def test_h_compile_produces_auditable_artifacts_and_real_decoding(tmp_path):
    import hashlib
    import stim
    from qec.surface.compile import compile_program, parse_program

    program = parse_program('{"qubits":1,"gates":[{"gate":"H","targets":[0]}]}')
    out = tmp_path / 'h'
    manifest = compile_program(program, out, basis='z', distance=3,
                               noise=.001, shots=32, seed=123)
    assert manifest['template'] == 'h'
    assert manifest['counts']['detectors'] == 56
    assert manifest['counts']['edges'] == 208
    assert manifest['shortest_graphlike_error'] == 3
    assert manifest['metrics']['shots'] == 32
    assert manifest['metrics']['uf_syndrome_failures'] == 0
    assert manifest['metrics']['ideal_detector_flips'] == 0
    assert manifest['metrics']['ideal_observable_flips'] == 0
    assert manifest['hardware']['compatible_with_loaded_image'] is False
    assert manifest['hardware']['rom_exported'] is True
    for filename, digest in manifest['sha256'].items():
        assert hashlib.sha256((out / filename).read_bytes()).hexdigest() == digest
    assert json.loads((out / 'manifest.json').read_text()) == manifest
    ideal = stim.Circuit((out / 'ideal.stim').read_text())
    det, obs = ideal.compile_detector_sampler(seed=123).sample(128, separate_observables=True)
    assert not det.any() and not obs.any()
    graph = json.loads((out / 'graph.json').read_text())
    vb = graph['detectors'].bit_length()
    words = [int(word, 16) for word in (out / 'graph.mem').read_text().splitlines()]
    assert words == [a | (b << vb) | (mask << (2 * vb)) for a, b, mask in graph['edges']]
    with pytest.raises(FileExistsError):
        compile_program(program, out, shots=1)


@OPTIONAL
@pytest.mark.parametrize('template,qubits,gates', [
    ('h', 1, [{'gate': 'H', 'targets': [0]}]),
    ('cx', 2, [{'gate': 'CX', 'targets': [0, 1]}]),
    ('memory', 1, []),
])
@pytest.mark.parametrize('basis', ['x', 'z'])
@pytest.mark.parametrize('distance', [3, 5])
def test_vetted_templates_both_bases_and_distances(tmp_path, template, qubits, gates, basis, distance):
    from qec.surface.compile import compile_program, parse_program

    p = parse_program(json.dumps(dict(qubits=qubits, gates=gates)))
    out = tmp_path / 'compiled'
    m = compile_program(p, out, basis=basis, distance=distance, shots=8, seed=123)
    assert m['shortest_graphlike_error'] == distance
    assert m['metrics']['uf_syndrome_failures'] == 0
    assert m['metrics']['ideal_observable_flips'] == 0
    assert m['counts']['observables'] == qubits
    edges = json.loads((out / 'graph.json').read_text())['edges']
    if template == 'cx':
        assert {e[2] for e in edges} == {0, 1, 2, 3}
        assert not (out / 'graph.mem').exists()
        assert m['hardware']['rom_exported'] is False


@OPTIONAL
def test_cli_compiles_and_rejects_wrong_image_before_opening_serial(tmp_path):
    source = tmp_path / 'h.json'
    source.write_text('{"qubits":1,"gates":[{"gate":"H","targets":[0]}]}')
    command = [sys.executable, '-m', 'qec.surface.compile', str(source),
               '--basis', 'x', '--k', '1', '--noise', '0', '--shots', '16',
               '--seed', '123', '--out', str(tmp_path / 'run')]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest['noise'] == 0
    assert manifest['reference_noise'] == .001
    assert manifest['metrics']['uf_logical_failures'] == 0
    assert manifest['metrics']['mwpm_logical_failures'] == 0
    assert 'error(' not in (tmp_path / 'run' / 'model.dem').read_text()
    assert 'error(' in (tmp_path / 'run' / 'reference.dem').read_text()
    command[command.index(str(tmp_path / 'run'))] = str(tmp_path / 'blocked')
    result = subprocess.run(command + ['--port', '/definitely/not/a/serial/device'],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'matching graph-specific image' in result.stderr
    assert 'SerialException' not in result.stderr
    assert not (tmp_path / 'blocked').exists()


@pytest.mark.parametrize('option,value', [
    ('basis', 'y'), ('distance', 7), ('distance', True),
    ('noise', -.1), ('noise', .751), ('noise', float('nan')),
    ('noise', float('inf')), ('noise', True),
    ('shots', 0), ('shots', True), ('seed', -1), ('seed', 2**64),
])
def test_invalid_compile_options_fail_without_artifacts(tmp_path, option, value):
    from qec.surface.compile import compile_program, parse_program

    with pytest.raises(ValueError):
        compile_program(parse_program('{"qubits":1,"gates":[]}'), tmp_path / 'bad',
                        **{option: value})
    assert not (tmp_path / 'bad').exists()


@OPTIONAL
@pytest.mark.parametrize('template,qubits,gates', [
    ('h', 1, [{'gate': 'H', 'targets': [0]}]),
    ('cx', 2, [{'gate': 'CX', 'targets': [0, 1]}]), ('memory', 1, [])])
@pytest.mark.parametrize('basis', ['x', 'z'])
@pytest.mark.parametrize('noise', [0, .75])
def test_zero_and_maximum_noise_models_are_real_and_decodable(tmp_path, template, qubits, gates, basis, noise):
    from qec.surface.compile import compile_program, parse_program

    p = parse_program(json.dumps(dict(qubits=qubits, gates=gates)))
    m = compile_program(p, tmp_path / 'run', basis=basis, noise=noise, shots=4)
    assert m['metrics']['uf_syndrome_failures'] == 0
    if noise == 0:
        assert m['metrics']['uf_logical_failures'] == 0
        assert m['metrics']['mwpm_logical_failures'] == 0
        assert m['reference_noise'] == .001
        assert m['counts']['edges'] > 0


@OPTIONAL
@pytest.mark.parametrize('basis', ['x', 'z'])
@pytest.mark.parametrize('template,qubits,gates', [
    ('h', 1, [{'gate': 'H', 'targets': [0]}]),
    ('cx', 2, [{'gate': 'CX', 'targets': [0, 1]}]),
])
def test_artifact_records_gate_correlations_and_replayable_decode_evidence(tmp_path, basis, template, qubits, gates):
    from qec.surface.compile import compile_program, parse_program
    from qec.surface.decoder import decode

    m = compile_program(parse_program(json.dumps(dict(qubits=qubits, gates=gates))),
                        tmp_path / 'run', basis=basis, shots=32)
    logical = json.loads((tmp_path / 'run' / 'logical.json').read_text())
    paulis = logical['observable_stabilizers']
    if template == 'h':
        assert paulis == (['XZ'] if basis == 'x' else ['ZX'])
    else:
        # Compare generated stabilizer group, not a particular generator choice.
        def group(gens):
            a, b = gens
            return {a, b, ''.join(x if y == 'I' else y if x == 'I' else 'I'
                                  for x, y in zip(a, b))}
        assert group(paulis) == group(['XIXX', 'IXIX'] if basis == 'x' else ['ZIZI', 'IZZZ'])
    graph = json.loads((tmp_path / 'run' / 'graph.json').read_text())
    evidence = json.loads((tmp_path / 'run' / 'shots.json').read_text())
    failures = 0
    for shot in evidence:
        syndrome = int(shot['syndrome_hex'], 16)
        r = decode(graph['detectors'], graph['edges'], syndrome)
        assert not r['error']
        assert r['prediction'] == shot['uf_prediction']
        residual = syndrome
        for edge in r['correction_edges']:
            for endpoint in graph['edges'][edge][:2]:
                if endpoint < graph['detectors']:
                    residual ^= 1 << endpoint
        assert residual == 0
        failures += shot['uf_prediction'] != shot['observable_mask']
    assert failures == m['metrics']['uf_logical_failures']
    assert m['noise_model'] == 'tqec.uniform_depolarizing'
    assert 'compiler_sha256' in m['versions']


def test_port_is_rejected_without_dependencies_or_even_reading_source(tmp_path, capsys):
    from qec.surface.compile import main

    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / 'absent.json'), '--out', str(tmp_path / 'blocked'),
              '--port', '/not/a/device'])
    assert exc.value.code == 2
    assert 'matching graph-specific image' in capsys.readouterr().err
    assert not (tmp_path / 'blocked').exists()


def test_missing_optional_dependencies_have_actionable_cli_error(tmp_path):
    source = tmp_path / 'memory.json'
    source.write_text('{"qubits":1,"gates":[]}')
    r = subprocess.run([sys.executable, '-S', '-m', 'qec.surface.compile', str(source),
                        '--out', str(tmp_path / 'run')], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2
    assert 'requirements-compiler.txt' in r.stderr
    assert 'Traceback' not in r.stderr
    assert not (tmp_path / 'run').exists()


@pytest.mark.parametrize('source', [
    '{"qubits":1,"gates":[{"gate":"S","targets":[0]}]}',
    '{"qubits":1,"gates":[{"gate":"H","targets":[0]},{"gate":"H","targets":[0]}]}',
    '{"qubits":1,"gates":[],"adaptive":true}', '{not json}',
])
def test_cli_rejects_unvetted_programs_without_artifacts(tmp_path, source):
    path = tmp_path / 'bad.json'
    path.write_text(source)
    r = subprocess.run([sys.executable, '-m', 'qec.surface.compile', str(path),
                        '--out', str(tmp_path / 'run')], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2
    assert 'Traceback' not in r.stderr
    assert not (tmp_path / 'run').exists()


def test_loss_checked_graph_preserves_all_masks_and_rejects_projection_loss():
    import stim
    from qec.surface.compile import checked_graph

    dem = stim.DetectorErrorModel('error(0.1) D0 D1 L0 L1\nerror(0.1) D1 L1')
    edges, _ = checked_graph(dem, 2, 2)
    assert edges == [(0, 1, 3), (1, 2, 2)]
    for text in ['error(0.1) D0 D1 D2', 'error(0.1) L0',
                 'error(0.1) D0\nerror(0.1) D0 L0',
                 'error(0.1) D3', 'error(0.1) D0 L2']:
        with pytest.raises(ValueError):
            checked_graph(stim.DetectorErrorModel(text), 3, 2)


def test_strict_frontend_accepts_only_vetted_templates():
    from qec.surface.compile import parse_program

    assert parse_program('{"qubits":1,"gates":[]}').template == 'memory'
    assert parse_program('{"qubits":1,"gates":[{"gate":"H","targets":[0]}]}').template == 'h'
    assert parse_program('{"qubits":2,"gates":[{"gate":"CX","targets":[0,1]}]}').template == 'cx'
    for text in [
        '{"qubits":1,"gates":[{"gate":"S","targets":[0]}]}',
        '{"qubits":1,"gates":[{"gate":"T","targets":[0]}]}',
        '{"qubits":1,"gates":[{"gate":"H","targets":[0]},{"gate":"H","targets":[0]}]}',
        '{"qubits":2,"gates":[{"gate":"CX","targets":[1,0]}]}',
        '{"qubits":1,"gates":[],"adaptive":true}',
        '{"qubits":true,"gates":[]}',
        '{"qubits":1,"qubits":1,"gates":[]}',
        '{"qubits":1,"gates":[{"gate":"H","targets":[false]}]}',
    ]:
        with pytest.raises(ValueError):
            parse_program(text)
