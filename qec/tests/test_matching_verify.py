"""Tests for variable-size archive verification in the experimental matching verifier."""
import csv
import importlib.util
import json
from pathlib import Path
import struct

from qec.surface.host import encode_frame

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('matching_verify', ROOT / 'fpga/experimental/matching/verify.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def test_verifier_uses_explicit_population_not_old_1050_constant(tmp_path):
    """Check that verify() handles a 514-shot synthetic archive and separates real and diagnostic counts."""
    count = 514
    rows = ['000001 000000000000001 0 0 0 ' + ('0' if i == 0 else '-1') for i in range(count)]
    (tmp_path / 'vectors.txt').write_text(str(count) + '\n' + '\n'.join(rows) + '\n')
    with (tmp_path / 'rtl-latency.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=['matching_cycles', 'uf_cycles'])
        writer.writeheader()
        writer.writerows({'matching_cycles': 512, 'uf_cycles': 5} for _ in rows)
    for name, cycles in [('uf', 5), ('matching', 512)]:
        path = tmp_path / name
        path.mkdir()
        records = []
        shots = []
        if name == 'matching':
            records.append(dict(tx_hex=encode_frame(0xD4, 0, 3).hex(),
                                rx_hex=encode_frame(0x4D, 0, 2).hex()))
        for i in range(count):
            seq = len(records) % 256
            records.append(dict(tx_hex=encode_frame(0xD4, seq, 5, b'\x01\0\0').hex(),
                                rx_hex=encode_frame(0x4D, seq, 0, struct.pack('<IIB', 0, cycles, 0)).hex()))
            shots.append(dict(syndrome=1, prediction=0, cycles=cycles))
        (path / 'wire.json').write_text(json.dumps(dict(transactions=records)))
        (path / 'results.json').write_text(json.dumps(dict(real_shots=1, shots=shots)))
    summary = verify.verify(tmp_path)
    assert summary['matching']['verified_shots'] == count
    assert summary['matching']['populations']['real']['count'] == 1
    assert summary['matching']['populations']['diagnostic']['count'] == 1
