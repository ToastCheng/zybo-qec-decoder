"""Tests for experimental d=3/d=5 frontier cycle-count expectations and wire-frame parsing."""
import importlib.util
from pathlib import Path
import struct

import pytest
from qec.surface.host import encode_frame

ROOT = Path(__file__).resolve().parents[2]

spec_cap = importlib.util.spec_from_file_location(
    'frontier_capture', ROOT / 'fpga/experimental/frontier/capture_curves.py'
)
capture = importlib.util.module_from_spec(spec_cap)
spec_cap.loader.exec_module(capture)

spec_ver = importlib.util.spec_from_file_location(
    'frontier_verify', ROOT / 'fpga/experimental/frontier/verify_curves.py'
)
verify = importlib.util.module_from_spec(spec_ver)
spec_ver.loader.exec_module(verify)


def test_frontier_cycle_schedule_matches_rtl():
    """Check that expected_frontier_cycles matches RTL cycle counts for empty and nonempty syndromes."""
    assert capture.expected_frontier_cycles(5, 102, 0) == 1
    assert capture.expected_frontier_cycles(5, 102, 1) == 5110
    assert capture.expected_frontier_cycles(11, 350, 1) == 1076414


def test_verify_parse_frame_checks_crc_and_magic():
    """Check that parse_frame decodes a valid reply frame and rejects a corrupted CRC."""
    frame = encode_frame(0x4D, 7, 0, struct.pack('<IIB', 1, 5110, 0))
    seq, status, payload = verify.parse_frame(frame.hex(), 0x4D)
    assert (seq, status) == (7, 0)
    assert struct.unpack('<IIB', payload) == (1, 5110, 0)
    damaged = bytearray(frame)
    damaged[-1] ^= 1
    with pytest.raises(AssertionError):
        verify.parse_frame(bytes(damaged).hex(), 0x4D)
