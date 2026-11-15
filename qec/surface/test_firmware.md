# Surface parser default-size native regression

## Functions and compilation interface

`SURFACE_NATIVE_TEST` includes the maintained parser directly and omits Xilinx code. `decode_test(data, bytes)` counts every call, returns zero for reset, otherwise requires bytes `12 34 56` and returns completion bit 30, prediction bit 28 and cycle count 98321. `main()` provides a zeroed parser and nine-byte output buffer.

## Operation and assertions

The fixture is `C3 25 03 12 34 56 XOR`; the checksum is calculated locally. Completion must occur only at the seventh byte. Assertions verify `3C` response marker, sequence, zero error, prediction 1, little-endian 32-bit cycles and XOR-zero reply. The test corrupts one checksum, sends a valid recovery frame, then abandons a two-byte partial request before a >50 ms gap. Finally `C3 28 00 EB` must invoke the zero-length reset callback. Total callbacks must be four.

## Failure, recovery and scope

The reset uses a callback, not PL. This file covers the default three-byte payload, not configurable sizes, identity, mailbox timeout or physical UART behavior. Failed assertions terminate the process with nonzero status; success prints the file's `PASS` message and returns normally. Compile without `NDEBUG`, which would disable assertions (and calls embedded in them).

## Run from the repository root

```sh
cc -std=c11 -Wall -Wextra -Werror qec/surface/test_firmware.c -o "$TMPDIR/test_firmware"
"$TMPDIR/test_firmware"
```
