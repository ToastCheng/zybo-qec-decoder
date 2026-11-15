"""D4/4D runtime serial transport. Never computes a replacement prediction."""
import struct
import zlib
import time
import threading
from dataclasses import dataclass

import serial


def encode_frame(magic, seq, code, payload=b""):
    """IEEE CRC32 covers the five-byte header and payload, including magic."""
    if len(payload) > 512:
        raise ValueError("payload exceeds 512 bytes")
    data = struct.pack("<BBBH", magic, seq, code, len(payload)) + payload
    return data + struct.pack("<I", zlib.crc32(data))


class RuntimeTransportError(IOError):
    """Raw transaction is retained even when completion cannot be determined."""
    def __init__(self, message, tx=b"", rx=b"", status=None):
        super().__init__(message)
        self.tx = tx
        self.rx = rx
        self.status = status


@dataclass(frozen=True)
class RuntimeIdentity:
    """PL metadata words, not a graph digest or cryptographic identity."""
    words: tuple

    protocol = property(lambda self: self.words[0])
    max_detectors = property(lambda self: self.words[1])
    max_edges = property(lambda self: self.words[2])
    max_observables = property(lambda self: self.words[3])
    detectors = property(lambda self: self.words[4])
    edges = property(lambda self: self.words[5])
    observables = property(lambda self: self.words[6])
    valid = property(lambda self: bool(self.words[7]))
    generation = property(lambda self: self.words[8] | self.words[9] << 16)


@dataclass(frozen=True)
class RuntimeResult:
    prediction: int
    cycles: int
    decode_error: bool


