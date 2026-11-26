"""CLI tests for the `python -m qec.surface.web` entry point."""

import subprocess
import sys


def test_web_command_has_one_interface_and_serial_option():
    """Web CLI help lists `--port` and `--serial-port` and rejects the removed `--legacy-fixed-image` flag."""
    command = [sys.executable, "-m", "qec.surface.web"]
    result = subprocess.run(
        command + ["--help"], capture_output=True, text=True, check=True
    )
    assert "--port" in result.stdout and "--serial-port" in result.stdout
    assert "legacy" not in result.stdout
    rejected = subprocess.run(
        command + ["--legacy-fixed-image"], capture_output=True, text=True, check=False
    )
    assert rejected.returncode == 2
    assert "unrecognized arguments" in rejected.stderr
