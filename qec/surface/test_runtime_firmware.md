# Native runtime firmware tests

`test_runtime_firmware.c` defines `RUNTIME_NATIVE` and includes the actual
[`main.c`](../../vitis/runtime/src/main.c). There is no duplicated parser and no
Xilinx dependency. The injected mailbox is explicitly a software test device:
it stages graph words, tracks ordered indices/commit validity/generation and
returns distinctive fixed prediction/cycle words. It does not implement an ARM
decoder, nor establish that PL executed.

`request` sends individual bytes with timestamps and verifies reply magic,
sequence and independent little-endian CRC extraction. The test covers identity,
BEGIN, edge-word ordering including bit 31 masks, COMMIT, variable-length syndrome
packing, and 32-bit output. The standard `123456789` CRC vector is asserted against
`0xcbf43926`, not just against the parser's own reply checksum.

`test_parser_recovery` feeds corrupt CRC, oversized length, fragmented/truncated
header and payload, every short-frame prefix, unknown opcode and maximum 512-byte
payload. Each failure is followed by a real valid identity request. It exercises
injected busy/configuration failure, mailbox timeout, failed COMMIT leaving the
new graph invalid, not-configured decode, high syndrome bits, wrong syndrome byte
count, completed decoder error payload, and abort retaining configuration.

`test_gpio_adapter` executes the actual toggle adapter with injected control,
status and monotonic-clock hooks. It checks opcode/index packing, readback,
acknowledged PL rejection, completed-decode error status, timeout and subsequent
ack/abort recovery, and rejection of reserved staging/metadata indices. The fake
GPIO is not a simulation of the RTL state machine; RTL acceptance is separate.

`test_reset_during_decode` couples the actual parser to the actual GPIO adapter.
The callback starts ACK=1 so that 15 metadata reads and one syndrome write place
DECODE at toggle 0. Reset clears ACK to the same value, with no completion bit.
The reply must fail with no prediction payload. Separate callback modes inject
invalid configuration, changed generation/dimensions and zero cycles after a
completed ACK; all fail closed. An unchanged positive-cycle control succeeds.

From repository root:

```sh
cc -std=c11 -Wall -Wextra -Werror -g \
  -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
  qec/surface/test_runtime_firmware.c -o "$TMPDIR/runtime-fw-test"
"$TMPDIR/runtime-fw-test"
```

`-fno-pie -no-pie` makes sanitizer address placement deterministic on the native
Linux test host; these flags are not Cortex-A9 firmware build flags. The Python
runtime suite also compiles/runs this harness, so sanitizer errors fail pytest.
Assertions must remain enabled (do not define `NDEBUG`).
