# Word-loaded surface decoder mailbox

Source: [`surface_ps_bridge.sv`](surface_ps_bridge.sv).

## Interface and command layout

All signals use one clock. A new command arrives when `ctrl[31] != status[31]` in IDLE. PS holds the complete command stable until the acknowledged toggle matches. Control fields are `[31] toggle`, `[27:24] opcode`, `[23:16] index`, `[15:0] payload`; `[30:28] are unused. Status is `{ack, result, error, prediction, cycles[27:0]}`.

## State transitions

- Opcode 1 loads a little-endian 16-bit syndrome word. Index must be below `(DETECTORS+15)/16`; an invalid index acknowledges with error. Padding bits are stored but only the detector-width slice reaches the core. Loading one word does not clear the others.
- Opcode 2 clears the status payload without acknowledging. LAUNCH holds core valid until ready. WAIT_RESULT captures the always-ready result and acknowledges the saved toggle. Core errors or cycle overflow above bit 27 set the error flag.
- Opcode 3 clears the shot and pulses synchronous core reset. RESET_ACK waits until the core has sampled reset before acknowledging with a zero payload.
- Unknown opcodes acknowledge with error and do not decode.

Commands presented while busy are not queued. External reset clears state, status, shot and saved request. An invalid FSM state resets the core and returns to IDLE; software owns recovery of its toggle convention. This is not a clock-domain crossing or a streaming interface. Graph dimensions and ROM are synthesis parameters; no runtime graph upload or identity query is implemented.

## Verification

From the repository root run `make sim_surface` then `make sim_bridge` with Vivado tools on PATH. The d3 Z vector file produced by the first command is required by `qec/surface/tb_bridge.sv`. Checks cover word loading, prediction, measured cycles, bounds, reset and recovery. See [the decoder](surface_decoder.md), [SoC shell](../top/top_surface_soc.md) and [firmware](../../vitis/surface/src/main.md).
