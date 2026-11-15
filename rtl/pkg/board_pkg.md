# Zybo board constants package

Source: [`board_pkg.sv`](board_pkg.sv).

## Contents and consumers

The include guard `BOARD_PKG_SV` protects package declarations. `CLK_FREQ_HZ` is
125 MHz for the PL oscillator, not a declaration of PS FCLK configuration.
`NUM_LEDS`, `NUM_RGB_LEDS`, `NUM_BUTTONS`, and `NUM_SWITCHES` describe board I/O
counts. `RGB_R=2`, `RGB_G=1`, `RGB_B=0` name channels of a `[2:0]` RGB vector.
There are no ports, registers, reset semantics, state machines or algorithm here.

## Invariants and limitations

These are compile-time constants. Importing the package does not constrain pins,
create clocks or configure the generated PS block design. In particular, SoC
latencies must use the configured FCLK frequency rather than this oscillator value.
The comments distinguish the single RGB LED on Z7-10 from the additional Z7-20 LED.

## Verification and related files

With Vivado on PATH, `xvlog --sv rtl/pkg/board_pkg.sv` from the repository root checks
package syntax; run it in an isolated build directory with an absolute source path
to keep generated simulator products out of source. See `constraints/` for actual
pin/clock constraints and [`../top/top_qec_uart.sv`](../top/top_qec_uart.sv) for
explicit UART timing parameters; that top does not import this package.
