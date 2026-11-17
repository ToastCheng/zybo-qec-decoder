# Core scan optimization: first measured batch

The optimized core was simulated and freshly routed for `xc7z010clg400-1` at
100 MHz with unchanged 128-detector / 512-edge / 32-observable capacity. It has
**not been loaded onto the board**. The USB/UART, ARM firmware, mailbox protocol
and public server are unchanged.

## What changed

Baseline FSM profiling on the same archived seed-123 shots attributed 28.1%,
28.2% and 37.2% of total clocks to the four-stage `FIND` scan for d3-Z/r3,
d3-X/r5 and d5-Z/r3, respectively. This batch makes two changes:

- `FIND` skips a nonforest or already-removed edge in one clock instead of
  visiting the three endpoint/work processing states. Forest edges still use
  the registered pipeline. Growth order, relabel scans, leaf selection and
  first-incident-edge selection are unchanged.
- A valid zero syndrome completes after one counted `INIT` clock without
  reading stale work arrays. Every subsequent nonzero shot still initializes
  all active work entries. Width validation precedes this shortcut.

This avoids adjacency memories and parallel relabel writes for the first batch.
The RTL still scans edges serially and has no arrival FIFO or continuous-window
state.

## Paired measurements

Each workload contains the same 128 archived Stim shots: seed 123, one batch of
128, Stim 1.16.0, with each of the four generated circuit-noise arguments at
0.001. The exact circuits, ordered graphs, truth and version metadata are in the
[research evidence](https://github.com/ToastCheng/qc-research/tree/feat/fpga-qec/fpga-qec/core-scan-study).
Baseline RTL clocks exactly reproduced the archived board cycle fields on all
384 shots. Optimized values below are **RTL acceptance-to-first-result clocks**,
measured independently at clock edges, excluding held-result stalls, graph
loading and transport. One clock is 10 ns.

| Workload | Empty shots | Mean before → after | Median before → after | Observed max before → after |
| --- | ---: | ---: | ---: | ---: |
| d3-Z, 3 rounds | 104/128 | 470.65625 → 250.453125 | 153 → 1 | 3649 → 2056 |
| d3-X, 5 rounds | 99/128 | 886.984375 → 498.2734375 | 265 → 1 | 6214 → 3547 |
| d5-Z, 3 rounds | 74/128 | 2852.3828125 → 1775.53125 | 497 → 1 | 13238 → 7265 |

The d3-Z mean is 2.50453125 us, a 1.879x mean-cycle speedup. The nonempty means
also improve: 1847.17 → 1331.42 clocks for d3-Z (27.9% reduction),
3010.31 → 2195.86 for d3-X (27.1%), and 6080.13 → 4207.30 for d5-Z (30.8%).
The median mostly describes the empty-shot path.

All 384 optimized predictions agree with the baseline and Python UF reference.
The ordered merge and peel traces are identical. UF and PyMatching each have
zero logical failures on each 128-shot workload; this small sample does not
establish a zero logical-error rate or general accuracy equivalence.

## Fresh routed implementation

Vivado 2025.2, full SoC, unchanged build strategy, clock and constraints:

| Metric | Baseline | Optimized |
| --- | ---: | ---: |
| Slice LUTs | 7822 | 9048 |
| Slice registers | 3184 | 3195 |
| BRAM36 tiles | 1.5 | 1.5 |
| Setup WNS | +0.095 ns | +0.190 ns |
| Hold WHS | +0.038 ns | +0.042 ns |
| TNS / THS | 0 / 0 ns | 0 / 0 ns |
| DRC checks found | 0 | 0 |

LUT use rises 15.7%, to 51.41% of the Z7-10. Both builds finish routing and
bitstream/XSA export. These are timing-closure results at 100 MHz, not measured
Fmax or new board latency. No timing exceptions were added or changed.
Both reports have zero unconstrained internal endpoints; the four LED outputs
retain their existing missing-output-delay warnings. RAM-mapping methodology
warnings remain in the raw reports.
Local image directories are `build/perf-baseline` and `build/perf-optimized`;
there is no newly verified matching firmware/board bundle.

## Arrival-rate screen and remaining work

An unblocked ready/valid RTL probe independently checks acceptance gaps equal to
result latency plus two clocks. With that overhead, d3-Z mean service is
252.453125 clocks (2.52453125 us), below the agent-selected 330-clock / 3.3-us
arrival screen, with 23.5% mean capacity margin.

A deterministic infinite-FIFO model at that arrival interval needs up to nine
waiting jobs for the 128-shot optimized trace, versus 39 for baseline. Repeating
the same trace 1000 times gives a maximum of 13 optimized waiting jobs versus
38639 baseline; these are repeated inputs, not 128000 independent noisy shots.
The optimized repeated trace still misses a 330-clock result deadline on
92993/128000 offers and reaches 4049 clocks of queue wait. The maximum observed
core latency remains 2056 clocks (20.56 us). Throughput screening does not imply
a per-window reaction deadline is met.

There is no implemented or board-tested arrival queue in this batch. These
terminal-readout windows also lack continuous-QEC overlap/commit semantics,
persistent Pauli-frame state and cross-window fault handling. A long real
load/buffer test and a valid continuous-window contract remain prerequisites for
claiming backlog-free continuous QEC. A larger FPGA comparison is deferred;
this result does not establish or promise parity with Helios.

## Verification and reproduction

`make test` passes 249 Python tests, including actual Vivado core, bridge,
long-counter and new paired performance regressions. Node passes 21 tests;
two opt-in live-browser tests are skipped. Separate fresh core, bridge and
counter runs also pass. Coverage includes bit-31 masks, parameter minimum and
maximum capacities, graph reload/poison recovery, busy/held-result writes,
backpressure, shot abort, full reset and independent cycle edges.

The performance tests first failed on actual RTL: unchanged nonempty cycle
costs violated the 15% reduction budget; after that change passed, empty shots
still took 153/265/497 clocks and failed the one-clock requirement. Raw RED,
GREEN, regression, profile, trace and route logs are archived in the research
study, along with source snapshots and hashes.

From the implementation root:

```sh
make test
python scripts/simulate.py --bench core --build-dir build/sim/NEW_CORE_RUN
make build IMAGE_DIR=build/NEW_IMAGE VIVADO=/path/to/Vivado/bin/vivado
```

Each simulation/build directory must be new. `scripts/simulate.py --vectors
PATH` accepts an existing corpus in the normal reference-vector format; it
skips only the default corpus's >65535-clock coverage requirement. The separate
counter bench retains that coverage. `--core-source PATH` selects an archived
RTL source for baseline replay. Neither option substitutes software for RTL.
