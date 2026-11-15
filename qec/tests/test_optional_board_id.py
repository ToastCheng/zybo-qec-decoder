"""Physical runners accept a serial port without a board-label argument."""

from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("runner", ["qec/surface/host.py", "qec/hardware_run.py"])
@pytest.mark.parametrize("board_args", [[], ["--board-id", "optional-label"]])
def test_board_label_is_optional(runner, board_args, tmp_path):
    missing_port = tmp_path / "missing-uart"
    assert not missing_port.exists()
    result = subprocess.run(
        [
            sys.executable,
            runner,
            "--port",
            str(missing_port),
            "--out",
            str(tmp_path / "capture"),
            "--shots",
            "1",
            *board_args,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
    )
    # A nonexistent path exercises CLI parsing and reaches serial open without
    # contacting hardware. Missing CLI arguments would instead return code 2.
    assert result.returncode == 1, result.stderr
    assert "could not open port" in result.stderr
    assert str(missing_port) in result.stderr
