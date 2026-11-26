# Core scan optimization study

This note documents the first cycle-count optimization pass on the runtime
union-find core (`fpga/rtl/common/qec_decoder.sv`), targeting `xc7z010clg400-1`
at 100 MHz with unchanged capacity (128 detectors, 512 edges, 32 observables).
The UART protocol, ARM firmware, and mailbox bridge did not change.

> **Status note:** This report records the initial simulation and routing
> study for the optimization pass. Subsequent on-board measurements of the
> resulting 9,048-LUT image are reported in
> [decoder performance](benchmark-timing.md#on-board-d3-and-d5-comparison).

## Why and what changed

Profiling the earlier baseline FSM on 128-shot workloads showed that the
four-stage `FIND` scan during forest peeling accounted for 28.1% (`d3-Z/r3`),
28.2% (`d3-X/r5`), and 37.2% (`d5-Z/r3`) of all clock cycles — mostly spent
reading endpoints for edges that were not even in the spanning forest.

Two targeted changes cut that overhead without adding adjacency tables or
parallel merge writes:

1. **One-clock nonforest skip in `FIND`:** if an edge is not in the forest (or
   has already been peeled), `FIND` advances past it in a single clock instead
   of stepping through the three registered endpoint/work stages. Forest edges
   keep the same pipeline, so merge order, tie-breaking, and leaf selection
   stay bit-for-bit identical.
2. **One-clock zero-syndrome fast path:** if the graph is valid and the
   syndrome is all zeros, `INIT` finishes after one counted clock without
   clearing work arrays. The next nonzero shot still initializes every active
   entry before use, and width checks still run first.

## Paired RTL measurements (before vs. after)

All three workloads replay the exact same 128 archived Stim 1.16.0 shots
(seed `123`, all four circuit-noise parameters at `0.001`). Circuits, ordered
graphs, and truth data are archived in
[core-scan-study](https://github.com/ToastCheng/qc-research/tree/feat/fpga-qec/fpga-qec/core-scan-study).
Baseline RTL matched the earlier board cycle counts on all 384 shots. Cycle
counts below measure acceptance-to-first-result clocks at 100 MHz (`10 ns` per
clock), excluding held-result stalls, graph uploads, and UART:

| Workload | Empty shots | Mean before → after | Median before → after | Observed max before → after |
| --- | ---: | ---: | ---: | ---: |
| d3-Z, 3 rounds | 104 / 128 | 470.66 → 250.45 | 153 → 1 | 3,649 → 2,056 |
| d3-X, 5 rounds | 99 / 128 | 886.98 → 498.27 | 265 → 1 | 6,214 → 3,547 |
| d5-Z, 3 rounds | 74 / 128 | 2,852.38 → 1,775.53 | 497 → 1 | 13,238 → 7,265 |

- Overall mean speedup on `d3-Z` is **1.88×** (`2.50 µs` mean).
- Looking only at **nonempty shots** (so the zero-syndrome shortcut does not
  mask peeling speed), mean cycles dropped by **27.9%** on `d3-Z`
  (`1,847.2 → 1,331.4`), **27.1%** on `d3-X` (`3,010.3 → 2,195.9`), and
  **30.8%** on `d5-Z` (`6,080.1 → 4,207.3`).
- Every prediction and every ordered merge/peel trace across all 384 shots
  matched the baseline and Python UF reference identically.

## Routed resource and timing impact

Full-SoC Vivado 2025.2 route with identical constraints and clock (100 MHz):

| Metric | Baseline | Optimized |
| --- | ---: | ---: |
| Slice LUTs | 7,822 | 9,048 |
| Slice registers | 3,184 | 3,195 |
| BRAM36 tiles | 1.5 | 1.5 |
| Setup WNS | +0.095 ns | +0.190 ns |
| Hold WHS | +0.038 ns | +0.042 ns |
| TNS / THS | 0 / 0 ns | 0 / 0 ns |
| Routed DRC findings | 0 | 0 |

LUT usage increases by 15.7% (reaching 51.4% of the Zybo Z7-10), while setup
slack improves slightly from `+0.095 ns` to `+0.190 ns` with no new timing
exceptions. All internal endpoints are constrained; the four asynchronous LED
outputs keep their existing missing-output-delay notices, and Vivado's
standard RAM-mapping advisories remain in the raw reports.

## Arrival-rate screening and what remains

In unblocked ready/valid simulation, consecutive shots need `latency + 2`
clocks between acceptances. That gives `d3-Z` a mean service time of `252.45`
clocks (`2.52 µs`) — 23.5% below a `3.3 µs` (330-clock) target arrival
interval.

Under an idealized infinite-FIFO model at `3.3 µs` arrivals:

- On the 128-shot `d3-Z` trace, peak queue depth drops from 39 waiting jobs
  (baseline) to 9 (optimized).
- Repeating that same 128-shot trace 1,000 times (a stress replay, not 128,000
  independent shots) caps queue depth at 13 waiting jobs versus 38,639 for
  baseline, but individual shots still exceed a 330-clock per-shot deadline on
  92,993 / 128,000 arrivals (peak wait 4,049 clocks; max core latency 2,056
  clocks).

Supporting continuous fault-tolerant QEC would still require a real hardware
input FIFO, sliding-window overlap/commit logic, and persistent Pauli-frame
tracking across rounds.

## Verification and reproduction

`make test` checks Python, native-C, RTL core/bridge/counter regressions, and
paired performance tests (which verify both the ≥15% nonempty speedup and the
1-clock empty-shot fast path). To rerun the checks or rebuild from the
repository root:

```sh
make test
python scripts/simulate.py --bench core --build-dir build/sim/NEW_CORE_RUN
make build IMAGE_DIR=build/NEW_IMAGE VIVADO=/path/to/Vivado/bin/vivado
```

`scripts/simulate.py` also accepts `--vectors PATH` to replay a custom vector
corpus and `--core-source PATH` to compare against an archived RTL baseline.
