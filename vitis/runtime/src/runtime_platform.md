# Xilinx runtime board platform

`runtime_platform.h` supplies the static inline hooks consumed by the production
[`main.c`](main.md) entry point. It is included after the portable parser; it
contains peripheral access only, not a CPU decoder. Build with
`-DRUNTIME_PLATFORM_HEADER='"runtime_platform.h"'`, supplied automatically by the
[runtime builder](../build_app.md). It does not depend on `vitis/surface`.

## Hardware and BSP contract

- Vitis Unified 2025.2 standalone/SDT BSP for `ps7_cortexa9_0`.
- PS UART1 at `0xe0001000`, enumerated as `XPAR_XUARTPS_0_BASEADDR` when it is
  the sole enabled UART. A compile-time check rejects a different address.
- UART configuration lookup uses the SDT base address, not a legacy device ID.
  Initialization sets 115200 baud and normal mode; the driver's reset defaults
  provide 8 data bits, no parity and one stop bit.
- AXI GPIO at `0x41200000`: channel 1 DATA at +0 is control, TRI at +4 is all
  output; channel 2 DATA at +8 is status, TRI at +12 is all input. This is the
  same-FCLK mailbox exported by the runtime SoC, not an asynchronous crossing.
- `xiltimer.h` provides `XTime`, `XTime_GetTime` and `COUNTS_PER_SECOND` through
  the generated `xtimer_config.h`. The BSP constructor initializes xiltimer;
  no interrupts or software tick counter are required here.

`runtime_platform_init` owns one static UART instance, checks lookup/configuration/
baud failures and exits silently with failure if any occur. It never prints a
banner, sends a mailbox command or writes the control DATA register. `main` then
adopts the settled PL acknowledgement phase. Start only with a reset/settled
bridge; restarting just the CPU during an in-flight command is not supported.
The BSP/bootloader's earlier console output is outside this header's control.

## Polling and binary bytes

`runtime_platform_read_byte` checks receive availability once. It returns -1
without blocking when empty and otherwise returns exactly one FIFO byte as
0..255, including zero. This lets the production idle loop enforce partial-frame
deadlines. `runtime_platform_emit` sends every byte with `XUartPs_SendByte`, then
waits until both the transmit FIFO is empty and the transmitter is inactive.
No string functions or newline translation are involved. Transmission polling is
synchronous and has no independent timeout if a UART peripheral stops responding.

`runtime_platform_now_ms` converts the free-running counter to whole milliseconds
with quotient/remainder arithmetic. It neither rounds the frequency down to
counts per millisecond nor multiplies the entire counter by 1000. Parentheses
around `COUNTS_PER_SECOND` are essential: the actual generated BSP expands it to
`XPAR_CPU_CORE_CLOCK_FREQ_HZ/2` without grouping. The uint32 result deliberately
wraps; parser/mailbox deadlines use unsigned subtraction and must be shorter than
one full uint32 millisecond period. The clock is monotonic modulo that wrap.

## Timeout safety and recovery limitation

The hooks do not track or reset mailbox phase. The maintained parser's
`runtime_gpio_mailbox` waits for the outstanding ACK before another toggle. A
late ACK permits subsequent commands; a timeout never authorizes toggling again.
Native tests verify both paths using these actual platform MMIO hooks.

**An indefinitely unacknowledged PL decode cannot be recovered by the current
parser/protocol.** Serial ABORT also waits for the outstanding ACK and returns
status 4 without issuing a new control write. The bridge cannot see that abort
while busy. Recovery requires the existing command to finish or an independently
controlled PL reset/resynchronization mechanism; neither is supplied by this
header. Do not implement a second toggle as an apparent timeout fix: it can erase
the outstanding request and desynchronize the mailbox. No board reset/programming
is performed by this implementation.

## Verification

Run `python -m pytest qec/tests/test_runtime_platform.py qec/tests/test_runtime_build.py -q`.
The [platform tests](../../../qec/tests/test_runtime_platform.md) compile and run
this real header through the maintained production `main.c` with native BSP
doubles, strict compiler warnings and ASan/UBSan. Their vendor builder test uses
fake exports but real CMake/native object compilation. These are not proof of
Xilinx library linkage, ARM execution, PL decoding or physical-board operation;
the matching routed hardware/board acceptance remains separate.

A real Vitis Unified 2025.2 compile/link was also executed using a no-bitstream
XSA exported from the existing runtime synthesis checkpoint into
`build/runtime-firmware-platform-probe`. It produced an ARM EABI5 hard-float
`runtime_app.elf`, linked against the generated standalone BSP and xiltimer.
The maintained/imported main.c and runtime_platform.h were byte-identical.
This verifies BSP API and linker integration, not execution on ARM or successful
100 MHz timing; it must not be used as a programmed-image acceptance artifact.
