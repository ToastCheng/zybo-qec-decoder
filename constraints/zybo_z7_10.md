# `zybo_z7_10.xdc`

[Source](zybo_z7_10.xdc). Physical and clock constraints for the Zybo Z7-10 pure-PL UART top, not the PS/FCLK SoC designs.

## Board interface

The 125 MHz single-ended clock uses K17 with an 8 ns period and a 0/4 ns waveform. All listed GPIO uses LVCMOS33. The file maps four active-high push buttons, four switches, four single-color LEDs and RGB LED LD6; RGB vector indices 2, 1 and 0 are red, green and blue. The commented LD5 pin list is Z7-20-only and is not an active constraint.

PL UART RX uses Pmod JE1/V12 with a pull-up; PL UART TX uses JE2/W16. Connect host TX to FPGA RX, host RX to FPGA TX and a common ground, using 3.3 V TTL only. The onboard USB UART is connected to the PS, so it cannot substitute for this Pmod wiring.

## Timing scope

`scripts/qec_build.tcl` reads this file in UART mode and adds external asynchronous false paths for inputs and outputs. Those exceptions are not specified here. Internal clocked paths remain timed. Read the post-route reports and DRC before interpreting timing; the XDC itself does not establish UART correctness or board operation.

The PS/PL SoC tops instead use their own `top_*_soc.xdc` files and the PS7-generated 100 MHz FCLK constraint.
