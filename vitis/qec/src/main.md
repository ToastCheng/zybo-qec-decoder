# Repetition-code PS firmware

`main.c` implements the bare-metal UART-to-AXI-GPIO adapter, not the decoder algorithm. Define `QEC_NATIVE_TEST` to omit Xilinx headers, MMIO and the board entry point while retaining the same static parser for native tests.

## Functions and operation

- `struct parser`: four-byte candidate buffer `b`, occupied count `n`, and last input time `last_ms`.
- `feed(p, byte, ms, out, decode)`: accepts one byte; returns 1 only when six reply bytes were produced. `decode(uint8_t)` receives the syndrome synchronously. A return of zero can mean incomplete/invalid input or a hardware timeout.
- `now_ms()`: converts the Xilinx timer count into a wrapping 32-bit millisecond clock.
- `reset_pl()`: asserts control bit 9, holds it for 10000 volatile loop iterations, then clears the control register and software toggle.
- `decode_pl(syndrome)`: toggles request phase, writes the syndrome, polls the acknowledgement, and resets PL on timeout.
- `main()`: initializes UART in normal mode at 115200 baud, resets PL, then polls RX and sends complete replies. Initialization returns 1 for missing/configuration failure and 2 for baud-rate failure.

## Interfaces

Request bytes are `A5 sequence syndrome checksum`; XOR of all four must be zero. Response is `5A sequence correction cycles_low cycles_high checksum`, also XOR-zero. The sequence byte is echoed, not used for deduplication. GPIO base is `0x41200000`: control at +0 carries syndrome bits 7:0, request toggle bit 8 and reset bit 9. Status at +8 carries ACK phase bit 0, correction bit 1, and a 16-bit cycle count in bits 17:2. Polling requires phase equality; it does not wait for a busy bit.

## Failure and recovery boundaries

A gap strictly greater than 50 ms discards partial input when the next byte arrives; subtraction is unsigned to tolerate clock wrap. Bad checksum candidates slide left, retaining any embedded `A5` for resynchronization. Non-sync bytes at idle are ignored. Each PL decode has a 100 ms polling deadline. On expiry, firmware resets PL and returns `0xffffffff`; `feed` consumes that request without replying. The host must time out/retry; there is no wire timeout status here. UART transmission is synchronous, without an additional firmware deadline.

## Build and native check

From repository root:

```sh
make build_soc SOC_TOP=top_qec_soc
vitis -s vitis/qec/build_app.py
cc -std=c11 -Wall -Wextra -Werror qec/test_ps_firmware.c -o "$TMPDIR/test_ps_firmware"
"$TMPDIR/test_ps_firmware"
```

The native test substitutes a callback; it does not validate timer/MMIO/UART behavior or program a board.
