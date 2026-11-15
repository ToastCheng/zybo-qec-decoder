# Runtime serial host

`runtime_host.py` implements only the runtime D4/4D protocol in
[`runtime-decoder-plan.md`](../../docs/runtime-decoder-plan.md). It does not import
a reference decoder, reuse C3/3C framing, program an FPGA or write boot flash.

## Public interface

```python
from qec.surface.runtime_host import RuntimeSerialDecoder

with RuntimeSerialDecoder('/dev/ttyUSB0', timeout=1.0) as device:
    capacities = device.identity()
    # Detector index 9 is the boundary. Preserve compiler-produced edge order.
    identity = device.load_graph(9, [(0, 9, 0x80000001)], 32)
    result = device.decode(1)
    device.save_archive('runtime-capture.json')
```

This is usage syntax, not captured board output. `load_graph(detectors, edges,
observables)` accepts integer endpoint/mask triples. The compiler is responsible
for detector/observable semantics; the host checks representation, dimensions,
endpoints, self-loops and masks without sorting, projecting or combining edges.
It checks the entire graph locally before BEGIN, obtains actual device capacities,
sends at most 51 ordered ten-byte edges per APPEND (510 payload bytes), COMMITs,
and verifies dimensions, config-valid and generation increment modulo 2^32.
A failed load disarms decoding, including when a prior graph was valid.

`RuntimeIdentity.words` contains the 15 mailbox metadata entries as uint32 wire
fields. Its named properties include `protocol`, `max_detectors`, `max_edges`,
`max_observables`, `detectors`, `edges`, `observables`, `valid`, and the combined
32-bit `generation`. These counts and generation are PL-sourced, not a graph hash.
`RuntimeResult` has `prediction` (all 32 bits), `cycles` and `decode_error`.

`decode(syndrome)` takes a nonnegative integer with detector zero in bit zero.
It sends exactly ceil(detectors/8) little-endian bytes, rejecting inactive bits,
and checks graph identity both before and after each shot (metadata words 0..9).
Zero cycle counts are invalid, including a zero prediction with otherwise valid
framing. Decoder errors raise; no substitute
prediction is computed. `abort()` clears the PL shot, not the graph, and never
re-arms a failed load. A successful abort on an otherwise healthy session leaves
its graph usable. `close()` releases the port and disarms the object.

## Transport and evidence

The port uses pyserial POSIX `exclusive=True`; cooperating exclusive owners cannot
open it concurrently. A reentrant lock also protects complete multi-command graph
loads and decodes within one instance. It is not protection against a privileged
process ignoring advisory serial locks.

Sequence increments modulo 256 for every attempted request. CRC is standard IEEE
CRC32 (`123456789` gives `cbf43926`) over the complete header and payload. Responses
must have the right magic, sequence, CRC, bounded length and operation-specific
payload width. A whole transaction has one monotonic deadline. There are no
retries, including for an uncertain completed decode.

`RuntimeTransportError` retains `tx`, `rx`, and optional device `status`.
`transactions` retains every attempted transaction's raw bytes, including partial
responses at timeout. Decode is disarmed on transport failures. An incomplete or
malformed response quarantines the entire stream: identity, abort and graph upload
all fail locally without writing another request. A complete CRC/sequence-valid
device error response settles the serial transaction but still disarms decode.

Call `resynchronize(timeout=...)` explicitly after a timeout. This performs bounded
reads only: it retains any partial reply and consumes exactly the outstanding
sequence with valid 4D framing/length/CRC. It never accepts that result, retries
the operation or clears the UART buffer. A second resynchronization can continue
a partially received reply after the first deadline. Only after success may you
abort/reload; a successful graph reload is required before another shot. Missing
or malformed replies leave the connection quarantined. Reopening a UART alone
is not a synchronization barrier: if recovery cannot consume the old reply, stop
using the session and establish an independently reset, settled device/transport
before constructing a new decoder. The initial connection assumes no command or
reply from an earlier owner remains in flight.

`uploaded_edges` is the exact ordered graph last successfully uploaded by this
object. `save_archive(path)` creates a new JSON file (never overwrites), recording
these edges, verified identity if still armed, and all raw TX/RX frames in hex.
`resync_rx_hex` retains the cumulative reply consumed during resynchronization;
the original timeout `rx_hex` remains unchanged.
After a failed operation the raw history remains, but active identity is null;
previous captures should be saved before changing graphs. No hardware-verified
digest or cryptographic identity is claimed.

## Verification

From repository root:

```sh
PYTHONPATH=qec qec/.venv/bin/python -m pytest qec/tests/test_runtime_host.py -q
```

These are real PTY byte streams and native firmware tests, not physical UART/PL
acceptance. See the adjacent [test walkthrough](../tests/test_runtime_host.md).
