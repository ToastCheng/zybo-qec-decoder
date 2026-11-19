# Decoder performance

The UF tables use RTL latency, modeled service capacity/FIFO waiting time, and an archived full-SoC route at 100 MHz. The separate d3 comparison below reports measured board execution of UF and optimized exact matching. Neither study establishes continuous-QEC operation.

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

These are full-SoC totals, not per-distance or core-only estimates. The simulated core is byte-identical to the archived routed core. Timing closure at this clock does not establish Fmax or board latency. That UF route predates the matching board comparison below.

## On-board d3 comparison

Both complete decoders ran in PL on Zybo Z7-10 at 100 MHz, using the same
4,096 real d=3/r=3 Z-memory shots at p=0.001. All four Stim noise parameters
were set to p.

| PL decoder | Mean core latency (µs) | Median (µs) | Observed max (µs) |
| --- | ---: | ---: | ---: |
| Maintained UF | 2.072122 | 0.01 | 24.57 |
| Optimized exact matching | 0.850854 | 0.01 | 5.12 |

Matching takes 512 cycles for every nonempty syndrome and one cycle for zero.
There were 3,422 empty real syndromes. Its parallel frontier preserves the exact
weighted objective and deterministic ties; the nonempty serial baseline took
9,826 cycles. The optimization trades area for latency: the matching full SoC
uses 11,981 LUTs, 8,126 flip-flops and one BRAM36-equivalent tile, with routed
setup/hold slack +0.027/+0.032 ns and zero DRC findings.

Matching remains fixed to the 24-detector/78-edge/one-observable graph and its
p=0.001 weights. There is no d=5 PL matching implementation or measured d=5
matching latency. The d=5 matching accuracy curve is the software PyMatching
reference; it cannot be used to infer hardware timing or resource use.

Cycle counts cover complete-syndrome acceptance through final observable
availability, excluding UART, ARM transport, graph upload and retirement stalls.
The independent adapter counter and RTL edge counter agree with every board
reply. In total, each core decoded 5,703 vectors, including stress/diagnostic and
accuracy-coverage patterns; only the 4,096 real shots enter the table. Sustained
service capacity and backlog were not measured for matching.

[Board report and raw evidence](https://github.com/ToastCheng/qc-research/blob/feat/fpga-qec/fpga-qec/matching-optimization/REPORT.md)
include all 11,406 successful decode replies, paired accuracy, bit/XSA/ELF hashes,
route reports and restoration checks. The compatible UF image and public server
were restored after the experiment; no flash writes were performed.

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
