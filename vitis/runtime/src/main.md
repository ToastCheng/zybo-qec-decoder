# Runtime firmware parser and GPIO mailbox adapter

`main.c` is independent of `vitis/surface`. It implements D4 requests, 4D responses,
IEEE CRC32 and the runtime mailbox contract in
[`runtime-decoder-plan.md`](../../../docs/runtime-decoder-plan.md). There is no ARM
QEC algorithm, reference fallback, boot-flash operation or old-frame compatibility.

## Native include interface

A harness defines `RUNTIME_NATIVE=1` and includes this source directly. The board
entry point and all BSP includes are then excluded. Public parser functions are:

```c
uint32_t runtime_crc32(const uint8_t *data, size_t length);
void runtime_init(runtime_parser *p, runtime_mailbox_fn mailbox,
                  runtime_emit_fn emit, void *user, uint32_t timeout_ms);
void runtime_feed(runtime_parser *p, uint8_t byte, uint32_t now_ms);
void runtime_tick(runtime_parser *p, uint32_t now_ms);
```

`runtime_mailbox_fn` is `int (*)(void *, uint8_t opcode, uint8_t index,
uint16_t data, uint16_t *read_value)`. Return 0 for accepted, 1 for rejected,
3 for a completed decode error, or 4 for timeout. `runtime_emit_fn` is
`void (*)(void *, const uint8_t *, size_t)` and must synchronously consume/copy
the emitted frame: its buffer has call-local lifetime. Callbacks run synchronously;
use one parser from one thread. Both callbacks receive the same `user` context.

The parser retains at most 521 bytes (five-byte header, 512 payload, four CRC).
Noise before D4 is ignored. Header length overflow is rejected immediately;
CRC failure or unknown command returns invalid. Inter-byte inactivity expires via
`runtime_tick`, using wrap-safe uint32 millisecond subtraction, and clears partial
state. A partial frame with a known sequence receives status 4; a lone D4 is simply
dropped at deadline. After rejection/deadline, the next valid frame is accepted.
For a corrupt length within the legal bound, the sender must allow the partial
frame deadline before recovery; a D4 inside a legitimate payload is not a delimiter.

## Mailbox adapter

`runtime_gpio_init(g, write_control, read_status, now_ms, user, timeout_ms)`
initializes an adapter from current status acknowledgement. The three hooks have
signatures `void (*)(void *, uint32_t)`, `uint32_t (*)(void *)`, and
`uint32_t (*)(void *)`. `runtime_gpio_mailbox` implements the parser callback and
uses the adapter pointer as context.

Each control write is toggle[31] | opcode[27:24] | index[23:16] | data[15:0].
The next command cannot overwrite an unacknowledged previous toggle, including
a command whose host deadline elapsed. Both settling the old ack and waiting for
the new ack are bounded by the monotonic mailbox clock. Error bit 29 means invalid;
for DECODE with result-complete bit 30 it means completed decoder error (status 3).
A successful DECODE additionally requires result-complete bit 30; reset ACK=0
can otherwise alias an outstanding toggle-0 command. Metadata reads return only
status[15:0]. Known staging/metadata indices and reserved
command indices are checked before writing. Syndrome index validity is also
checked by PL against actual configured dimensions.

Serial identity reads metadata 0..14 and zero-extends each 16-bit mailbox word to
a separate uint32 wire field; generation/prediction/cycles halves are not collapsed
in identity. BEGIN stages words 0..2 then sends mailbox 2. APPEND stages words 3..7
(index, a, b, mask low, mask high), then mailbox 3 for each ten-byte record. COMMIT
is mailbox 4. DECODE reads config-valid/count, checks byte count and inactive bits,
writes every active little-endian 16-bit syndrome word through mailbox 5, sends
mailbox 6 and reads PL prediction/error/cycles. Before emitting any result it
compares metadata words 0..9 against the pre-shot identity (including validity,
generation and dimensions), and requires a positive 32-bit cycle count. Cleared or
changed metadata returns status 2 with no result payload. Even a completed error returns its
nine-byte result payload with serial status 3. ABORT maps to mailbox 8.

Graph validation and retention belong to PL. Firmware does not claim a graph
digest; successful identity carries PL dimensions/config-valid/generation only.
Partial graph upload cannot be made usable by firmware: COMMIT acceptance and
config-valid are authoritative.

## Board platform header contract

Compile without `RUNTIME_NATIVE`, with for example
`-DRUNTIME_PLATFORM_HEADER='"runtime_platform.h"'`. That header is included after
the portable implementation and must supply these functions (static inline is
suitable):

```c
void runtime_platform_init(void);
void runtime_platform_write_control(void *ignored, uint32_t value);
uint32_t runtime_platform_read_status(void *ignored);
uint32_t runtime_platform_now_ms(void *ignored);
int runtime_platform_read_byte(void); /* -1 when no UART byte is available */
void runtime_platform_emit(void *ignored, const uint8_t *data, size_t length);
```

The header owns Xilinx BSP includes and UART/GPIO instances. Control/status hooks
map to the separate runtime XGpio control/status channels; the clock must advance
while polling. UART input must be nonblocking, output must complete synchronously,
and initialization must not print text on the binary UART. `emit` receives the
adapter context, so board hooks should ignore the pointer or use board-global
instances. Default `RUNTIME_FRAME_TIMEOUT_MS` is 250; default
`RUNTIME_MAILBOX_TIMEOUT_MS` is 1000, both compile-time overrideable. Mailbox
initialization assumes a reset/settled bridge, not takeover of an in-flight command.

The supplied [Xilinx platform header](runtime_platform.md) implements this contract
with UART1, AXI GPIO MMIO and xiltimer 2025.2. The [builder](../build_app.md) copies
it alongside the unchanged maintained main.c and selects it using a CMake compile
definition. Building without either a platform header or `RUNTIME_NATIVE` fails.
Python tests execute the real production `main` with native BSP doubles.

## Native verification

From repository root:

```sh
cc -std=c11 -Wall -Wextra -Werror -g \
  -fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie \
  qec/surface/test_runtime_firmware.c -o "$TMPDIR/runtime-fw-test"
"$TMPDIR/runtime-fw-test"
```

See [native harness](../../../qec/surface/test_runtime_firmware.md). This verifies
software parsing and command encoding only, not Xilinx BSP linkage or FPGA timing.
