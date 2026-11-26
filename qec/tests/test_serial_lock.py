"""Tests for serial port lock detection in `qec.surface.host`, ensuring existing locks are respected and never deleted."""

import os

import pytest

from qec.surface import host


def test_live_lock_is_reported(tmp_path):
    """An active PID lock file is detected and left intact on disk."""
    lock = tmp_path / "LCK..ttyUSB1"
    lock.write_text(f"{os.getpid():10d}\n")
    assert host.serial_lock_owner("/dev/ttyUSB1", (tmp_path,)) == os.getpid()
    assert lock.exists()


def test_stale_or_malformed_lock_is_not_removed(tmp_path, monkeypatch):
    """Stale PIDs and malformed lock files are ignored without deleting or modifying the file."""
    lock = tmp_path / "LCK..ttyUSB1"
    lock.write_text("12345\n")

    def missing(pid, signal):
        raise ProcessLookupError

    monkeypatch.setattr(host.os, "kill", missing)
    assert host.serial_lock_owner("/dev/ttyUSB1", (tmp_path,)) is None
    lock.write_text("bad lock\n")
    assert host.serial_lock_owner("/dev/ttyUSB1", (tmp_path,)) is None
    assert lock.read_text() == "bad lock\n"


def test_monitor_lock_rejects_before_serial_open(monkeypatch):
    """A live serial monitor lock raises ProtocolError with the owner PID before pySerial opens the port."""
    monkeypatch.setattr(host, "serial_lock_owner", lambda port: 12345)

    def forbidden(*args, **kwargs):
        pytest.fail("serial opened despite another reader")

    monkeypatch.setattr(host.serial, "Serial", forbidden)
    with pytest.raises(host.ProtocolError, match="12345.*minicom"):
        host.GraphDecoder("/dev/ttyUSB1")
