# Exhaustive repetition GPIO latency bench

Source: [`tb_ps_bridge.sv`](tb_ps_bridge.sv).

## Clock, mailbox and oracle

A 10 ns clock drives the real repetition bridge. The bench loads the packed one-bit
`qec/lut.mem` oracle. `ctrl[8]` carries a request toggle and `[7:0]` the syndrome;
`status[0]` acknowledges, `[1]` returns prediction, and `[17:2]` returns latency.
Requests remain stable until acknowledged, with a 30-cycle timeout per shot.

## Independent timing and recovery checks

A rising-edge monitor records `dut.in_valid && dut.in_ready` before NBA updates,
then samples `dut.out_valid` after a one-unit delay. A falling-edge tick counter
supplies an independent edge scale. Across all 256 syndromes, both mailbox latency
and availability-minus-acceptance must equal two. Prediction must match the LUT,
and five additional idle cycles must not change the completion toggle.

The final software-reset request (`ctrl = 0x200`) must clear status. A fresh toggle
with zero syndrome (`0x100`) must decode correctly afterward. A global 200000 ns
watchdog bounds the run. This checks direct GPIO wires, not AXI bus timing, firmware
serial framing, or physical FCLK frequency. It does not independently regenerate
the PyMatching-derived table.

## Verification and related files

Run `make sim_surface` then `make sim_bridge` from root with Vivado tools on PATH;
the first target creates vectors needed by the companion surface bridge bench.
See [`../rtl/common/qec_ps_bridge.sv`](../rtl/common/qec_ps_bridge.sv),
[`../rtl/common/qec_decoder.sv`](../rtl/common/qec_decoder.sv), and
[`surface/tb_bridge.sv`](surface/tb_bridge.sv).
