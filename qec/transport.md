# Repetition UART framing and bounded software exchange

Companion to [`transport.py`](transport.py).

## Contracts and flow

`request(seq, syndrome)` requires two byte-range values and emits `A5 seq syndrome xor`. The XOR covers all preceding bytes; XOR of a complete valid frame is zero.

`Parser.feed(data)` accepts arbitrary byte chunks and returns `(sequence, prediction, cycles)` tuples. It skips noise until `5A`, buffers a six-byte response, clears that buffer, then checks checksum and a binary prediction. Cycles are bytes 3–4 in little-endian order. Invalid complete frames raise ValueError instead of silently resynchronizing through them. A partial frame remains in `buffer` for the next call.

`exchange(endpoint, seq, syndrome, timeout)` requires a full write, reads chunks of up to 64 bytes, and checks the monotonic deadline again after a read. It accepts one matching-sequence frame; multiple frames returned together or a wrong sequence raise. The parser and deadline are per exchange, not persistent connection state. Endpoint read/write operations must themselves be bounded: Python cannot interrupt an indefinitely blocked endpoint. After timeout the diagnostic requires closing/reopening before retrying, avoiding stale-response ambiguity.

`Loopback(table)` implements write/read over an in-memory response queue. Its prediction is the indexed table entry and its cycle count is always zero. It exercises framing only; it neither simulates RTL nor measures FPGA timing.

## Callable index

- `request` — Encode A5, sequence, eight-bit syndrome and XOR checksum as a four-byte request.
- `exchange` — Endpoint reads/writes must themselves be bounded by timeout.
- `Loopback` — Software only. Cycle count is zero: no RTL timing is simulated.
- `Loopback.__init__` — Bind the prediction table and initialize the software response queue.
- `Loopback.write` — Validate one request and queue a six-byte response with zero placeholder cycles.
- `Loopback.read` — Consume at most size queued bytes without blocking.
- `Parser` — Incrementally parse six-byte 5A replies, retaining at most one partial frame.
- `Parser.__init__` — Start with no partial response bytes.
- `Parser.feed` — Return (sequence, prediction, little-endian cycles) tuples; reject malformed complete frames.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/host.py --mode loopback --shots 32
python -m pytest -q qec/tests/test_transport.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.
