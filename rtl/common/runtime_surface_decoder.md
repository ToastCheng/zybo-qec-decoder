# Runtime surface decoder core

`runtime_surface_decoder.sv` implements the runtime graph contract in
[`runtime-decoder-plan.md`](../../docs/runtime-decoder-plan.md). It does not
instantiate the fixed-image decoder, read an edge ROM, or use a syndrome LUT.

## Parameters and exact ports

All ports are synchronous to rising `clk`. `rst` is synchronous, active high.
Capacities must be positive: `MAX_DETECTORS` and `MAX_EDGES` fit unsigned 16-bit
counts; `MAX_OBSERVABLES` is 1–32. Defaults are 128, 512 and 32. Runtime counts
may be zero, including a zero-detector/zero-edge/zero-observable graph.

| Port | Direction/width | Meaning |
|---|---|---|
| `clk`, `rst` | input, 1 each | Clock and full reset |
| `shot_abort` | input, 1 | Abort active/held shot and clear shot outputs, retaining graph/load state |
| `cfg_begin`, `cfg_write`, `cfg_commit` | input, 1 each | Mutually exclusive configuration strobes |
| `cfg_detector_count`, `cfg_edge_count`, `cfg_observable_count` | input, 16 each | Dimensions sampled by begin |
| `cfg_edge_index`, `cfg_endpoint_a`, `cfg_endpoint_b` | input, 16 each | Sequential index and unsigned endpoints sampled by write |
| `cfg_observable_mask` | input, 32 | Full multibit observable mask sampled by write |
| `cfg_ack`, `cfg_error` | output, 1 each | Registered acknowledgement and rejection for a configuration request |
| `configured` | output, 1 | Graph committed and usable |
| `detector_count`, `edge_count`, `observable_count` | output, 16 each | Most recently begun dimensions; meaningful as active dimensions only when configured |
| `in_valid`, `in_ready` | input/output, 1 | Shot ready/valid acceptance |
| `syndrome` | input, `MAX_DETECTORS` | Detector bit i is bit i; unused upper bits must be zero |
| `out_valid`, `out_ready` | output/input, 1 | Result ready/valid retirement |
| `prediction` | output, `MAX_OBSERVABLES` | XOR of selected edge masks |
| `decode_error` | output, 1 | Invalid high syndrome bits or failed growth/peeling |
| `cycles` | output, 32 | Acceptance-to-first-result clock-edge difference, excluding stalled retirement |

Assert one configuration strobe with stable payload for one rising edge. After
that edge `cfg_ack=1`; `cfg_error=0` means its effect completed. Both clear on a
clock without a request. Holding a strobe repeats the command, not a handshake
wait. Configuration takes precedence over shot acceptance: `in_ready` is low
while any strobe, reset or shot abort is asserted.

## Loading and failure recovery

1. Begin invalidates the previous graph, records dimensions and clears the
   sequential-write count. Oversize dimensions acknowledge error immediately.
2. Write indices must be exactly 0, 1, …, edge_count−1. Endpoints must be distinct
   and in 0…detector_count inclusive. The runtime boundary is detector_count.
   Masks cannot set any bit >= observable_count. Edge order is retained, including
   parallel edges; duplicate *write indices*, not parallel endpoint pairs, are
   forbidden.
3. Commit succeeds only after every edge has passed validation. Any rejected
   write, incomplete commit or simultaneous command during a load poisons it.
   A new begin is the only recovery; no stale graph can be decoded.

Append/commit outside a load reject without changing an existing committed
configuration. Every command while decoding or holding a result acknowledges
error without changing the shot or graph. A busy begin does **not** invalidate the
active graph. Do not combine configuration commands with abort.

Full reset clears graph validity, dimensions and all control/result state. Graph
RAM need not be physically cleared because no shot is accepted before a complete
new load. `shot_abort` clears only active/held shot state and outputs; a committed
graph survives, and an incomplete/failed load does not become committed.

## Serial policy and cycles

INIT clears active per-shot vertex/edge arrays. CHECK scans non-boundary cluster
parities. Each growth edge uses five clocked stages: GROW reads graph endpoints
and growth; GROW_ROOTS reads labels and endpoint degrees; GROW_VALUES reads root
parities; GROW_SELECT computes and registers winner, loser, expanded growth and
merged parity; GROW_APPLY updates the selected edge and vertices. No indirect
array read feeds another array read or a root-dependent write address in the
same cycle. The stages are serial, not overlapping: every union and complete
RELABEL sweep finishes before the next edge is sampled. Thus input edge order,
half-edge saturation, boundary-first/lower-root ties and predictions are unchanged.

