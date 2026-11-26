"""Protocol and transport tests for the GraphDecoder serial client and C firmware parser."""

import os
import pty
import select
import struct
import threading
import zlib
from contextlib import contextmanager

import pytest

from qec.surface.host import GraphDecoder, ProtocolError, encode_frame


@contextmanager
def pty_device(handler):
    """Open a PTY-backed test server that checks request CRCs and streams handler replies in 3-byte chunks."""
    master, slave = pty.openpty()
    stop = threading.Event()
    failures = []
    requests = []

    def serve():
        buffer = bytearray()
        try:
            while not stop.is_set():
                if not select.select([master], [], [], 0.02)[0]:
                    continue
                buffer.extend(os.read(master, 4096))
                while len(buffer) >= 5:
                    length = int.from_bytes(buffer[3:5], "little") + 9
                    if len(buffer) < length:
                        break
                    frame = bytes(buffer[:length])
                    del buffer[:length]
                    assert frame[0] == 0xD4
                    assert zlib.crc32(frame[:-4]) == int.from_bytes(
                        frame[-4:], "little"
                    )
                    requests.append(frame)
                    response = handler(frame)
                    if response:
                        for offset in range(0, len(response), 3):
                            os.write(master, response[offset : offset + 3])
        except BaseException as exc:  # noqa: BLE001 -- propagate thread failures to the test
            failures.append(exc)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield os.ttyname(slave), requests
    finally:
        stop.set()
        thread.join(1)
        os.close(master)
        os.close(slave)
        assert not thread.is_alive()
        if failures:
            raise failures[0]


