"""End-to-end PTY serial tests for EditorLab memory and custom-circuit runs."""

import struct
from pathlib import Path

import pytest

from qec.surface.decoder import decode
from qec.surface.engine import EditorLab
from qec.surface.host import encode_frame
from qec.tests.test_host import MailboxTestDevice, pty_device


class OracleDevice(MailboxTestDevice):
    """Mailbox test device that answers decode requests using the Python reference decoder."""
    def __call__(self, frame):
        """Decode syndrome frames in software and delegate all other opcodes."""
        if frame[2] == 5:
            syndrome = int.from_bytes(frame[5:-4], "little")
            result = decode(self.meta[4], self.edges, syndrome)
            return encode_frame(
                0x4D,
                frame[1],
                0,
                struct.pack("<IIB", result["prediction"], 12345, result["error"]),
            )
        return super().__call__(frame)


def test_memory_uploads_actual_graph_on_every_run_and_changes_dimensions():
    """Check that layout() avoids serial I/O and each memory run uploads its current graph over PTY."""
    device = OracleDevice()
    with pty_device(device) as (port, requests):
        lab = EditorLab(port)
        settings = lab.layout()["run_defaults"]
        assert not requests
        result = lab.run(settings)
        assert result["source"] == "FPGA"
        assert result["hardware"]["protocol"] == "graph-v2"
        assert result["hardware"]["cycles"] == 12345
        assert result["prediction"] == result["reference_prediction"]
        assert result["experiment"]["compiled"]["edges"] == [
            list(e) for e in device.edges
        ]
        settings.update(rounds=4)
        settings["faults"] = [{"tick": 8, "qubit": 1, "pauli": "X"}]
        other = lab.run(settings)
        assert other["experiment"]["compiled"]["counts"]["detectors"] == 32
        assert other["prediction"] == other["reference_prediction"]
        assert len(other["trace"]) == len(other["layout"]["ticks"])
        assert sum(frame[2] == 4 for frame in requests) == 2


@pytest.mark.parametrize(
    "name,qubits", [("phase_bell", 2), ("two_repetition_echo", 6), ("bit31", 1)]
)
def test_general_editor_uses_real_serial_graph_transactions(name, qubits):
    """Check custom-circuit graph uploads and decode replies over PTY, including unsigned observable bit 31."""
    text = (
        "R 0\nX_ERROR(1) 0\nM 0\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(31) rec[-1]"
        if name == "bit31"
        else (Path(__file__).parent / f"fixtures/bare_{name}.stim").read_text()
    )
    device = OracleDevice()
    with pty_device(device) as (port, requests):
        response = EditorLab(port).circuit_run(
            {"circuit": text, "reference": None, "seed": 1, "added_noise": 0}
        )
        assert len(response["layout"]["data"]) == qubits
        assert response["result"]["hardware"]["cycles"] == 12345
        assert response["experiment"]["compiled"]["edges"] == [
            list(e) for e in device.edges
        ]
        assert sum(frame[2] == 4 for frame in requests) == 1
        if name == "bit31":
            assert (
                response["result"]["prediction"]
                == response["result"]["observable"]
                == 2147483648
            )
