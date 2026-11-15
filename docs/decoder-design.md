# Decoder design

One graph-loadable image accepts circuit-specific detector graphs and complete
syndrome windows. The accepted Z7-10 design has capacities of 128 detectors,
512 edges and 32 observable bits at 100 MHz. Physical-qubit count is separate
from these limits. [Verification](verification.md) records measured acceptance;
[source navigation](code-walkthrough.md) identifies the implementation.

## Circuit and graph contract

Inputs are detector-annotated physical Clifford Stim circuits with declared
observables. Checks and observables must be deterministic without noise.
The compiler rejects unsupported feedback, non-graphlike fault components,
detectorless logical components and ambiguous endpoint/mask assignments.
Zero-probability faults do not create graph edges. A noiseless experiment with
an empty graph requires an explicit compatible noisy reference.

An edge is `(endpoint_a, endpoint_b, observable_mask)`. The boundary vertex is
`detector_count`; mask bit i refers to observable i. Masks are unsigned 32-bit
values. The unweighted half-edge union-find/forest-peeling algorithm retains
input edge order for deterministic ties. It is not weighted matching.

Configuration begins with dimensions, writes sequential ordered edges and commits
only after all declared edges pass validation. A malformed load stays invalid
until another begin. Busy or held-result writes are rejected. Shot abort
preserves the committed graph; full reset clears it. The core checks unused high
syndrome bits and returns prediction, decode error and acceptance-to-result cycles.

## PS/PL mailbox

ARM firmware and the PL bridge exchange 32-bit command/status words through
AXI GPIO in one 100 MHz FCLK domain. Only one toggle command may be outstanding.
Command fields are toggle bit 31, opcode bits 27:24, index bits 23:16 and data
bits 15:0. Status contains acknowledgement bit 31, completion bit 30, error bit
29 and read data bits 15:0.

Mailbox operations stage dimensions/edge words, begin, append, commit, write
syndrome words, decode, read metadata and abort a shot. Metadata reports protocol
version 2, capacities, configured dimensions, validity, generation, prediction,
cycles and decode error. Graph generation advances only on successful commit.

Decode acknowledgement requires completion, positive cycles and unchanged graph
identity. A matching toggle alone can alias after reset. An abort command cannot
preempt an unacknowledged decode on this one-outstanding-command mailbox.

## Serial framing and recovery

Requests start with `D4`, replies with `4D`. Both contain an 8-bit sequence,
an opcode/status byte, a little-endian 16-bit payload length, payload and
little-endian IEEE CRC32 over header and payload. Maximum payload is 512 bytes.

Serial operations read identity, begin graph load, append indexed edge records,
commit, decode and abort. An edge record contains three uint16 fields
(index and endpoints) and a uint32 mask. Decode returns a uint32 prediction,
uint32 cycle count and an error byte. Upload verifies committed dimensions,
validity and generation before any shot is submitted.

After uncertain completion, the host blocks writes until bounded
resynchronization validates the outstanding reply, then requires graph reload.
Closing and reopening the port does not prove a delayed reply has disappeared.
FPGA failures never trigger silent software fallback.

## Interpretation

Graph hashes identify host artifacts; the FPGA does not cryptographically attest
the uploaded graph. Observable truth remains on the host. Hardware predictions
are observable-frame decisions, not physical correction gates or a demonstrated
adaptive feedback loop. A known memory preset or supplied logical mapping can
support a logical view; physical annotations alone do not establish an encoding
or automatic fault-tolerant synthesis.
