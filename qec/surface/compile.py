"""Compile only vetted memory, temporal-H and lattice-surgery-CX templates.

This is not an arbitrary Clifford compiler. See README for the strict JSON IR.
Optional TQEC imports are deferred so input and hardware rejection work without it.
"""
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class Program:
    template: str
    qubits: int
    source: dict


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def parse_program(text):
    """Reject extra fields, implicit controls, and all unvalidated compositions."""
    obj = json.loads(text, object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or set(obj) != {'qubits', 'gates'}:
        raise ValueError('program requires exactly qubits and gates')
    n, gates = obj['qubits'], obj['gates']
    if type(n) is not int or not isinstance(gates, list):
        raise ValueError('qubits must be an integer; gates must be a list')
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != {'gate', 'targets'}:
            raise ValueError('each gate requires exactly gate and targets')
        if (not isinstance(gate['targets'], list)
                or any(type(t) is not int for t in gate['targets'])):
            raise ValueError('targets must be a list of integer qubit indices')
    if n == 1 and gates == []:
        template = 'memory'
    elif n == 1 and gates == [{'gate': 'H', 'targets': [0]}]:
        template = 'h'
    elif n == 2 and gates == [{'gate': 'CX', 'targets': [0, 1]}]:
        template = 'cx'
    else:
        raise ValueError('unsupported logical program: only one-qubit memory, H 0, '
                         'or CX 0 1 is vetted; S/T, adaptive gates and compositions are unsupported')
    return Program(template, n, obj)


def checked_graph(dem, detectors, observables):
    """Preserve each graphlike component, or fail before PyMatching can merge it.

    Repeated equal signatures may be probabilistically merged by PyMatching.
    Distinct observable masks for equal endpoints cannot be represented by this
    UF graph and must not be silently projected. Separator correlations remain
    in the archived DEM, but the decoders use the independent-edge approximation.
    """
    import pymatching
    import stim

    signatures = {}
    for instruction in dem.flattened():
        if instruction.type != 'error':
            continue
        ds, mask = set(), 0
        for target in instruction.targets_copy() + [stim.target_separator()]:
            if target.is_separator():
                if not ds and mask:
                    raise ValueError('detectorless logical component cannot be represented')
                if len(ds) > 2:
                    raise ValueError('non-graphlike component cannot be represented')
                if ds:
                    endpoints = tuple(sorted(ds | ({detectors} if len(ds) == 1 else set())))
                    if endpoints in signatures and signatures[endpoints] != mask:
                        raise ValueError('ambiguous endpoint observable masks cannot be represented')
                    signatures[endpoints] = mask
                ds, mask = set(), 0
            elif target.is_relative_detector_id():
                if not 0 <= target.val < detectors:
                    raise ValueError('detector index outside graph')
                ds.symmetric_difference_update([target.val])
            elif target.is_logical_observable_id():
                if not 0 <= target.val < observables:
                    raise ValueError('observable index outside graph')
                mask ^= 1 << target.val
    matching = pymatching.Matching.from_detector_error_model(dem)
    matching.ensure_num_fault_ids(observables)
    edges = sorted((min(a, detectors if b is None else b),
                    max(a, detectors if b is None else b),
                    sum(1 << i for i in data['fault_ids']))
                   for a, b, data in matching.edges())
    expected = sorted((a, b, mask) for (a, b), mask in signatures.items())
    if edges != expected:
        raise ValueError('PyMatching graph projection lost or changed DEM components')
    return edges, matching


def compile_program(program, out, *, basis='z', distance=3, noise=.001,
                    shots=256, seed=123):
    """Publish a fresh self-contained artifact directory; never overwrite a run."""
    import math

    if not isinstance(program, Program) or parse_program(json.dumps(program.source)) != program:
        raise ValueError('program must be produced by parse_program')
    if basis not in ('x', 'z') or type(distance) is not int or distance not in (3, 5):
        raise ValueError('only x/z basis and vetted distances 3 or 5 are supported')
    if (type(noise) not in (int, float) or not math.isfinite(noise)
            or not 0 <= noise <= .75):
        raise ValueError('noise must be finite and in [0, 0.75]')
    if type(shots) is not int or shots < 1:
        raise ValueError('shots must be a positive integer')
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError('seed must be an unsigned 64-bit integer')

    import hashlib
    from importlib import metadata
    from pathlib import Path
    import platform
    import shutil
    import tempfile

    import numpy as np
    import pymatching
    import stim
    from tqec import BlockGraph, NoiseModel, compile_block_graph
    from tqec.compile.convention import FIXED_BULK_CONVENTION
    from tqec.compile.detectors.database import DetectorDatabase
    from tqec.utils.position import Position3D
    from qec.surface.decoder import decode

    out = Path(out)
    if out.exists():
        raise FileExistsError(f'output already exists: {out}')
    if program.template == 'memory':
        ideal = stim.Circuit.generated('surface_code:rotated_memory_' + basis,
                                       distance=distance, rounds=distance)
        logical = dict(generator='stim.surface_code:rotated_memory_' + basis,
                       rounds=distance, port_order=['In', 'Out'],
                       observable_stabilizers=[basis.upper() * 2])
    else:
        if program.template == 'cx':
            from tqec.gallery.cnot import cnot
            from tqec.utils.enums import Basis
            g = cnot(Basis(basis.upper()))
        else:
            g = BlockGraph('Temporal H')
            a = g.add_cube(Position3D(0, 0, 0), 'XZZ' if basis == 'z' else 'XZX')
            b = g.add_cube(Position3D(0, 0, 1), 'ZXX' if basis == 'z' else 'ZXZ')
            g.add_pipe(a, b)
        surfaces = g.find_correlation_surfaces()
        ports = ([Position3D(0, 0, 0), Position3D(1, 1, 0),
                  Position3D(0, 0, 3), Position3D(1, 1, 3)] if program.template == 'cx'
                 else [Position3D(0, 0, 0), Position3D(0, 0, 1)])
        logical = dict(block_graph=g.to_dict(),
                       port_order=(['In_Control', 'In_Target', 'Out_Control', 'Out_Target']
                                   if program.template == 'cx' else ['In', 'Out']),
                       observable_stabilizers=[s.external_stabilizer(ports) for s in surfaces],
                       correlation_surfaces=[s.to_dict() for s in surfaces])
        compiled = compile_block_graph(g, FIXED_BULK_CONVENTION, surfaces)
        ideal = compiled.to_layer_tree().generate_circuit(
            (distance - 1) // 2, detector_database=DetectorDatabase(), database_path=None)
    reference_noise = noise if noise else .001
    if program.template == 'memory':
        def memory_at(p):
            return stim.Circuit.generated('surface_code:rotated_memory_' + basis,
                distance=distance, rounds=distance, after_clifford_depolarization=p,
                before_round_data_depolarization=p, before_measure_flip_probability=p,
                after_reset_flip_probability=p)
        noisy = memory_at(noise)
        reference = noisy if noise else memory_at(reference_noise)
    else:
        noisy = NoiseModel.uniform_depolarizing(noise).noisy_circuit(ideal)
        reference = (noisy if noise else
                     NoiseModel.uniform_depolarizing(reference_noise).noisy_circuit(ideal))
    dem = noisy.detector_error_model(decompose_errors=True)
    reference_dem = reference.detector_error_model(decompose_errors=True)
    n, width = ideal.num_detectors, ideal.num_observables
    edges, matching = checked_graph(reference_dem, n, width)
    d0, o0 = ideal.compile_detector_sampler(seed=seed).sample(shots, separate_observables=True)
    if d0.any() or o0.any():
        raise ValueError('non-deterministic ideal detector or logical correlation')
    det, obs = noisy.compile_detector_sampler(seed=seed).sample(shots, separate_observables=True)
    mwpm = matching.decode_batch(det)
    uf_failures = 0
    evidence = []
    for shot_index, (bits, truth) in enumerate(zip(det, obs)):
        syndrome = sum(int(v) << i for i, v in enumerate(bits))
        result = decode(n, edges, syndrome)
        residual = syndrome
        for index in result['correction_edges']:
            for endpoint in edges[index][:2]:
                if endpoint < n:
                    residual ^= 1 << endpoint
        if result['error'] or residual:
            raise ValueError('UF correction failed detector-boundary verification')
        expected = sum(int(v) << i for i, v in enumerate(truth))
        uf_failures += result['prediction'] != expected
        evidence.append(dict(syndrome_hex=hex(syndrome), observable_mask=expected,
                             uf_prediction=result['prediction'],
                             mwpm_prediction=sum(int(v) << i for i, v in enumerate(mwpm[shot_index]))))
    graph = dict(detectors=n, observables=width, edges=edges,
                 boundary_vertex=n, detector_order='Stim detector index, little-endian',
                 observable_order='Stim observable index; bit i = L_i',
                 decoder='serial-half-edge-union-find-peeling-unweighted')
    texts = {'ideal.stim': str(ideal) + '\n', 'noisy.stim': str(noisy) + '\n',
             'model.dem': str(dem) + '\n', 'reference.dem': str(reference_dem) + '\n',
             'graph.json': json.dumps(graph, indent=2) + '\n',
             'logical.json': json.dumps(logical, indent=2) + '\n',
             'shots.json': json.dumps(evidence, indent=2) + '\n',
             'program.json': json.dumps(program.source, indent=2) + '\n'}
    if width == 1:
        vb = n.bit_length()
        texts['graph.mem'] = ''.join(f'{a | (b << vb) | (mask << (2 * vb)):0{(2 * vb + 4) // 4}x}\n'
                                     for a, b, mask in edges)
    manifest = dict(
        schema_version=1, template=program.template, basis=basis, distance=distance,
        k=(distance - 1) // 2, noise=noise, reference_noise=reference_noise, seed=seed,
        convention='fixed_bulk' if program.template != 'memory' else 'Stim rotated memory',
        noise_model=('stim.generated four-location memory noise' if program.template == 'memory'
                     else 'tqec.uniform_depolarizing'),
        counts=dict(qubits=ideal.num_qubits, detectors=n, observables=width, edges=len(edges)),
        shortest_graphlike_error=len(reference.shortest_graphlike_error()),
        metrics=dict(shots=shots, ideal_detector_flips=int(d0.sum()),
                     ideal_observable_flips=int(o0.sum()), uf_syndrome_failures=0,
                     uf_logical_failures=int(uf_failures),
                     mwpm_logical_failures=int(np.any(mwpm != obs, axis=1).sum())),
        versions=dict(python=platform.python_version(), stim=stim.__version__,
                      pymatching=pymatching.__version__, tqec=metadata.version('tqec'),
                      tqec_direct_url=metadata.distribution('tqec').read_text('direct_url.json'),
                      compiler_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      uf_sha256=hashlib.sha256(Path(__file__).with_name('decoder.py').read_bytes()).hexdigest()),
        hardware=dict(compatible_with_loaded_image=False, rom_exported=width == 1,
                      vertex_bits=n.bit_length(), prediction_bits=width,
                      reason='requires graph-specific bitstream and matching firmware; no board access'),
        limitations=['restricted templates, not arbitrary Clifford or composition',
                     'UF is unweighted; MWPM ignores decomposed inter-component correlations',
                     'graphlike distance is not a proof against every correlated fault',
                     'logical outputs are commuting correlation parities, not a running Pauli frame',
                     'software simulation only; no physical correction or adaptive feedback'],
        sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in texts.items()})
    texts['manifest.json'] = json.dumps(manifest, indent=2) + '\n'
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.qec-compile-', dir=out.parent))
    try:
        for name, text in texts.items():
            (temporary / name).write_text(text, encoding='utf-8')
        temporary.rename(out)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def main(argv=None):
    """Software-only compiler entry point; reject serial before any I/O to a board."""
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('logical_circuit', type=Path, help='strict logical JSON gate list')
    parser.add_argument('--basis', choices=['x', 'z'], default='z', help='logical input preparation basis')
    scale = parser.add_mutually_exclusive_group()
    scale.add_argument('--distance', type=int, choices=[3, 5], help='vetted code distance (default 3)')
    scale.add_argument('--k', type=int, choices=[1, 2], help='TQEC scale, distance = 2*k+1')
    parser.add_argument('--noise', type=float, default=.001)
    parser.add_argument('--shots', type=int, default=256)
    parser.add_argument('--seed', type=int, default=123)
    parser.add_argument('--out', type=Path, required=True, help='new output directory (must not exist)')
    parser.add_argument('--port', help='not supported; never opens serial')
    args = parser.parse_args(argv)
    if args.port is not None:
        parser.error('compiler serial execution is disabled: requires a matching graph-specific image '
                     'and firmware; the existing memory image is not valid for H/CX. '
                     'Use qec.surface.example separately for the existing memory board example.')
    distance = args.distance if args.distance is not None else 2 * (args.k or 1) + 1
    try:
        program = parse_program(args.logical_circuit.read_text(encoding='utf-8'))
        manifest = compile_program(program, args.out, basis=args.basis, distance=distance,
                                   noise=args.noise, shots=args.shots, seed=args.seed)
    except ImportError as exc:
        parser.error(f'optional compiler dependency missing: {exc}; '
                     'install qec/requirements-compiler.txt in a Python 3.12 environment')
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
