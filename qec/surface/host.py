"""UART host driver for the FPGA decoder's D4/4D version-2 serial protocol.

Handles exclusive serial access, CRC32 framing, graph uploads with readback
verification, and per-shot hardware decoding for ``run.py`` and
``partition.py``.

Wire frame layout (little-endian):
- Header (5 bytes, ``<BBBH``): magic (``0xD4`` host request, ``0x4D`` device
  reply), wrapping 8-bit sequence number, request opcode or reply status byte
  (``0`` means OK), and uint16 payload length (at most 512 bytes).
- Payload: 0 to 512 bytes.
- Trailer (4 bytes, ``<I``): IEEE CRC32 over the header (including magic) and
  payload.
"""

import os
import struct
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

import serial


def encode_frame(magic, seq, code, payload=b""):
    """Build a CRC32-protected protocol frame from header fields and payload.

    Packs ``(magic, seq, code, len(payload))`` as ``<BBBH``, appends
    ``payload``, and finishes with a little-endian IEEE CRC32 over the full
    header (including ``magic``) and payload. Raises ``ValueError`` if
    ``payload`` exceeds 512 bytes.
    """
    if len(payload) > 512:
        raise ValueError("payload exceeds 512 bytes")
    data = struct.pack("<BBBH", magic, seq, code, len(payload)) + payload
    return data + struct.pack("<I", zlib.crc32(data))


class ProtocolError(IOError):
    """Raised when a UART transaction fails framing, CRC, status, or readback checks.

    Carries the raw ``tx`` and ``rx`` wire bytes captured during the exchange
    along with any nonzero device ``status`` byte so callers and archives can
    inspect what happened on the wire.
    """

    def __init__(self, message, tx=b"", rx=b"", status=None):
        """Attach captured request/response bytes and an optional device status."""
        super().__init__(message)
        self.tx = tx
        self.rx = rx
        self.status = status


@dataclass(frozen=True)
class DecoderIdentity:
    """Parsed view of the 15 metadata words returned by the IDENTITY command.

    Exposes both the fixed FPGA image capacities (``max_detectors``,
    ``max_edges``, ``max_observables``) and the state of the currently loaded
    graph (``detectors``, ``edges``, ``observables``, ``valid``, and the 32-bit
    ``generation`` counter).
    """

    words: tuple

    protocol = property(
        lambda self: self.words[0],
        doc="Protocol metadata version reported by the runtime image.",
    )
    max_detectors = property(
        lambda self: self.words[1],
        doc="Maximum detector count the FPGA image supports, excluding the boundary.",
    )
    max_edges = property(
        lambda self: self.words[2],
        doc="Maximum number of ordered edges the FPGA image supports.",
    )
    max_observables = property(
        lambda self: self.words[3], doc="Maximum logical observable width in bits."
    )
    detectors = property(
        lambda self: self.words[4], doc="Detector count of the currently loaded graph."
    )
    edges = property(
        lambda self: self.words[5], doc="Edge count of the currently loaded graph."
    )
    observables = property(
        lambda self: self.words[6],
        doc="Logical observable width in bits of the currently loaded graph.",
    )
    valid = property(
        lambda self: bool(self.words[7]),
        doc="Whether the device reports a valid committed graph.",
    )
    generation = property(
        lambda self: self.words[8] | self.words[9] << 16,
        doc="32-bit graph generation counter assembled from low and high 16-bit words.",
    )


@dataclass(frozen=True)
class DecoderReply:
    """Decoded result returned for a single FPGA shot.

    Holds the logical observable bitmask (``prediction``), the measured FPGA
    core cycle count (``cycles``), and the device's ``decode_error`` flag.
    ``GraphDecoder.decode`` raises ``ProtocolError`` whenever ``decode_error``
    is set instead of returning a failed reply.
    """

    prediction: int
    cycles: int
    decode_error: bool


def serial_lock_owner(port, directories=(Path("/run/lock"), Path("/var/lock"))):
    """Return the PID of a live process holding a UUCP lock file for ``port``.

    Checks ``LCK..<name>`` under ``directories`` for both the given port name
    and its resolved symlink target without modifying any lock files. Uses
    ``os.kill(pid, 0)`` to check liveness (treating ``PermissionError`` as alive
    under another user) and returns ``None`` if no live lock is found.
    """
    names = {Path(port).name, Path(port).resolve().name}
    for directory in directories:
        for name in names:
            try:
                with (Path(directory) / ("LCK.." + name)).open("rb") as stream:
                    pid = int(stream.read(64).strip())
                if pid <= 0:
                    continue
                try:
                    os.kill(pid, 0)
                except PermissionError:
                    pass
                return pid
            except (OSError, ValueError):
                continue
    return None


