# Parameterized graph decoder acceptance bench

Source: [`tb_surface.sv`](tb_surface.sv).

## Parameters, vectors and clock

`surface_core_test` takes `N`, `E`, `CASES`, `GRAPH` and `VECTORS`. It reads each
`N+2`-bit vector as `{syndrome[N-1:0], error, prediction}` and instantiates the real
surface decoder with that graph. Clock period is 10 ns. `tb_surface_d3` is only a
one-case convenience wrapper; the Python runner generates `tb_surface_run` with
the actual corpus count and paths. Running the default wrapper alone does not
exercise the full generated corpus.

## Acceptance, availability and stalls

Each case waits for ready, drives syndrome/valid at a falling edge, records the
acceptance tick at the rising edge, and checks after NBA updates. Waiting for
out_valid is bounded to 500000 cycles. Both error and prediction must match the
reference vector; `cycles` must equal independently observed edge separation, not
merely a copied expected constant. The bench then stalls retirement for three
cycles, requiring valid and stable error/prediction, before pulsing ready.

After all vectors, it launches a dense shot, resets it during execution, and
requires ready with no leaked output after reset. A separate 1000000000 ns watchdog
catches global stalls. The held-result loop does not explicitly recheck cycle
stability; the implementation freezes cycles in HOLD. It does not test UART or
mailbox framing, synthesized graph ROMs, or physical timing.

## Verification and related files

From root run `python qec/surface/sim.py --distance 3 --basis z --shots 256`;
repeat with d5 Z/128 and d3 X/128, or use `make sim_surface`. The runner generates
real Stim shots plus zero, single-detector, edge and dense random cases using the
reference in `qec/surface/decoder.py`.
See [`../../rtl/common/surface_decoder.sv`](../../rtl/common/surface_decoder.sv)
and [`tb_bridge.sv`](tb_bridge.sv).
