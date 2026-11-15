/* Includes the real parser in this translation unit; no ARM decoder exists. */
#define RUNTIME_NATIVE 1
#include "../../vitis/runtime/src/main.c"
#include <assert.h>
#include <stdio.h>

static uint16_t metadata[15] = {2, 128, 512, 32};
static uint16_t staged[8];
static unsigned edge_count;
static unsigned decode_calls;
static unsigned mailbox_calls;
static int forced_status;
static uint8_t forced_opcode;
static uint16_t syndrome_words[8];
static uint8_t reply[521];
static size_t reply_length;

/* Injected mailbox test device: never presented as PL execution evidence. */
static int mailbox(void *user, uint8_t op, uint8_t index, uint16_t data,
                   uint16_t *value)
{
    (void)user;
    mailbox_calls++;
    if (forced_status && (!forced_opcode || op == forced_opcode)) {
        return forced_status;
    }
    switch (op) {
    case 1:
        assert(index < 8);
        staged[index] = data;
        break;
    case 2:
        memcpy(metadata + 4, staged, 3 * sizeof(uint16_t));
        metadata[7] = 0;
        edge_count = 0;
        break;
    case 3:
        assert(staged[3] == edge_count++);
        break;
    case 4:
        assert(edge_count == metadata[5]);
        metadata[7] = 1;
        metadata[8]++;
        break;
    case 5:
        assert(index < 8);
        syndrome_words[index] = data;
        break;
    case 6:
        decode_calls++;
        metadata[10] = 0x1234;
        metadata[11] = 0x8000;
        metadata[12] = 99;
        break;
    case 7:
        assert(index < 15);
        *value = metadata[index];
        break;
    case 8:
        break;
    default:
        assert(0);
    }
    return 0;
}

static void emit(void *user, const uint8_t *data, size_t length)
{
    (void)user;
    assert(length <= sizeof(reply));
    memcpy(reply, data, length);
    reply_length = length;
}

static void request(runtime_parser *parser, uint8_t op, const uint8_t *payload,
                    uint16_t length)
{
    uint8_t frame[521] = {0xd4, 17, op, length & 255, length >> 8};
    if (length) {
        memcpy(frame + 5, payload, length);
    }
    uint32_t crc = runtime_crc32(frame, length + 5);
    for (unsigned i = 0; i < 4; ++i) {
        frame[length + 5 + i] = (uint8_t)(crc >> (8 * i));
    }
    reply_length = 0;
    for (size_t i = 0; i < (size_t)length + 9; ++i) {
        runtime_feed(parser, frame[i], i);
    }
    assert(reply_length >= 9);
    assert(reply[0] == 0x4d && reply[1] == 17);
    assert(runtime_crc32(reply, reply_length - 4) ==
           ((uint32_t)reply[reply_length - 4] |
            (uint32_t)reply[reply_length - 3] << 8 |
            (uint32_t)reply[reply_length - 2] << 16 |
            (uint32_t)reply[reply_length - 1] << 24));
}

static uint32_t gpio_control;
static uint32_t gpio_now;
static uint32_t gpio_error;
static int gpio_stall;

static void gpio_write(void *user, uint32_t value)
{
    (void)user;
    gpio_control = value;
}

static uint32_t gpio_read(void *user)
{
    (void)user;
    if (gpio_stall) {
        return (gpio_control ^ 0x80000000u) & 0x80000000u;
    }
    return (gpio_control & 0x80000000u) | gpio_error | 0x4567u;
}

static uint32_t gpio_clock(void *user)
{
    (void)user;
    return gpio_now++;
}

static void test_gpio_adapter(void)
{
    runtime_gpio gpio;
    runtime_gpio_init(&gpio, gpio_write, gpio_read, gpio_clock, NULL, 10);
    uint16_t result = 0;
    assert(runtime_gpio_mailbox(&gpio, 7, 14, 0, &result) == 0);
    assert(result == 0x4567);
    assert((gpio_control & 0x0fffffffu) == 0x070e0000u);
    gpio_error = 0x20000000u;
    assert(runtime_gpio_mailbox(&gpio, 2, 0, 0, &result) == 1);
    gpio_error = 0x60000000u;
    assert(runtime_gpio_mailbox(&gpio, 6, 0, 0, &result) == 3);
    gpio_error = 0;
    gpio_stall = 1;
    assert(runtime_gpio_mailbox(&gpio, 6, 0, 0, &result) == 4);
    gpio_stall = 0;
    assert(runtime_gpio_mailbox(&gpio, 8, 0, 0, &result) == 0);
    /* Out-of-range indexes must not be truncated onto valid mailbox words. */
    assert(runtime_gpio_mailbox(&gpio, 7, 15, 0, &result) == 1);
    assert(runtime_gpio_mailbox(&gpio, 1, 8, 0, &result) == 1);
}

