# Two-edge repetition-code LUT decoder

Source: [`qec_decoder.sv`](qec_decoder.sv).

## Interface and bit contract

`clk` drives synchronous active-high `rst`. Accept an eight-bit completed shot on
`in_valid && in_ready`; syndrome bit i is detector i and the full byte is the ROM
address. `LUT_FILE` initializes 256 packed one-bit words. The packed representation
is deliberate for Vivado initialization, not an interchangeable scalar-array style.
`prediction` is one logical-flip bit, not a physical correction.

## State and timing walkthrough

- `IDLE` accepts and registers `syndrome` as `address`.
- `READ` registers `lut[address]` in `rom_value`.
- `RESULT` copies that bit to `prediction`, writes `cycles = 2`, and enters `HOLD`.
- `HOLD` asserts `out_valid` and keeps the result until `out_ready`, then returns
  to `IDLE`. Input cannot be accepted on the retirement edge itself.

The first valid result appears two rising edges after acceptance. `cycles` is
schedule metadata, not a running timestamp. Reset gates both handshake outputs
combinationally and clears state/data at the rising edge, aborting an in-flight or
held shot. ROM contents are not reset. There is only one outstanding request and
no continuous-round streaming or runtime table loading.

## Verification and related files

From the repository root: `python scripts/qec_sim.py` exhaustively checks all 256
addresses, exact result timing, backpressure, reset abort and UART integration.
See [`../tb/tb_qec_decoder.sv`](../tb/tb_qec_decoder.sv),
[`qec_ps_bridge.sv`](qec_ps_bridge.sv), and `qec/lut.mem` (root-relative).
After core synthesis, `python scripts/qec_sim.py --netlist` checks initialized ROM
behavior in the synthesized design; it requires `build/qec_core/post_synth.v`.
