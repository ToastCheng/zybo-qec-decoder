# Surface-code PS firmware

[Source](main.c). ARM firmware parses host frames and drives the PL surface decoder mailbox. `SURFACE_NATIVE_TEST` excludes board headers and main so native tests can include the production parser. `DETECTOR_BYTES` defaults to 3; the current fixed parser buffer has 20 bytes. Changing payload width requires reviewing that buffer bound, not merely changing the define.

## Parser and wire contract

`struct parser` holds the candidate bytes, count and last arrival time. `shift()` discards one byte, retaining a possible embedded sync. `feed(p, byte, ms, out, decode)` consumes a byte, invokes the callback only for a valid complete normal/reset frame, and returns a completion flag (0 or 1). The caller supplies a nine-byte output buffer.

Requests are `C3 sequence length payload XOR`, with total XOR zero. Length must be `DETECTOR_BYTES` for decode or zero for reset. There is no identity opcode. Replies are nine bytes: `3C sequence error prediction cycles_le32 XOR`. Error comes from status bit 29, or equals 2 for the `0xffffffff` timeout/load-failure sentinel. Reset forces prediction zero; otherwise it comes from bit 28. The low 28 cycle bits are serialized in four bytes. Timeout retains `0x0fffffff` there, which is not a measured latency. Sequence is echoed without replay suppression.

A partial candidate expires on the next byte after a gap greater than 50 ms; unsigned subtraction handles timer wrap. Bad lengths/checksums cause one-byte sliding and re-examination. Idle non-sync bytes are ignored. A valid frame clears the buffer. Idle time alone does not invoke parser recovery.

## Mailbox and board flow

`command(op,index,data)` writes AXI GPIO at `0x41200000`: toggle bit 31, opcode bits 27:24, index bits 23:16, data bits 15:0. It polls offset +8 until ACK bit 31 matches, with a 1000 ms deadline per command. Status bits 30/29/28 are result/error/prediction and 27:0 are cycles. Timeout returns all ones without automatic reset or toggle resynchronization.

`decode_pl` uses opcode 3 for reset. Otherwise opcode 1 loads consecutive little-endian 16-bit words (zero-extending an odd final byte), aborting on load failure, then opcode 2 starts decode and waits for acknowledgement. `now_ms` reads the Xilinx timer. `main` sets 115200-baud normal UART, adopts current ACK phase, requests reset, then polls RX and sends nine bytes after each completed frame. UART configuration/baud errors return 1/2. Initial reset's result is ignored and UART sends have no separate firmware deadline.

## Verification

```sh
vitis -s vitis/surface/build_app.py
cc -std=c11 -Wall -Wextra -Werror qec/surface/test_firmware.c -o "$TMPDIR/test_firmware"
"$TMPDIR/test_firmware"
```

Native tests check parser callbacks, checksum, timeout and recovery, not physical UART or board MMIO. Keep firmware width consistent with the [bridge](../../../rtl/common/surface_ps_bridge.md) and selected graph ROM.