class GraphDecoder:
    """Thread-safe UART client for uploading graphs and decoding shots on the FPGA.

    Talks directly to the runtime image over an exclusive serial port with no
    silent fallback to software decoding.
    """

    def __init__(self, port, *, baudrate=115200, timeout=1.0):
        """Open ``port`` exclusively after verifying no live serial monitor holds it.

        ``timeout`` sets the per-transaction deadline in seconds and must be
        positive. No graph is loaded on open; callers must call ``load_graph``
        before ``decode``.
        """
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        owner = serial_lock_owner(port)
        if owner is not None:
            raise ProtocolError(
                f"Serial port {port} is locked by process {owner}. Close minicom or the other serial monitor, then press Run."
            )
        self.timeout = timeout
        self._lock = threading.RLock()
        self._seq = 0
        self._loaded = None
        self._pending = None
        self.uploaded_edges = ()
        self.transactions = []
        self._serial = serial.Serial(
            port,
            baudrate,
            timeout=min(timeout, 0.02),
            write_timeout=timeout,
            exclusive=True,
        )

    def close(self):
        """Close the serial port and forget the cached graph identity."""
        with self._lock:
            self._serial.close()
            self._loaded = None

    def __enter__(self):
        """Return this decoder (the serial port is opened during ``__init__``)."""
        return self

    def __exit__(self, *exc):
        """Close the serial port without suppressing exceptions."""
        self.close()

    def resynchronize(self, *, timeout=None):
        """Drain and validate an in-flight reply before allowing new requests.

        When an earlier transaction times out or fails mid-frame, the device
        may still finish transmitting its reply afterward; sending another
        request immediately would mix stale bytes into the next response and
        desynchronize sequence numbers. This method finishes reading the
        pending reply frame, verifies its ``0x4D`` magic, matching sequence
        number, and CRC32, records the drained bytes in ``resync_rx``, and
        clears the pending block. It does nothing when no reply is pending.
        """
        timeout = self.timeout if timeout is None else timeout
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        with self._lock:
            if self._pending is None:
                return
            record, rx = self._pending
            deadline = time.monotonic() + timeout
            try:
                target = 5
                while True:
                    if len(rx) >= 5:
                        length = int.from_bytes(rx[3:5], "little")
                        if length > 512:
                            raise ProtocolError("resynchronization invalid length")
                        target = length + 9
                    if len(rx) == target and target != 5:
                        break
                    if time.monotonic() >= deadline:
                        raise ProtocolError("resynchronization timeout")
                    rx.extend(self._serial.read(target - len(rx)))
                if (
                    rx[0] != 0x4D
                    or rx[1] != record["tx"][1]
                    or zlib.crc32(rx[:-4]) != int.from_bytes(rx[-4:], "little")
                ):
                    raise ProtocolError("resynchronization invalid reply")
                self._pending = None
            finally:
                record["resync_rx"] = bytes(rx)

    def _transact(self, opcode, payload=b""):
        """Send one framed command and return its validated reply payload.

        Every exchange is appended to ``self.transactions`` with raw ``tx`` and
        ``rx`` bytes. Any failure clears the cached graph identity. When a
        failure happens at the transport, timeout, framing, or CRC layer, the
        UART stream position is uncertain, so ``_pending`` is set to block
        further writes until ``resynchronize()`` drains the outstanding reply.
        A well-formed reply with a nonzero device status byte still clears the
        cached graph, but leaves the wire stream synchronized.
        """
        with self._lock:
            if self._pending is not None:
                raise ProtocolError(
                    "stream uncertain; explicit resynchronization required"
                )
            tx = encode_frame(0xD4, self._seq, opcode, payload)
            seq = self._seq
            self._seq = (seq + 1) & 255
            rx = bytearray()
            record = {"tx": tx, "rx": b"", "opcode": opcode}
            self.transactions.append(record)
            deadline = time.monotonic() + self.timeout
            try:
                if self._serial.write(tx) != len(tx):
                    raise ProtocolError("partial serial write", tx, bytes(rx))
                target = 5
                while len(rx) < target:
                    if time.monotonic() >= deadline:
                        raise ProtocolError("runtime response timeout", tx, bytes(rx))
                    rx.extend(self._serial.read(target - len(rx)))
                    if len(rx) == 5 and target == 5:
                        length = int.from_bytes(rx[3:5], "little")
                        if length > 512:
                            raise ProtocolError(
                                "response payload exceeds 512", tx, bytes(rx)
                            )
                        target = length + 9
                if rx[0] != 0x4D or rx[1] != seq:
                    raise ProtocolError("response magic/sequence", tx, bytes(rx))
                if zlib.crc32(rx[:-4]) != int.from_bytes(rx[-4:], "little"):
                    raise ProtocolError("response CRC32", tx, bytes(rx))
                if rx[2]:
                    raise ProtocolError(f"runtime status {rx[2]}", tx, bytes(rx), rx[2])
                return bytes(rx[5:-4])
            except (OSError, serial.SerialException) as exc:
                self._loaded = None
                if not isinstance(exc, ProtocolError) or exc.status is None:
                    self._pending = (record, rx)
                record["error"] = str(exc)
                if isinstance(exc, ProtocolError):
                    raise
                raise ProtocolError(str(exc), tx, bytes(rx)) from exc
            finally:
                record["rx"] = bytes(rx)

    def identity(self):
        """Query opcode 1 (IDENTITY) and validate the device's metadata words.

        Expects a 60-byte payload of 15 little-endian uint32 values where the
        protocol version is 2 and every word fits in 16 bits. Clears the cached
        graph and raises ``ProtocolError`` if the response is invalid.
        """
        with self._lock:
            payload = self._transact(1)
            if len(payload) != 60:
                self._loaded = None
                raise ProtocolError(
                    "identity must contain 15 uint32 values", **self._raw_last()
                )
            identity = DecoderIdentity(struct.unpack("<15I", payload))
            if identity.protocol != 2 or any(word > 65535 for word in identity.words):
                self._loaded = None
                raise ProtocolError("unsupported runtime metadata", **self._raw_last())
            return identity

    def _raw_last(self):
        """Return the latest transaction's ``tx`` and ``rx`` bytes for error reports."""
        record = self.transactions[-1]
        return {"tx": record["tx"], "rx": record["rx"]}

    def _ack(self, opcode, payload=b""):
        """Send a command and raise ``ProtocolError`` if the reply carries a payload."""
        if self._transact(opcode, payload):
            self._loaded = None
            raise ProtocolError("command ack must be empty", **self._raw_last())

    def save_archive(self, path):
        """Write the loaded identity, uploaded edges, and wire log to a new JSON file.

        Refuses to overwrite an existing file at ``path``. Each logged
        transaction records its opcode, hex-encoded ``tx``/``rx``/``resync_rx``
        frames, and any error string under the ``runtime-serial-v2`` format.
        """
        import json
        from pathlib import Path

        with self._lock:
            archive = {
                "format": "runtime-serial-v2",
                "identity": list(self._loaded.words) if self._loaded else None,
                "ordered_edges": self.uploaded_edges,
                "transactions": [
                    {
                        "opcode": row["opcode"],
                        "tx_hex": row["tx"].hex(),
                        "rx_hex": row["rx"].hex(),
                        "resync_rx_hex": row.get("resync_rx", b"").hex(),
                        "error": row.get("error"),
                    }
                    for row in self.transactions
                ],
            }
            with Path(path).open("x") as file:
                json.dump(archive, file, indent=2)
                file.write("\n")

    def load_graph(self, detectors, edges, observables):
        """Validate a graph locally, upload it to the FPGA, and verify readback.

        Checks ``detectors`` (1..65535), ``observables`` (0..32), and every
        ``(a, b, mask)`` edge triple (distinct endpoints in ``0..detectors``
        and ``mask`` within ``observables`` bits) against both protocol limits
        and the board's reported capacities before sending ``BEGIN`` (opcode
        2), chunked ``EDGES`` frames (opcode 3), and ``COMMIT`` (opcode 4).

        After ``COMMIT``, re-reads ``identity()`` to confirm ``valid`` is set,
        the dimensions match, and the 32-bit ``generation`` counter advanced by
        one. Only then is the graph cached to arm ``decode()``.
        """
        with self._lock:
            self._loaded = None
            self.uploaded_edges = ()
            if type(detectors) is not int or not 1 <= detectors <= 65535:
                raise ValueError("detector count")
            if type(observables) is not int or not 0 <= observables <= 32:
                raise ValueError("observable count")
            edges = tuple(tuple(edge) for edge in edges)
            if len(edges) > 65535:
                raise ValueError("edge count")
            for edge in edges:
                if len(edge) != 3 or any(type(value) is not int for value in edge):
                    raise ValueError("edges must be integer (a,b,mask) triples")
                a, b, mask = edge
                if not (0 <= a <= detectors and 0 <= b <= detectors) or a == b:
                    raise ValueError("invalid endpoint/self-loop")
                if not 0 <= mask < (1 << observables):
                    raise ValueError("observable mask")
            before = self.identity()
            if (
                detectors > before.max_detectors
                or len(edges) > before.max_edges
                or observables > before.max_observables
            ):
                raise ValueError("graph exceeds device capacities")
            self._ack(2, struct.pack("<HHH", detectors, len(edges), observables))
            # Each indexed edge is 10 bytes (<HHHI), so at most 51 fit in 512 bytes.
            for start in range(0, len(edges), 51):
                chunk = b"".join(
                    struct.pack("<HHHI", index, *edges[index])
                    for index in range(start, min(start + 51, len(edges)))
                )
                self._ack(3, chunk)
            self._ack(4)
            after = self.identity()
            if (
                not after.valid
                or (after.detectors, after.edges, after.observables)
                != (detectors, len(edges), observables)
                or after.generation != (before.generation + 1) & 0xFFFFFFFF
            ):
                raise ProtocolError(
                    "graph identity readback mismatch", **self._raw_last()
                )
            self._loaded = after
            self.uploaded_edges = edges
            return after

    def decode(self, syndrome):
        """Decode one packed syndrome on the FPGA and return a ``DecoderReply``.

        ``syndrome`` is a little-endian integer bitmask with detector 0 in bit
        0 and must fit in ``loaded.detectors`` bits. Before sending opcode 5
        (DECODE), this checks ``identity()`` to confirm the board still holds
        the exact graph generation cached by ``load_graph``; after receiving
        the 9-byte ``<IIB`` reply (``prediction``, ``cycles``, ``error``), it
        checks ``identity().words[:10]`` again so a mid-shot reset or reload
        cannot slip by unnoticed.

        Raises ``RuntimeError`` if no graph is loaded, ``ValueError`` if the
        syndrome is out of range, and ``ProtocolError`` if the identity drifts,
        the reply width is wrong, ``cycles`` is zero, ``error`` is set, or
        ``prediction`` exceeds ``loaded.observables`` bits.
        """
        with self._lock:
            loaded = self._loaded
            if loaded is None:
                raise RuntimeError("successful graph reload required before decode")
            if type(syndrome) is not int or not 0 <= syndrome < (1 << loaded.detectors):
                raise ValueError("syndrome exceeds detector count")
            current = self.identity()
            if (
                not current.valid
                or current.generation != loaded.generation
                or (current.detectors, current.edges, current.observables)
                != (loaded.detectors, loaded.edges, loaded.observables)
            ):
                self._loaded = None
                raise ProtocolError(
                    "graph identity changed; reload required", **self._raw_last()
                )
            payload = self._transact(
                5, syndrome.to_bytes((loaded.detectors + 7) // 8, "little")
            )
            if len(payload) != 9:
                self._loaded = None
                raise ProtocolError("decode reply width", **self._raw_last())
            prediction, cycles, error = struct.unpack("<IIB", payload)
            if not cycles or error or prediction >> loaded.observables:
                self._loaded = None
                raise ProtocolError(
                    "invalid prediction/cycles/decode_error", **self._raw_last()
                )
            after = self.identity()
            if not after.valid or after.words[:10] != loaded.words[:10]:
                self._loaded = None
                raise ProtocolError(
                    "graph identity changed after decode; reload required",
                    **self._raw_last(),
                )
            return DecoderReply(prediction, cycles, bool(error))

    def abort(self):
        """Send opcode 6 (ABORT) and require an empty acknowledgement."""
        with self._lock:
            return self._ack(6)