class MailboxTestDevice:
    """In-memory serial mailbox device that tracks uploaded graphs and returns canned decode replies."""
    def __init__(self):
        self.meta = [2, 128, 512, 32, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.edges = []
        self.fail_commit = False

    def __call__(self, frame):
        """Handle one incoming mailbox frame and return the encoded reply."""
        seq, op = frame[1:3]
        data = frame[5:-4]
        payload = b""
        status = 0
        if op == 1:
            payload = struct.pack("<15I", *self.meta)
        elif op == 2:
            self.meta[4:7] = struct.unpack("<3H", data)
            self.meta[7] = 0
            self.edges = []
        elif op == 3:
            for offset in range(0, len(data), 10):
                index, a, b, mask = struct.unpack("<HHHI", data[offset : offset + 10])
                assert index == len(self.edges)
                self.edges.append((a, b, mask))
        elif op == 4:
            status = int(self.fail_commit)
            if not status:
                assert len(self.edges) == self.meta[5]
                self.meta[7] = 1
                self.meta[8] += 1
        elif op == 5:
            assert len(data) == (self.meta[4] + 7) // 8
            payload = struct.pack("<IIB", 0x80000001, 12345, 0)
        elif op == 6:
            pass
        else:
            status = 1
        return encode_frame(0x4D, seq, status, payload)


def test_real_serial_graph_upload_and_multibit_decode():
    """Check chunked graph upload, sequence numbering, and 32-bit prediction decode over a PTY."""
    device = MailboxTestDevice()
    edges = [(i % 9, 9, (1 << 31) | 1) for i in range(103)]
    with (
        pty_device(device) as (port, requests),
        GraphDecoder(port, timeout=0.3) as decoder,
    ):
        identity = decoder.identity()
        assert (
            identity.max_detectors,
            identity.max_edges,
            identity.max_observables,
        ) == (128, 512, 32)
        loaded = decoder.load_graph(9, edges, 32)
        assert (
            loaded.detectors,
            loaded.edges,
            loaded.observables,
            loaded.valid,
            loaded.generation,
        ) == (9, 103, 32, True, 1)
        result = decoder.decode(0x101)
        assert (result.prediction, result.cycles, result.decode_error) == (
            0x80000001,
            12345,
            False,
        )
        assert decoder.uploaded_edges == tuple(edges)
        assert decoder.transactions[-1]["tx"] == requests[-1]
    assert device.edges == edges
    chunks = [frame for frame in requests if frame[2] == 3]
    assert [len(frame) - 9 for frame in chunks] == [510, 510, 10]
    assert [frame[1] for frame in requests] == list(range(len(requests)))


@pytest.mark.parametrize(
    "dimensions,edges,observables",
    [
        (0, [], 1),
        (9, [(0, 10, 0)], 1),
        (9, [(1, 1, 0)], 1),
        (9, [(0, 9, 2)], 1),
        (9, [(0, 9, -1)], 32),
        (9, [(0, 9, 1.5)], 32),
        (9, [], 33),
        (129, [], 1),
        (9, [(0, 9, 0)] * 513, 1),
    ],
)
def test_invalid_graph_never_begins_upload(dimensions, edges, observables):
    """Ensure invalid graph dimensions, edges, or capacities fail validation before sending upload frames."""
    with (
        pty_device(MailboxTestDevice()) as (port, requests),
        GraphDecoder(port) as decoder,
    ):
        with pytest.raises(ValueError):
            decoder.load_graph(dimensions, edges, observables)
        assert all(frame[2] == 1 for frame in requests)
        with pytest.raises(RuntimeError, match="reload"):
            decoder.decode(0)


def test_failed_commit_disarms_previous_graph_and_abort_does_not_rearm():
    """Ensure a failed commit disarms decoding until a fresh graph is loaded, even after abort()."""
    device = MailboxTestDevice()
    with pty_device(device) as (port, _requests), GraphDecoder(port) as decoder:
        decoder.load_graph(9, [(0, 9, 1)], 32)
        device.fail_commit = True
        with pytest.raises(ProtocolError) as failure:
            decoder.load_graph(9, [(1, 9, 2)], 32)
        assert failure.value.status == 1
        decoder.abort()
        with pytest.raises(RuntimeError):
            decoder.decode(0)
        device.fail_commit = False
        decoder.load_graph(9, [(0, 9, 1)], 32)
        assert decoder.decode(0).prediction == 0x80000001


@pytest.mark.parametrize(
    "damage", ["crc", "seq", "timeout", "oversize", "magic", "status"]
)
def test_transport_errors_retain_raw_bytes_and_next_valid_identity(damage):
    """Check that protocol errors keep raw tx/rx bytes and that framing faults require resynchronization."""
    device = MailboxTestDevice()
    sent = []

    def handler(frame):
        reply = device(frame)
        if not sent:
            if damage == "crc":
                reply = reply[:-1] + bytes([reply[-1] ^ 1])
            elif damage == "seq":
                reply = encode_frame(0x4D, (frame[1] + 1) % 256, 0, reply[5:-4])
            elif damage == "timeout":
                reply = reply[:7]
            elif damage == "oversize":
                reply = b"\x4d" + frame[1:2] + b"\x00\x01\x02"
            elif damage == "magic":
                reply = encode_frame(0x3C, frame[1], 0, reply[5:-4])
            else:
                reply = encode_frame(0x4D, frame[1], 4)
        sent.append(reply)
        return reply

    with (
        pty_device(handler) as (port, requests),
        GraphDecoder(port, timeout=0.08) as decoder,
    ):
        with pytest.raises(ProtocolError) as failure:
            decoder.identity()
        assert failure.value.tx == requests[0]
        assert failure.value.rx == sent[0]
        assert decoder.transactions[0]["rx"] == sent[0]
        if damage == "status":
            assert decoder.identity().protocol == 2
            assert len(requests) == 2
        else:
            with pytest.raises(ProtocolError, match="resynchron"):
                decoder.identity()
            with pytest.raises(ProtocolError, match="resynchron"):
                decoder.resynchronize(timeout=0.02)
            with pytest.raises(ProtocolError, match="resynchron"):
                decoder.abort()
            assert len(requests) == 1


def test_identity_change_disarms_decode_before_sending_shot():
    """Ensure decode refuses to send a shot if the device's graph generation changed."""
    device = MailboxTestDevice()
    with pty_device(device) as (port, requests), GraphDecoder(port) as decoder:
        decoder.load_graph(9, [(0, 9, 0)], 32)
        device.meta[8] += 1
        with pytest.raises(ProtocolError, match="identity"):
            decoder.decode(0)
        assert all(frame[2] != 5 for frame in requests)


def test_exclusive_port_and_sequence_wrap():
    """Check that the serial port is opened exclusively and sequence bytes wrap cleanly past 255."""
    import serial

    with (
        pty_device(MailboxTestDevice()) as (port, requests),
        GraphDecoder(port, timeout=0.3) as decoder,
    ):
        with pytest.raises(serial.SerialException):
            GraphDecoder(port)
        for _ in range(258):
            decoder.identity()
    assert [frame[1] for frame in requests] == [i % 256 for i in range(258)]


def test_archive_preserves_ordered_edges_identity_and_raw_frames(tmp_path):
    """Check that save_archive records edge order, identity, and raw frames without overwriting existing files."""
    import json

    device = MailboxTestDevice()
    edges = [(2, 9, 0x80000000), (0, 2, 3), (1, 9, 0)]
    with pty_device(device) as (port, requests), GraphDecoder(port) as decoder:
        decoder.load_graph(9, edges, 32)
        decoder.decode(0)
        path = tmp_path / "capture.json"
        decoder.save_archive(path)
        archive = json.loads(path.read_text())
        assert archive["ordered_edges"] == [list(edge) for edge in edges]
        assert archive["identity"][8] == 1
        assert [
            bytes.fromhex(row["tx_hex"]) for row in archive["transactions"]
        ] == requests
        assert all(row["rx_hex"] for row in archive["transactions"])
        assert "hash" not in archive and "digest" not in archive
        with pytest.raises(FileExistsError):
            decoder.save_archive(path)


@pytest.mark.parametrize("opcode", [2, 3, 4, 6])
def test_nonempty_command_ack_is_not_success(opcode):
    """Ensure nonempty payloads on graph-control or abort ACKs raise ProtocolError and leave decode disarmed."""
    device = MailboxTestDevice()

    def handler(frame):
        reply = device(frame)
        if frame[2] == opcode:
            return encode_frame(0x4D, frame[1], 0, b"unexpected")
        return reply

    with pty_device(handler) as (port, _requests), GraphDecoder(port) as decoder:
        with pytest.raises(ProtocolError, match="ack"):
            if opcode == 6:
                decoder.abort()
            else:
                decoder.load_graph(9, [(0, 9, 0)], 32)
        with pytest.raises(RuntimeError):
            decoder.decode(0)


@pytest.mark.parametrize("change", ["cycles", 4, 5, 6, 7, 8, 9])
def test_decode_rejects_reset_or_changed_identity_after_shot(change):
    """Ensure decode raises and disarms if the reply reports zero cycles or altered post-shot metadata."""
    device = MailboxTestDevice()

    def handler(frame):
        reply = device(frame)
        if frame[2] == 5:
            if change == "cycles":
                return encode_frame(0x4D, frame[1], 0, struct.pack("<IIB", 0, 0, 0))
            device.meta[change] ^= 1
        return reply

    with (
        pty_device(handler) as (port, requests),
        GraphDecoder(port, timeout=0.3) as decoder,
    ):
        decoder.load_graph(9, [(0, 9, 0)], 32)
        with pytest.raises(ProtocolError):
            decoder.decode(0)
        with pytest.raises(RuntimeError, match="reload"):
            decoder.decode(0)
        assert sum(frame[2] == 5 for frame in requests) == 1


@pytest.mark.parametrize("delayed_opcode", [1, 5])
def test_late_complete_reply_requires_bounded_resynchronization_before_any_write(
    delayed_opcode, tmp_path
):
    """Check that a timed-out request blocks writes until resynchronize() drains the late reply."""
    device = MailboxTestDevice()
    release = threading.Event()
    entered = threading.Event()

    def handler(frame):
        if frame[2] == delayed_opcode and not entered.is_set():
            entered.set()
            release.wait(0.4)
        return device(frame)

    with (
        pty_device(handler) as (port, requests),
        GraphDecoder(port, timeout=0.05) as decoder,
    ):
        if delayed_opcode == 5:
            decoder.load_graph(9, [(0, 9, 0)], 32)
        with pytest.raises(ProtocolError, match="timeout"):
            decoder.decode(0) if delayed_opcode == 5 else decoder.identity()
        assert entered.is_set()
        before = len(requests)

        for operation in [
            decoder.identity,
            decoder.abort,
            lambda: decoder.load_graph(9, [(0, 9, 0)], 32),
        ]:
            with pytest.raises(ProtocolError, match="resynchron"):
                operation()
        assert len(requests) == before
        with pytest.raises(ProtocolError, match="resynchron"):
            decoder.resynchronize(timeout=0.02)
        assert len(requests) == before
        release.set()
        decoder.resynchronize(timeout=0.5)
        import json

        capture = tmp_path / "resync.json"
        decoder.save_archive(capture)
        recovered = json.loads(capture.read_text())["transactions"][-1]
        assert recovered["rx_hex"] == ""
        late = bytes.fromhex(recovered["resync_rx_hex"])
        assert late[0] == 0x4D and late[1] == requests[-1][1]
        assert zlib.crc32(late[:-4]) == int.from_bytes(late[-4:], "little")
        with pytest.raises(RuntimeError, match="reload"):
            decoder.decode(0)
        assert decoder.identity().protocol == 2
        decoder.load_graph(9, [(0, 9, 0)], 32)
        assert decoder.decode(0).cycles > 0
        assert [frame[1] for frame in requests] == list(range(len(requests)))


def test_standard_crc_and_request_layout():
    """Verify CRC-32 against the standard check vector and confirm little-endian request framing."""
    assert zlib.crc32(b"123456789") == 0xCBF43926
    header = b"\xd4\x07\x02\x06\x00" + struct.pack("<HHH", 9, 2, 32)
    assert encode_frame(0xD4, 7, 2, header[5:]) == header + struct.pack(
        "<I", zlib.crc32(header)
    )


def test_native_parser_harness_under_sanitizers(tmp_path):
    """Compile and run the C firmware parser test harness under ASan and UBSan."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    binary = tmp_path / "runtime-parser"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-g",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            "-fno-pie",
            "-no-pie",
            str(root / "fpga/vitis/tests/test_firmware.c"),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True, timeout=5)


@pytest.mark.parametrize("detectors", [1, 9, 17, 128])
def test_variable_syndromes_using_explicit_core_algorithm_test_device(detectors):
    """Check decoding across 1-to-128-detector syndromes and reject out-of-range bits before sending."""
    from qec.surface.decoder import decode as test_device_algorithm

    class CoreAlgorithmTestDevice(MailboxTestDevice):
        """Mailbox device that computes shot replies with the Python decoder."""
        def __call__(self, frame):
            if frame[2] != 5:
                return super().__call__(frame)
            syndrome = int.from_bytes(frame[5:-4], "little")
            result = test_device_algorithm(self.meta[4], self.edges, syndrome)
            payload = struct.pack("<IIB", result["prediction"], 77, result["error"])
            return encode_frame(0x4D, frame[1], 3 if result["error"] else 0, payload)

    edges = [(i, detectors, 1 << (i % 32)) for i in range(detectors)]
    with (
        pty_device(CoreAlgorithmTestDevice()) as (port, requests),
        GraphDecoder(port) as decoder,
    ):
        decoder.load_graph(detectors, edges, 32)
        for syndrome in (0, 1, 1 << (detectors - 1), (1 << detectors) - 1):
            expected = test_device_algorithm(detectors, edges, syndrome)
            assert decoder.decode(syndrome).prediction == expected["prediction"]
        before = len(requests)
        with pytest.raises(ValueError):
            decoder.decode(1 << detectors)
        assert len(requests) == before
        decoder.abort()
        assert decoder.decode(0).prediction == 0


@pytest.mark.parametrize("field", [4, 5, 6, 7, 8])
def test_wrong_graph_readback_never_enables_decode(field):
    """Ensure a metadata readback mismatch after commit raises ProtocolError and blocks decoding."""
    device = MailboxTestDevice()

    def handler(frame):
        reply = device(frame)
        if frame[2] == 4:
            device.meta[field] ^= 1
        return reply

    with pty_device(handler) as (port, requests), GraphDecoder(port) as decoder:
        with pytest.raises(ProtocolError, match="readback"):
            decoder.load_graph(9, [(0, 9, 0)], 32)
        with pytest.raises(RuntimeError):
            decoder.decode(0)
        assert not any(frame[2] == 5 for frame in requests)


def test_uncertain_completed_decode_is_never_retried():
    """Ensure a truncated decode reply is never automatically retried and blocks writes until resync."""
    device = MailboxTestDevice()

    def handler(frame):
        reply = device(frame)
        return reply[:8] if frame[2] == 5 else reply

    with (
        pty_device(handler) as (port, requests),
        GraphDecoder(port, timeout=0.05) as decoder,
    ):
        decoder.load_graph(9, [(0, 9, 0)], 32)
        with pytest.raises(ProtocolError, match="timeout") as failure:
            decoder.decode(0)
        assert len(failure.value.rx) == 8
        with pytest.raises(RuntimeError):
            decoder.decode(0)
        assert sum(frame[2] == 5 for frame in requests) == 1
        before = len(requests)
        with pytest.raises(ProtocolError, match="resynchron"):
            decoder.abort()
        with pytest.raises(ProtocolError, match="resynchron"):
            decoder.load_graph(9, [(0, 9, 0)], 32)
        assert len(requests) == before


def test_platform_header_entrypoint_runs_actual_firmware(tmp_path):
    """Compile fpga/vitis/src/main.c against a mock platform header and verify its identity reply."""
    import subprocess
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "fpga/vitis/src/main.c"
    frame = encode_frame(0xD4, 42, 1)
    header = tmp_path / "qec_test_platform.h"
    header.write_text(
        """
#include <stdlib.h>
#include <assert.h>
static uint32_t control;
static unsigned seen;
static unsigned cursor;
static unsigned clock_ms;
static const uint8_t input[] = {"""
        + ",".join(str(b) for b in frame)
        + """};
static void qec_platform_init(void) {}
static void qec_platform_write_control(void *u, uint32_t value)
{
    (void)u;
    control = value;
}
static uint32_t qec_platform_read_status(void *u)
{
    (void)u;
    unsigned index = (control >> 16) & 255;
    return (control & 0x80000000u) | (index == 0 ? 2u : 0u);
}
static uint32_t qec_platform_now_ms(void *u)
{
    (void)u;
    return clock_ms++;
}
static int qec_platform_read_byte(void)
{
    if (cursor == sizeof(input)) {
        exit(seen == 1 ? 0 : 1);
    }
    return input[cursor++];
}
static void qec_platform_emit(void *u, const uint8_t *data, size_t length)
{
    (void)u;
    assert(length == 69 && data[0] == 0x4d && data[1] == 42);
    assert(data[2] == 0 && data[5] == 2);
    assert(qec_crc32(data, length - 4) == get32(data + length - 4));
    seen++;
}
"""
    )
    binary = tmp_path / "firmware-platform"
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-g",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            "-fno-pie",
            "-no-pie",
            '-DQEC_PLATFORM_HEADER="' + str(header) + '"',
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    subprocess.run([str(binary)], check=True, timeout=5)
