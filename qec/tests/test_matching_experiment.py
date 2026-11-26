"""Tests for vector-file parsing and truth-label validation in the experimental matching capture tool."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('matching_capture', ROOT / 'fpga/experimental/matching/capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def test_replay_accepts_explicit_real_population(tmp_path):
    """Check that read_vectors accepts an explicit real-shot count and keeps unlabeled diagnostic rows."""
    vectors = tmp_path / 'vectors.txt'
    vectors.write_text('3\n000000 000000000000000 0 0 0 0\n000001 000000000000001 1 0 0 1\nffffff 000000000000002 0 1 0 -1\n')
    rows = capture.read_vectors(vectors, 2)
    assert len(rows) == 3
    assert rows[1][0] == 1
    assert rows[1][-1] == 1
    assert rows[2][-1] == -1


def test_replay_rejects_false_real_truth_before_serial(tmp_path):
    """Ensure read_vectors rejects a row in the real-shot prefix when its truth label is missing."""
    vectors = tmp_path / 'vectors.txt'
    vectors.write_text('1\n000001 000000000000001 1 0 0 -1\n')
    with pytest.raises(ValueError, match='truth'):
        capture.read_vectors(vectors, 1)
