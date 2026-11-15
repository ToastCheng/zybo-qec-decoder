# Serial half-edge growth and forest peeling

Source: [`surface_decoder.sv`](surface_decoder.sv).

## Interface, storage and graph format

`DETECTORS` syndrome bits represent one complete shot; `EDGES` ROM words describe
the fixed graph selected by `GRAPH_FILE`. `VB` must encode vertices 0 through
`DETECTORS`; the last vertex `B = DETECTORS` is the shared boundary. Each word is
`{observable[0], b[VB-1:0], a[VB-1:0]}`. Endpoint indices must be valid; ROM order is
part of deterministic tie-breaking. `prediction` is one observable bit only.
`decode_error` reports growth exhaustion, a missing forest edge, residual detector
parity or an invalid state, not a probability of logical failure.

`label[v]` directly names the cluster root. Only roots carry cluster `parity`;
`work[v]` separately retains the detector parity used for peeling. `growth[e]`
saturates at two half-edges; `forest[e]` and vertex `degree` record merge edges.
There are no parent-pointer traversals or syndrome prediction tables.

## State-machine walkthrough

1. `IDLE` accepts a shot and clears prediction/error/cycle count. `INIT` rewrites
   vertex and edge arrays with one shared cursor covering both domains.
2. `CHECK` folds parity over detector vertices, excluding the boundary. No odd
   non-boundary root means growth is complete. Otherwise it starts another sweep,
   or reports error after `2 * (DETECTORS + 1)` sweeps.
3. `GROW` scans edges serially. Each odd non-boundary endpoint root contributes
   one half-edge. Distinct roots merge once growth reaches two: boundary wins if
   present, otherwise the smaller root wins. Root parity XORs, the loser clears,
   and this edge joins the forest. Internal-cluster edges do not grow.
4. `RELABEL` scans every vertex and replaces the losing label before `ADVANCE`
   moves to the next edge. At the end of a sweep, control returns to `CHECK`.
5. `LEAVES` finds the first degree-one detector vertex (never the boundary).
   `FIND` scans edges for its forest edge. If the leaf has odd `work` parity, that
   edge is selected: neighbor parity toggles and its observable XORs into prediction.
   The edge is removed either way, degrees decrement, and scanning restarts at zero.
6. With no detector leaves left, `VERIFY` requires every detector's `work` bit to
   be zero; boundary parity is deliberately unconstrained. `HOLD` publishes the
   result until accepted.

## Timing, invariants and limitations

Handshake is single-shot valid/ready; inputs are ignored outside `IDLE`. Active-high
reset clears control synchronously and immediately gates handshake outputs; arrays
are initialized by the next `INIT`, not reset fanout. `cycles` counts every active
algorithm edge after acceptance through entry into `HOLD`, and freezes while held.
It excludes input wait and output backpressure. Result fields remain stable in HOLD.

The algorithm is serial and unweighted: flat relabel scans and repeated edge/leaf
scans cost latency despite graph-size storage. It is not weighted MWPM, a continuous
streaming decoder, or a multibit-observable implementation. Graph connectivity,
valid endpoints and matching ROM parameters are caller/build responsibilities.

## Verification and related files

From root: `python qec/surface/sim.py --distance 3 --basis z --shots 256`, then
repeat with `--distance 5 --basis z --shots 128` and
`--distance 3 --basis x --shots 128`. The real Stim/graph/reference corpus drives
`qec/surface/tb_surface.sv`, checking predictions, independent cycle edges, held
results and reset abort. `make sim_surface` runs the same three configurations.
See `qec/surface/decoder.py` for reference tie ordering, `qec/surface/graphs/` for
ROMs, and [`surface_ps_bridge.sv`](surface_ps_bridge.sv) for the mailbox wrapper.
