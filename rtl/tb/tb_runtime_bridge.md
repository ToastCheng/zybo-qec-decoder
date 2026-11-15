# Runtime mailbox regression

`tb_runtime_bridge.sv` tests the actual mailbox plus core at capacities 20/16/32,
not a mailbox stub. Run `python scripts/run_runtime_rtl.py --bench bridge`.
The PS driver toggles ctrl[31] only after acknowledgement, drives on falling
edges and samples after rising-edge nonblocking updates. Every command has an
ack timeout and an explicit expected status[29].

Coverage includes protocol/capacity reads, unknown opcode and index rejection,
invalid begin and incomplete commit acknowledgement, failed-upload fail-closed
behavior, successful generation increments, and next-valid recovery. Begin,
append, commit, decode and abort require index zero. Staging and metadata reject
out-of-range indices without aliasing.

A one-detector/one-edge graph returns prediction 0x80000005 and 31 cycles. A
17-detector/two-edge graph in the **same executable** verifies a second syndrome
word, missing-word rejection, unused high bits in its final partial word,
per-shot written-word freshness and separate low/high observable masks. A
committed one-detector/no-edge graph verifies completed decode-error reporting
and subsequent zero-syndrome recovery. Saved result/status stability, reads,
graph-preserving abort and full-reset generation/configuration clearing are
also asserted.

The initial RED ran before bridge creation (xvlog reported the missing bridge).
The later reserved-index RED is retained in `build/runtime-red-index/`:
`Fatal: mailbox error op=2 status=00000000`. The production fix rejects nonzero
indices instead of aliasing begin. The final real xsim marker is:

```
PASS runtime bridge mailbox rejection/recovery metadata decode abort reset
```

Pipelined logs are in `build/runtime-test-bridge-7cee8241c52b/`; the independent high cycle-half test is
[tb_runtime_counter](tb_runtime_counter.md). This does not simulate UART firmware
or establish physical GPIO operation. The mailbox permits one outstanding
command and does not support toggling an abort while decode is unacknowledged.
