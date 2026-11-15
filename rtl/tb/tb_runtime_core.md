# Runtime core regression

`tb_runtime_core.sv` drives the actual runtime core, with default capacities
128 detectors / 512 edges / 32 observables. A concurrent minimum-capacity probe
uses 1/1/1, verifies the one-bit observable datapath and rejects count 2.

Run `python scripts/run_runtime_rtl.py --bench core` at the repository root.
The runner generates `runtime_vectors.txt` in its isolated build directory using
the actual `decode` function extracted from `qec/surface/decoder.py`; no Stim or
PyMatching installation is needed for this dependency-free reference function.
There is no independently reimplemented software UF oracle.

The same elaborated executable loads 12 graphs with 0, 1, 2, 3, 4, 5, 8, 17 and
128 detectors; 0 through 512 edges; and 0 through 32 observables. Small graphs are
exhaustive over syndromes. Larger graphs use reproducible seeded shots plus zero,
single-low, single-high and all-set syndromes. Unsorted edge order, disconnected
components, an empty graph, independent observable bits including bit 31 and a
reverse-ordered 128-edge path exercise scheduling, failure and 32-bit counters.
All 469 corpus shots compare both prediction and error with the actual reference.
Five additional checked shots cover high unused syndrome bits and reset recovery.

Each checked shot independently counts rising edges after acceptance until
`out_valid`, compares that count with cycles, and holds the result for three
clocks while offering another input. Outputs must remain stable and `in_ready`
low. The long-path shot reaches 287940 cycles, crossing the 16-bit boundary.

Configuration tests reject oversize dimensions, incomplete commit, out-of-order
and duplicate write indices, endpoint overflow, self-loops, invalid masks and
simultaneous commands. Errors poison an in-progress load until a fresh begin.
Busy/held-result commands must acknowledge errors without interrupting the shot
or changing its graph. Abort during execution and HOLD preserves the graph;
full reset removes it, and reload recovers. Inputs are driven on falling edges;
outputs are sampled after nonblocking updates. The abort-ready check also waits
for the combinational ready path to settle.

The first RED preceded core creation: xvlog reported the missing
`runtime_surface_decoder.sv`. The conflict-poisoning extension produced the real
behavioral RED `Fatal: config op=3 error=0 expected=1`; the fix marks the partial
load failed. That failure remains in `build/runtime-red-conflict/`.

Verified final marker:

```
PASS runtime core graphs=12 checked_shots=474 maximum_cycles=287940 config recovery stalls abort reset cycles
```

Pipelined compiler/elaborator/simulator logs are in
`build/runtime-test-core-2e2702a60f1b/`. The additional archived five-circuit
compiler regression is in `build/runtime-compiled-circuits-v2/`: 640 circuit
shots, one separately identified synthetic long-path shot and five recovery
checks, all matching predictions/errors and independently counted cycles.
This establishes behavioral RTL correctness on the exercised corpus, not an
exhaustive proof over all possible graphs or physical timing closure.
