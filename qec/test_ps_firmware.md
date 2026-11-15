# Repetition parser native regression

## Functions and compilation interface

`QEC_NATIVE_TEST` includes the actual `vitis/qec/src/main.c` parser while excluding Xilinx dependencies. Static `decode(s)` increments `calls`, requires syndrome `0x37`, and returns `(7u << 2) | 2u`: ACK 0, correction 1, cycle count 7. `main()` owns a zeroed parser and a six-byte reply buffer.

## Operation and assertions

The four-byte fixture is `A5 42 37 D0` (XOR zero). The first three arrivals must return zero; the fourth must return one. Assertions check sequence echo, correction, both cycle bytes and complete reply XOR. A deliberately wrong final checksum must not call decode; a subsequent valid frame must recover. A two-byte partial frame at 30/31 ms is abandoned before a new frame at 100 ms. Exactly three valid callbacks must have occurred.

## Failure, recovery and scope

This covers normal framing, checksum rejection, sliding recovery and inter-byte expiry. It does not exercise hardware timeout/reset or UART/MMIO paths. Failed assertions terminate the process with nonzero status; success prints the file's `PASS` message and returns normally. Compile without `NDEBUG`, which would disable assertions (and calls embedded in them).

## Run from the repository root

```sh
cc -std=c11 -Wall -Wextra -Werror qec/test_ps_firmware.c -o "$TMPDIR/test_ps_firmware"
"$TMPDIR/test_ps_firmware"
```
