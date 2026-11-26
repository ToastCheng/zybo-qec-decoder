# Decoder performance

This page covers two sets of measurements at 100 MHz (`10 ns` per clock) on
the Zybo Z7-10 (`xc7z010clg400-1`):

1. **Default runtime union-find (UF) core:** RTL simulation latency, modeled
   FIFO queue wait, and full-SoC resource usage (the numbers summarized in the
   README).
2. **On-board `d=3` and `d=5` comparison:** real Zybo Z7-10 hardware latency
   and resource trade-offs across three programmable-logic decoders — runtime
   UF, programmable 4-lane BRAM exact matching, and fixed-`d=3` 32-lane FF
   exact matching.

All benchmarks decode complete three-round memory shots rather than a
continuous streaming QEC feedback loop.

## Runtime UF latency and service capacity (RTL simulation)

These numbers come from simulating the maintained UF core (`qec_decoder.sv`)
on 256 shots of three-round rotated Z memory at `p = 0.001`:

| Workload | Empty syndromes | Mean RTL latency (µs) | p95 (µs) | Observed max (µs) | Modeled capacity (k jobs/s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| d3 Z memory | 215 / 256 | 2.0206 | 15.97 | 19.29 | 490.05 |
| d5 Z memory | 158 / 256 | 17.7691 | 67.05 | 88.81 | 56.21 |

- **Latency scope:** counts clock cycles from core acceptance (`in_valid &&
  in_ready`) to the first cycle `out_valid` goes high. It excludes Stim
  sampling, graph uploads, ARM firmware, UART transfer, and downstream stalls.
- **Empty syndromes:** at `p = 0.001`, most shots have an all-zero syndrome
  and finish in 1 clock (`10 ns`), which pulls down the mean while nonempty
  shots dominate the p95 (nearest-rank) and observed maximum.
- **Modeled capacity:** the unblocked ready/valid testbench shows that
  back-to-back shots require `latency + 2` clocks between acceptances, so
  capacity is calculated as `100,000,000 / (mean_cycles + 2)`.

## FIFO backlog model

To see how bursty nonempty shots behave under steady arrivals, we feed the 256
simulated shots (in sample order, without repeating them) into a simple
single-server model with an unbounded first-in, first-out (FIFO) queue. Each
job occupies the core for `latency + 2` clocks, and wait time is `service
start - arrival time`.

| Workload | Arrival interval (µs) | Offered rate (k jobs/s) | Maximum modeled wait (µs) |
| --- | ---: | ---: | ---: |
| d3 Z memory | 3.3 | 303.03 | 46.58 |
| d3 Z memory | 10 | 100.00 | 14.23 |
| d5 Z memory | 3.3 | 303.03 | 3,728.82 |
| d5 Z memory | 10 | 100.00 | 2,079.59 |

At `d=3`, mean capacity (490k jobs/s) stays ahead of both arrival rates,
though clusters of nonempty shots still create temporary queue wait. At `d=5`,
both arrival rates outpace the core's 56k jobs/s capacity and the backlog
grows throughout the trace. No physical hardware FIFO was built or tested.

## Runtime UF full-SoC resources

Full routed Zybo Z7-10 SoC at 100 MHz (capacity: 128 detectors, 512 edges,
32 observables):

| Resource or timing metric | Value |
| --- | ---: |
| Slice LUTs | 9,048 |
| Flip-flops | 3,195 |
| BRAM36 tiles | 1.5 |
| Setup WNS (ns) | +0.190 |
| Hold WHS (ns) | +0.042 |

These totals include the Zynq PS interface, AXI GPIO, mailbox bridge, and
decoder core together, and close timing cleanly at 100 MHz.

## On-board `d=3` and `d=5` decoder comparison

All measurements below were recorded over UART from actual programmable-logic
execution on the connected Zybo Z7-10 at 100 MHz (three extraction rounds,
`p = 0.001`):

| PL image | Workload | Shots | Mean core latency (µs) | Nonempty / observed max (µs) | Routed LUT / FF / BRAM36 | Setup / hold slack (ns) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Maintained runtime UF (`128/512/32`) | d3 X / d3 Z | 8,000 / 8,000 | 1.985 / 1.944 | 24.68 / 24.43 | 9,048 / 3,195 / 1.5 | +0.190 / +0.042 |
| Maintained runtime UF (`128/512/32`) | d5 X / d5 Z | 1,500 / 1,500 | 15.735 / 18.520 | 103.11 / 130.22 | 9,048 / 3,195 / 1.5 | +0.190 / +0.042 |
| Programmable exact matching (`fpga/experimental/frontier/`, 4-lane BRAM, width ≤ 12) | d3 X / d3 Z | 8,000 / 8,000 | 8.344 / 7.999 | 51.10 / 51.10 | 3,090 / 3,247 / 18 | +0.954 / +0.028 |
| Programmable exact matching (`fpga/experimental/frontier/`, 4-lane BRAM, width ≤ 12) | d5 X / d5 Z | 1,500 / 1,500 | 4,104.73 / 4,513.77 | 10,764.14 / 10,764.14 | 3,090 / 3,247 / 18 | +0.954 / +0.028 |
| Fixed-d3 exact matching (`fpga/experimental/matching/`, 32-lane FF, width 5) | d3 Z | 4,096 | 0.851 | 5.12 | 11,981 / 8,126 / 1 | +0.027 / +0.032 |

### How the three hardware architectures compare

Both exact-matching images solve minimum-weight matching in programmable logic
using parity-frontier dynamic programming with lossless integer edge weights,
explicit infinity saturation, a 1-cycle zero-syndrome fast path, and a second
independent cycle counter checked on every shot:

- **Fixed-`d=3` 32-lane FF matching (`fpga/experimental/matching/`):** Unrolls
  all `2^5 = 32` frontier states in flip-flops for the 102-op `d=3` Z graph.
  It is the fastest core at `d=3` — `512` clocks (`5.12 µs`) for any nonempty
  shot and `0.851 µs` mean — beating runtime UF on both speed and accuracy,
  at the cost of 68% of the Zybo's LUTs and a fixed graph.
- **Programmable 4-lane BRAM matching (`fpga/experimental/frontier/`):**
  Stores up to `2^12 = 4,096` frontier states in 18 BRAM36 tiles using only
  3,090 LUTs, allowing both `d=3` and `d=5` programs to be uploaded at
  runtime. Because frontier state count scales as `2^width`, a nonempty shot
  takes `5,110` clocks (`51.10 µs`) on `d=3` (width 5) and `1,076,414` clocks
  (`10.76 ms`) on `d=5` (width 11, 2,048 states, 350 ops).
- **Maintained runtime UF (`fpga/rtl/`):** Accepts arbitrary graphlike
  circuits up to 128 detectors / 512 edges with only 1.5 BRAM36 tiles, and
  stays in the microsecond range at `d=5` (`15.7–18.5 µs` mean) because its
  cost grows with edge scans rather than `2^width`.

Raw board logs, wire archives, and route reports live in
[fpga-four-curve-benchmark](https://github.com/ToastCheng/qc-research/tree/feat/fpga-qec/fpga-qec/fpga-four-curve-benchmark)
and
[matching-optimization](https://github.com/ToastCheng/qc-research/blob/feat/fpga-qec/fpga-qec/matching-optimization/REPORT.md).
The runtime UF image and web server were restored after the comparison runs
with no flash writes.

## RTL sweep methods and reproduction

For the RTL sweep tables above, Stim 1.16.0 generated
`surface_code:rotated_memory_z` (all four noise channels set to `p`, seed
`123`, 256 shots per point across `p = 0.0001, 0.0003, 0.001, 0.003, 0.01` for
`d=3` and `d=5`, three rounds). `d=3` compiles to 24 detectors / 78 edges and
`d=5` to 72 detectors / 278 edges. Vivado 2025.2 ran `fpga/rtl/tb/tb_decoder.sv`
against `fpga/rtl/common/qec_decoder.sv`, verifying all 2,560 sampled shots
against Python UF and counting clock edges independently. Full logs, per-state
profiles, queue CSVs, and route reports are archived in
[sweep-20261119-final](https://github.com/ToastCheng/qc-research/tree/feat/fpga-qec/fpga-qec/readme-benchmarks/timing/sweep-20261119-final)
under archive key `optimized`.

To reproduce the RTL timing sweep from the repository root (with Stim 1.16.0,
PyMatching 2.4.0, NumPy 2.5.5, Matplotlib 3.11.2, Vivado 2025.2, and the
research repository available):

```sh
PYTHONPYCACHEPREFIX=build/readme-timing-cache \
MPLCONFIGDIR=build/readme-timing-mpl \
python scripts/benchmark_timing.py run \
  --data /path/to/new-benchmark-run \
  --study /path/to/qc-research/fpga-qec/core-scan-study \
  --vivado-bin /path/to/Vivado/bin \
  --images build/benchmark-figures \
  --shots 256 --seed 123
```

The script compares the current core (`optimized`) against the archived
pre-optimization baseline using fresh simulator directories under `build/sim/`.
