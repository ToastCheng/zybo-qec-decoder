# Same-clock repetition decoder mailbox

Source: [`qec_ps_bridge.sv`](qec_ps_bridge.sv).

## Register interface

Both AXI GPIO and core use PS `FCLK_CLK0`; this module is not a CDC synchronizer.
`ctrl[7:0]` is the syndrome, `[8]` the request toggle, `[9]` software reset.
`status[0]` is the completed toggle, `[1]` the prediction, `[17:2]` the 16-bit elapsed
core latency, and `[31:18]` zero. PS must hold the request stable until the returned
toggle matches. A level-valid request would not be interchangeable with this protocol.

## Transaction and reset semantics

A toggle mismatch launches only while `!busy` and not reset. Acceptance records
`start_tick`, saves the toggle in `request`, and sets `busy`/`launched`. The core
always has `out_ready = 1`. On observing its valid result, the bridge publishes
prediction, saved toggle and `ticks - start_tick - 1`, then clears the busy flags.
The subtraction removes the one-edge observer delay: the result became available
after the preceding edge. The decoder's `schedule_cycles` wire is not returned.
`ticks` increments even during reset and subtraction is modulo its 32-bit width;
only 16 latency bits fit in status.

`rst || ctrl[9]` synchronously clears status and bridge state and resets the core.
Holding software reset high prevents launches. A mismatching toggle after reset
is a fresh request; software must reestablish its toggle convention.

## Verification and related files

Run `make sim_bridge` from the root with Vivado tools on PATH, after
`make sim_surface` creates the surface bridge vectors. The repetition test
`qec/tb_ps_bridge.sv` exhausts 256 syndromes, checks independent acceptance/result
edges, stable acknowledgement and software-reset recovery. See
[`qec_decoder.sv`](qec_decoder.sv), [`../top/top_qec_soc.sv`](../top/top_qec_soc.sv),
and `vitis/qec/src/main.c` for the consumer. No board programming is needed.