LEAVES selects the lowest detector leaf. FIND reads endpoints, forest and mask;
FIND_VALUES reads endpoint degrees and leaf work, registering the other endpoint;
FIND_OTHER reads that endpoint work; FIND_APPLY removes the first matching forest
edge, transfers work and XORs its registered mask. Unmatched edges still traverse
all four stages. VERIFY ignores boundary parity. Pipeline registers need no
reset because every consuming state follows the corresponding producer; abort
returns to IDLE and the next shot runs INIT before reading per-shot arrays.
This is the same serial UF policy as
`qec.surface.decoder.decode`, not weighted MWPM.

Zero-edge graphs avoid edge-array accesses in algorithm states: zero syndrome
succeeds; a nonzero syndrome fails. High unused syndrome bits yield an immediate
error result (`cycles=0`). No ordinary shot can start before configuration, and
no new shot is accepted until a held result retires. Prediction, error and cycles
remain stable throughout HOLD, including rejected configuration requests.

Each active algorithm edge increments cycles; acceptance and stalled HOLD do
not. A one-detector, one-boundary-edge odd shot takes 31 clocks; zero syndrome
takes 8. Each growth edge adds four clocks and each searched peel edge adds
three clocks versus the original unpipelined schedule. The reverse-ordered
128-edge path used by the counter bench takes 287940 clocks (2.8794 ms at
100 MHz, excluding transport). The core bench independently measures every corpus shot from
acceptance to result, rather than trusting these example constants.

## Verification and physical limitations

Run `python scripts/run_runtime_rtl.py --bench core` from the repository root.
See [the bench walkthrough](../tb/tb_runtime_core.md) for actual coverage.
The original routed report in `build/runtime-image/runtime_soc_timing_summary.rpt`
failed setup at WNS -3.479 ns with 3278 failing endpoints; hold was +0.022 ns.
Its worst path chained edge_cursor through graph RAM, label RAM, root selection
and parity write decoding (13 logic levels, 13.204 ns data delay). The registered
stages above remove those serial indirect reads rather than hiding them with
timing exceptions. Original evidence is untouched.

A fresh 128/512/32, 100 MHz build uses `build/runtime-image-v2`; the exact source
snapshot and SHA256 manifest are in `build/runtime-image-v2-inputs`. Check its
actual routed report with `python scripts/verify_runtime_timing.py
build/runtime-image-v2/runtime_soc_timing_summary.rpt`. Behavioral simulation is
not routing or board evidence. No clock, capacity, DRC severity or timing
exception was changed by this pipeline fix.

Vivado 2025.2 completed that build successfully: WNS +0.095 ns, WHS
+0.038 ns, TNS/THS zero, zero setup/hold failing endpoints (8844 checked),
and zero DRC findings. The actual generated PS FCLK remains 10 ns / 100 MHz.
Resources are 7822 LUTs, 3184 registers and 1.5 BRAM tiles. The new worst path
is graph_b BRAM output to degree write enable, six logic levels / 9.412 ns,
not the original graph/label/parity cascade. Margin is positive but small;
this is routed closure, not measured board timing or an Fmax claim.

`runtime_soc.bit` and `runtime_soc.xsa` were exported and their embedded
bitstream bytes matched (SHA256
`14d5f3e2ce9c20cfc9a584a8d80dedf28f55dc9be2e02faca301bc0e9707b1f1`).
The four LED outputs retain their existing no-output-delay diagnostics; there
are no unconstrained internal endpoints. Existing vendor GPIO synchronizer
false paths are unchanged. No board programming or Vitis changes were performed.

Behavioral evidence: the 12-graph/474-checked-shot core corpus, bridge recovery
and independent counter bench pass. The five archived compiler circuits were
recompiled with the actual frontend and their graph/count contracts matched;
all 640 circuit shots plus a separately identified synthetic long-path shot
match the reference on the new RTL (`build/runtime-compiled-circuits-v2/`,
646 total checked shots including five bench recovery cases). The archived
d3-X/r5 circuit retains its two reference logical failures; reference agreement
is not a claim of perfect decoding. The combined compiler and RTL pytest run
passed 21 tests.