static void test_parser_recovery(void)
{
    runtime_parser parser;
    runtime_init(&parser, mailbox, emit, NULL, 100);
    unsigned calls = mailbox_calls;
    /* Bad CRC with a nonempty payload must not execute anything. */
    const uint8_t corrupt[] = {0xd4, 17, 6, 0, 0, 0, 0, 0, 0};
    for (size_t i = 0; i < sizeof(corrupt); ++i) {
        runtime_feed(&parser, corrupt[i], (uint32_t)i);
    }
    assert(reply[2] == 1 && mailbox_calls == calls);
    request(&parser, 1, NULL, 0);
    assert(reply[2] == 0);
    const uint8_t oversize[] = {0xd4, 17, 3, 1, 2};
    for (size_t i = 0; i < sizeof(oversize); ++i) {
        runtime_feed(&parser, oversize[i], (uint32_t)i);
    }
    assert(reply[2] == 1);
    request(&parser, 1, NULL, 0);
    assert(reply[2] == 0);
    /* Explicit deadline drops a truncated header/payload, then next valid works. */
    const uint8_t partial[] = {0xd4, 17, 3, 10, 0, 1, 2};
    for (size_t i = 0; i < sizeof(partial); ++i) {
        runtime_feed(&parser, partial[i], (uint32_t)i);
    }
    runtime_tick(&parser, 200);
    assert(reply[2] == 4 && parser.used == 0);
    request(&parser, 1, NULL, 0);
    assert(reply[2] == 0);
    for (unsigned length = 1; length <= 8; ++length) {
        runtime_feed(&parser, 0xd4, 0);
        for (unsigned i = 1; i < length; ++i) {
            runtime_feed(&parser, 0, i);
        }
        runtime_tick(&parser, 200);
        request(&parser, 1, NULL, 0);
        assert(reply[2] == 0);
    }
    request(&parser, 99, NULL, 0);
    assert(reply[2] == 1);
    request(&parser, 1, NULL, 0);
    assert(reply[2] == 0);
    forced_status = 1; /* busy/configuration rejection is acknowledged. */
    uint8_t dimensions[] = {9, 0, 1, 0, 32, 0};
    request(&parser, 2, dimensions, sizeof(dimensions));
    assert(reply[2] == 1);
    forced_status = 4;
    request(&parser, 6, NULL, 0);
    assert(reply[2] == 4);
    forced_status = 0;
    request(&parser, 1, NULL, 0);
    assert(reply[2] == 0);
    metadata[7] = 0;
    uint8_t syndrome[] = {1, 0};
    request(&parser, 5, syndrome, sizeof(syndrome));
    assert(reply[2] == 2);
    metadata[4] = 9;
    metadata[7] = 1;
    syndrome[1] = 2; /* Upper inactive detector bit. */
    unsigned decodes = decode_calls;
    request(&parser, 5, syndrome, sizeof(syndrome));
    assert(reply[2] == 1 && decode_calls == decodes);
    request(&parser, 5, syndrome, 1);
    assert(reply[2] == 1 && decode_calls == decodes);
    metadata[14] = 1;
    syndrome[1] = 1;
    request(&parser, 5, syndrome, sizeof(syndrome));
    assert(reply[2] == 3 && reply_length == 18 && reply[13] == 1);
    forced_status = 3;
    forced_opcode = 6;
    request(&parser, 5, syndrome, sizeof(syndrome));
    assert(reply[2] == 3 && reply_length == 18 && reply[13] == 1);
    forced_status = 0;
    forced_opcode = 0;
    metadata[14] = 0;
    request(&parser, 6, NULL, 0);
    assert(reply[2] == 0 && metadata[7] == 1);
    uint8_t maximum_payload[512];
    memset(maximum_payload, 0xd4, sizeof(maximum_payload));
    request(&parser, 99, maximum_payload, sizeof(maximum_payload));
    assert(reply[2] == 1);
    request(&parser, 1, NULL, 0);
    assert(reply[2] == 0);

    /* A failed commit leaves the begun graph invalid, never the old graph. */
    request(&parser, 2, dimensions, sizeof(dimensions));
    assert(reply[2] == 0 && metadata[7] == 0);
    forced_status = 1;
    forced_opcode = 4;
    request(&parser, 4, NULL, 0);
    assert(reply[2] == 1);
    forced_status = 0;
    forced_opcode = 0;
    request(&parser, 5, syndrome, sizeof(syndrome));
    assert(reply[2] == 2);
    request(&parser, 1, NULL, 0);
    assert(reply[2] == 0);
}