class RuntimeSerialDecoder:
    """Own an exclusive UART and serialize whole graph/decode transactions.

    No automatic retry, no reference decoder. A failed/uncertain operation disarms
    decode until an explicit successful graph reload. `transactions` stores bytes.
    """
    def __init__(self, port, *, baudrate=115200, timeout=1.0):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.timeout = timeout
        self._lock = threading.RLock()
        self._seq = 0
        self._loaded = None
        self._pending = None
        self.uploaded_edges = ()
        self.transactions = []
        self._serial = serial.Serial(
            port, baudrate, timeout=min(timeout, 0.02),
            write_timeout=timeout, exclusive=True,
        )

    def close(self):
        with self._lock:
            self._serial.close()
            self._loaded = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def resynchronize(self, *, timeout=None):
        """Consume exactly the outstanding reply without accepting its result.

        No request/retry/abort is sent. A missing or malformed reply leaves the
        stream quarantined; merely reopening the port is not a recovery barrier.
        Successful resynchronization still requires an explicit graph reload.
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
                            raise RuntimeTransportError("resynchronization invalid length")
                        target = length + 9
                    if len(rx) == target and target != 5:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeTransportError("resynchronization timeout")
                    rx.extend(self._serial.read(target - len(rx)))
                if (rx[0] != 0x4D or rx[1] != record["tx"][1] or
                        zlib.crc32(rx[:-4]) != int.from_bytes(rx[-4:], "little")):
                    raise RuntimeTransportError("resynchronization invalid reply")
                self._pending = None
            finally:
                record["resync_rx"] = bytes(rx)

    def _transact(self, opcode, payload=b""):
        with self._lock:
            if self._pending is not None:
                raise RuntimeTransportError("stream uncertain; explicit resynchronization required")
            tx = encode_frame(0xD4, self._seq, opcode, payload)
            seq = self._seq
            self._seq = (seq + 1) & 255
            rx = bytearray()
            record = {"tx": tx, "rx": b"", "opcode": opcode}
            self.transactions.append(record)
            deadline = time.monotonic() + self.timeout
            try:
                if self._serial.write(tx) != len(tx):
                    raise RuntimeTransportError("partial serial write", tx, bytes(rx))
                target = 5
                while len(rx) < target:
                    if time.monotonic() >= deadline:
                        raise RuntimeTransportError("runtime response timeout", tx, bytes(rx))
                    rx.extend(self._serial.read(target - len(rx)))
                    if len(rx) == 5 and target == 5:
                        length = int.from_bytes(rx[3:5], "little")
                        if length > 512:
                            raise RuntimeTransportError("response payload exceeds 512", tx, bytes(rx))
                        target = length + 9
                if rx[0] != 0x4D or rx[1] != seq:
                    raise RuntimeTransportError("response magic/sequence", tx, bytes(rx))
                if zlib.crc32(rx[:-4]) != int.from_bytes(rx[-4:], "little"):
                    raise RuntimeTransportError("response CRC32", tx, bytes(rx))
                if rx[2]:
                    raise RuntimeTransportError(f"runtime status {rx[2]}", tx, bytes(rx), rx[2])
                return bytes(rx[5:-4])
            except (OSError, serial.SerialException) as exc:
                self._loaded = None
                if not isinstance(exc, RuntimeTransportError) or exc.status is None:
                    self._pending = (record, rx)
                record["error"] = str(exc)
                if isinstance(exc, RuntimeTransportError):
                    raise
                raise RuntimeTransportError(str(exc), tx, bytes(rx)) from exc
            finally:
                record["rx"] = bytes(rx)

    def identity(self):
        with self._lock:
            payload = self._transact(1)
            if len(payload) != 60:
                self._loaded = None
                raise RuntimeTransportError("identity must contain 15 uint32 values",
                                            **self._raw_last())
            identity = RuntimeIdentity(struct.unpack("<15I", payload))
            if identity.protocol != 2 or any(word > 65535 for word in identity.words):
                self._loaded = None
                raise RuntimeTransportError("unsupported runtime metadata", **self._raw_last())
            return identity

    def _raw_last(self):
        record = self.transactions[-1]
        return {"tx": record["tx"], "rx": record["rx"]}

    def _ack(self, opcode, payload=b""):
        if self._transact(opcode, payload):
            self._loaded = None
            raise RuntimeTransportError("command ack must be empty", **self._raw_last())

    def save_archive(self, path):
        """Create a new JSON evidence file; never overwrite a previous capture.

        Counts/generation are PL-sourced. Ordered edges and raw frames are host
        records only; no hardware-verified hash/digest claim is made.
        """
        import json
        from pathlib import Path
        with self._lock:
            archive = {
                "format": "runtime-serial-v2",
                "identity": list(self._loaded.words) if self._loaded else None,
                "ordered_edges": self.uploaded_edges,
                "transactions": [
                    {"opcode": row["opcode"], "tx_hex": row["tx"].hex(),
                     "rx_hex": row["rx"].hex(),
                     "resync_rx_hex": row.get("resync_rx", b"").hex(),
                     "error": row.get("error")}
                    for row in self.transactions
                ],
            }
            with Path(path).open("x") as file:
                json.dump(archive, file, indent=2)
                file.write("\n")

    def load_graph(self, detectors, edges, observables):
        """Upload exact ordered (a,b,mask) edges; boundary index is detectors.

        Fully validate locally before sending BEGIN. Identity supplies actual
        device capacities. Only verified COMMIT/readback enables decode.
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
            if (detectors > before.max_detectors or len(edges) > before.max_edges or
                    observables > before.max_observables):
                raise ValueError("graph exceeds device capacities")
            self._ack(2, struct.pack("<HHH", detectors, len(edges), observables))
            for start in range(0, len(edges), 51):
                chunk = b"".join(struct.pack("<HHHI", index, *edges[index])
                                 for index in range(start, min(start + 51, len(edges))))
                self._ack(3, chunk)
            self._ack(4)
            after = self.identity()
            if (not after.valid or (after.detectors, after.edges, after.observables) !=
                    (detectors, len(edges), observables) or
                    after.generation != (before.generation + 1) & 0xFFFFFFFF):
                raise RuntimeTransportError("graph identity readback mismatch", **self._raw_last())
            self._loaded = after
            self.uploaded_edges = edges
            return after

    def decode(self, syndrome):
        with self._lock:
            loaded = self._loaded
            if loaded is None:
                raise RuntimeError("successful graph reload required before decode")
            if type(syndrome) is not int or not 0 <= syndrome < (1 << loaded.detectors):
                raise ValueError("syndrome exceeds detector count")
            current = self.identity()
            if (not current.valid or current.generation != loaded.generation or
                    (current.detectors, current.edges, current.observables) !=
                    (loaded.detectors, loaded.edges, loaded.observables)):
                self._loaded = None
                raise RuntimeTransportError("graph identity changed; reload required", **self._raw_last())
            payload = self._transact(5, syndrome.to_bytes((loaded.detectors + 7) // 8, "little"))
            if len(payload) != 9:
                self._loaded = None
                raise RuntimeTransportError("decode reply width", **self._raw_last())
            prediction, cycles, error = struct.unpack("<IIB", payload)
            if not cycles or error or prediction >> loaded.observables:
                self._loaded = None
                raise RuntimeTransportError("invalid prediction/cycles/decode_error", **self._raw_last())
            after = self.identity()
            if not after.valid or after.words[:10] != loaded.words[:10]:
                self._loaded = None
                raise RuntimeTransportError("graph identity changed after decode; reload required",
                                            **self._raw_last())
            return RuntimeResult(prediction, cycles, bool(error))

    def abort(self):
        """Abort a shot without changing the PL graph; does not re-arm failed upload."""
        with self._lock:
            return self._ack(6)
