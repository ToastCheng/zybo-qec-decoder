# Decoder performance

These tables describe the current decoder at 100 MHz: latency comes from RTL simulation, capacity and FIFO waiting time are modeled from measured cycles, and resource counts come from an archived full-SoC route. They are not new board measurements or continuous-QEC validation.

## Latency and service capacity

Z-memory experiments use three extraction rounds, p = 0.001 and 256 shots per distance.

| Workload | Empty syndromes | Mean RTL latency (µs) | p95 (µs) | Observed max (µs) | Modeled capacity (k jobs/s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| d3 Z memory | 215 / 256 | 2.0206 | 15.97 | 19.29 | 490.05 |
| d5 Z memory | 158 / 256 | 17.7691 | 67.05 | 88.81 | 56.21 |

Latency runs from core acceptance to the first available result. It excludes sampling, acquisition, graph uploads, ARM firmware, UART, host calls, queueing and held-result stalls. Means include empty syndromes; p95 uses the nearest-rank statistic. These are empirical statistics, not worst-case bounds.

The unblocked ready/valid probe independently verifies an initiation interval equal to result latency plus two clocks. Estimated capacity is 100,000,000 divided by mean service cycles, including those two clocks; it is not measured hardware throughput.

## FIFO backlog model

One nonpreemptive server processes the 256 sampled jobs once, in sample order, with a fixed resident graph, immediate result consumption and an infinite modeled first-in, first-out (FIFO) queue.

| Workload | Arrival interval (µs) | Offered rate (k jobs/s) | Maximum modeled wait (µs) |
| --- | ---: | ---: | ---: |
| d3 Z memory | 3.3 | 303.03 | 46.58 |
| d3 Z memory | 10 | 100.00 | 14.23 |
| d5 Z memory | 3.3 | 303.03 | 3,728.82 |
| d5 Z memory | 10 | 100.00 | 2,079.59 |

For each arrival, service starts when both the job has arrived and the server is free; waiting time is service start minus arrival time. Service occupies measured latency plus two clocks. These values describe waiting time, not FIFO depth. No hardware queue or overflow behavior was tested, and no sample sequence was repeated.

The d3 mean capacity exceeds both offered rates, but bursts still cause waiting. Both rates exceed d5's estimated capacity. A finite trace does not prove sustained backlog-free operation or deadline guarantees; these independent terminal-readout jobs have no continuous-window detector history.

## Routed resource cost

The full SoC targets `xc7z010clg400-1` at 100 MHz, with capacity for 128 detectors, 512 edges and 32 observables.

| Resource or timing metric | Value |
| --- | ---: |
| Slice LUTs | 9,048 |
| Flip-flops | 3,195 |
| BRAM36 tiles | 1.5 |
| Setup WNS (ns) | +0.190 |
| Hold WHS (ns) | +0.042 |

These are full-SoC totals, not per-distance or core-only estimates. The simulated core is byte-identical to the archived routed core. Timing closure at this clock does not establish Fmax or board latency. No new route or board programming was performed.

## Methods and evidence

Stim 1.16.0 generates `surface_code:rotated_memory_z`, with all four noise arguments set to p: `after_clifford_depolarization`, `before_round_data_depolarization`, `before_measure_flip_probability` and `after_reset_flip_probability`. Each circuit uses seed 123 and one batch of 256 shots. The wider archived sweep covers p = 0.0001, 0.0003, 0.001, 0.003 and 0.01 for d3 and d5, always with three rounds; equal seeds do not imply independent datasets across points.

The graph compiler validates the detector error model and produces ordered unweighted edges: 24 detectors / 78 edges for d3, and 72 / 278 for d5. Vivado 2025.2 runs the maintained `fpga/rtl/tb/tb_decoder.sv` against `fpga/rtl/common/qec_decoder.sv`. The bench checks predictions against the Python decoder and independently counts clock edges. All 2,560 sampled shots pass; five extra protocol diagnostics are excluded from the tables. Accuracy against observable truth is reported in the [separate accuracy benchmark](benchmark-accuracy.md).

[Raw evidence](https://github.com/ToastCheng/qc-research/tree/feat/fpga-qec/fpga-qec/readme-benchmarks/timing/sweep-20261119-final) includes exact circuits, shot vectors, simulator logs, per-state profiles, initiation checks, queue CSVs, source snapshots, route reports, provenance and SHA256 manifests. The current implementation's records use the archive key `optimized`; historical comparison records remain unchanged in that archive.

## Reproduction

Install Stim 1.16.0, PyMatching 2.4.0, NumPy 2.5.5 and Matplotlib 3.11.2 in a private environment under `build/`. With Vivado 2025.2 and the research repository available, run from the implementation root using a new data directory:

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

The archival study script runs the current core plus a historical reference check and retains their original archive keys. Use only the `optimized` records for these tables. Simulator scratch stays in fresh directories under `build/sim/`; generated comparison figures are not part of the README.