/* Execute real parser AND adapter across a simulated asynchronous PL reset.
 * Initial ACK=1 makes the outstanding DECODE request toggle=0, the reset value. */
static uint32_t reset_status;
static unsigned reset_mode;
static int reset_decoded;
static uint16_t reset_meta[15];

static void reset_write(void *user, uint32_t control)
{
    (void)user;
    unsigned op = (control >> 24) & 15u;
    unsigned index = (control >> 16) & 255u;
    reset_status = control & 0x80000000u;
    if (op == 6) {
        assert((control & 0x80000000u) == 0);
        reset_decoded = 1;
        if (reset_mode == 0) {
            memset(reset_meta, 0, sizeof(reset_meta));
            reset_status = 0; /* Full PL reset aliases the outstanding ACK. */
            return;
        }
        reset_status |= 0x40000000u;
        reset_meta[12] = 19;
        if (reset_mode == 1) {
            reset_meta[7] = 0;
        }
        if (reset_mode == 2) {
            reset_meta[8]++;
        }
        if (reset_mode == 3) {
            reset_meta[4]++;
        }
        if (reset_mode == 4) {
            reset_meta[5]++;
        }
        if (reset_mode == 5) {
            reset_meta[6]++;
        }
        if (reset_mode == 6) {
            reset_meta[12] = 0;
        }
    }
    if (op == 7) reset_status |= reset_meta[index];
}

static uint32_t reset_read(void *user)
{
    (void)user;
    return reset_status;
}

static void test_reset_during_decode(void)
{
    for (reset_mode = 0; reset_mode <= 7; ++reset_mode) {
        runtime_gpio gpio;
        runtime_parser parser;
        memset(reset_meta, 0, sizeof(reset_meta));
        reset_meta[0] = 2;
        reset_meta[4] = 9;
        reset_meta[5] = 1;
        reset_meta[6] = 32;
        reset_meta[7] = 1;
        reset_meta[8] = 42;
        reset_decoded = 0;
        reset_status = 0x80000000u;
        runtime_gpio_init(&gpio, reset_write, reset_read, gpio_clock, NULL, 10);
        runtime_init(&parser, runtime_gpio_mailbox, emit, &gpio, 100);
        const uint8_t syndrome[] = {1, 0};
        request(&parser, 5, syndrome, sizeof(syndrome));
        assert(reset_decoded);
        if (reset_mode == 7) {
            assert(reply[2] == 0 && reply_length == 18 && reply[9] == 19);
        } else {
            assert(reply[2] != 0 && reply_length == 9);
        }
    }
}

int main(void)
{
    test_reset_during_decode();
    test_gpio_adapter();
    test_parser_recovery();
    decode_calls = 0;
    runtime_parser parser;
    runtime_init(&parser, mailbox, emit, NULL, 100);
    request(&parser, 1, NULL, 0);
    assert(reply_length == 69 && reply[2] == 0 && reply[5] == 2);
    uint8_t dimensions[] = {9, 0, 1, 0, 32, 0};
    request(&parser, 2, dimensions, sizeof(dimensions));
    assert(reply[2] == 0);
    uint8_t edge[] = {0, 0, 0, 0, 9, 0, 0, 0, 0, 128};
    request(&parser, 3, edge, sizeof(edge));
    assert(reply[2] == 0);
    assert(staged[3] == 0 && staged[4] == 0 && staged[5] == 9);
    assert(staged[6] == 0 && staged[7] == 0x8000);
    request(&parser, 4, NULL, 0);
    assert(reply[2] == 0 && metadata[7] && metadata[8] == 1);
    uint8_t syndrome[] = {1, 1};
    request(&parser, 5, syndrome, sizeof(syndrome));
    assert(reply[2] == 0 && reply_length == 18);
    assert(reply[5] == 0x34 && reply[8] == 0x80 && reply[9] == 99);
    assert(decode_calls == 1 && syndrome_words[0] == 0x101);
    assert(runtime_crc32((const uint8_t *)"123456789", 9) == 0xcbf43926u);
    puts("runtime firmware: CRC vector passed");
    return 0;
}
