/* Parse D4 requests and emit 4D replies; the PL performs decoding. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>

uint32_t qec_crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xffffffffu;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ ((crc & 1u) ? 0xedb88320u : 0u);
        }
    }
    return crc ^ 0xffffffffu;
}

/* Mailbox callbacks return protocol status, including PL rejection and timeout. */
typedef int (*qec_mailbox_fn)(void *, uint8_t, uint8_t, uint16_t, uint16_t *);
typedef void (*qec_emit_fn)(void *, const uint8_t *, size_t);

/* Wait for an overdue acknowledgement before issuing another toggle. */
typedef struct {
    void (*write_control)(void *, uint32_t);
    uint32_t (*read_status)(void *);
    uint32_t (*now_ms)(void *);
    void *user;
    uint32_t timeout_ms;
    uint32_t toggle;
} qec_gpio;

void qec_gpio_init(qec_gpio *g, void (*write_control)(void *, uint32_t),
                   uint32_t (*read_status)(void *),
                   uint32_t (*now_ms)(void *), void *user, uint32_t timeout_ms)
{
    g->write_control = write_control;
    g->read_status = read_status;
    g->now_ms = now_ms;
    g->user = user;
    g->timeout_ms = timeout_ms;
    g->toggle = read_status(user) & 0x80000000u;
}

static int gpio_wait(qec_gpio *g, uint32_t *status)
{
    uint32_t start = g->now_ms(g->user);
    do {
        *status = g->read_status(g->user);
        if ((*status & 0x80000000u) == g->toggle) {
            return 0;
        }
    } while ((uint32_t)(g->now_ms(g->user) - start) < g->timeout_ms);
    return 4;
}

int qec_gpio_mailbox(void *context, uint8_t op, uint8_t index,
                     uint16_t data, uint16_t *value)
{
    qec_gpio *g = context;
    uint32_t status;
    if (op < 1 || op > 8 || (op == 1 && index >= 8) ||
        (op == 7 && index >= 15) ||
        (op != 1 && op != 5 && op != 7 && index != 0)) {
        return 1;
    }
    if (gpio_wait(g, &status)) {
        return 4;
    }
    g->toggle ^= 0x80000000u;
    g->write_control(g->user, g->toggle | (uint32_t)op << 24 |
                     (uint32_t)index << 16 | data);
    if (gpio_wait(g, &status)) {
        return 4;
    }
    /* A reset can match toggle zero; decoding also requires the completion bit. */
    if (op == 6 && !(status & 0x40000000u)) {
        return 1;
    }
    *value = (uint16_t)status;
    if (status & 0x20000000u) {
        return op == 6 && (status & 0x40000000u) ? 3 : 1;
    }
    return 0;
}

/* Frames carry a five-byte header, up to 512 payload bytes and an IEEE CRC32.
 * Lengths, CRCs and multibyte payload fields are little-endian. */
typedef struct {
    uint8_t frame[521];
    size_t used;
    uint32_t last_ms;
    uint32_t timeout_ms;
    qec_mailbox_fn mailbox;
    qec_emit_fn emit;
    void *user;
} qec_parser;

static uint16_t get16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | (uint16_t)p[1] << 8);
}

static uint32_t get32(const uint8_t *p)
{
    return (uint32_t)get16(p) | (uint32_t)get16(p + 2) << 16;
}

static void put32(uint8_t *p, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) {
        p[i] = (uint8_t)(value >> (8 * i));
    }
}

void qec_init(qec_parser *p, qec_mailbox_fn mailbox,
              qec_emit_fn emit, void *user, uint32_t timeout_ms)
{
    memset(p, 0, sizeof(*p));
    p->mailbox = mailbox;
    p->emit = emit;
    p->user = user;
    p->timeout_ms = timeout_ms;
}

static void respond(qec_parser *p, uint8_t seq, uint8_t status,
                    const uint8_t *payload, uint16_t length)
{
    uint8_t response[521] = {0x4d, seq, status, length & 255, length >> 8};
    if (length) {
        memcpy(response + 5, payload, length);
    }
    put32(response + 5 + length, qec_crc32(response, 5 + length));
    p->emit(p->user, response, 9 + length);
}

static int command(qec_parser *p, uint8_t op, uint8_t index,
                   uint16_t data, uint16_t *value)
{
    return p->mailbox(p->user, op, index, data, value);
}

static int metadata_read(qec_parser *p, uint16_t metadata[15])
{
    for (uint8_t i = 0; i < 15; ++i) {
        int status = command(p, 7, i, 0, metadata + i);
        if (status) {
            return status;
        }
    }
    return 0;
}

static int dispatch(qec_parser *p, uint8_t op, const uint8_t *data,
                    uint16_t length, uint8_t output[60], uint16_t *out_length)
{
    uint16_t metadata[15];
    uint16_t unused = 0;
    int status;
    *out_length = 0;
    switch (op) {
    case 1: /* Read metadata. */
        if (length) {
            return 1;
        }
        status = metadata_read(p, metadata);
        if (status) {
            return status;
        }
        for (unsigned i = 0; i < 15; ++i) {
            uint32_t value = metadata[i];
            /* Expand each 16-bit metadata word into its 32-bit wire field. */
            put32(output + 4 * i, value);
        }
        *out_length = 60;
        return 0;
    case 2: /* Begin a graph load with detector, edge and observable counts. */
        if (length != 6) {
            return 1;
        }
        for (uint8_t i = 0; i < 3; ++i) {
            status = command(p, 1, i, get16(data + 2 * i), &unused);
            if (status) {
                return status;
            }
        }
        return command(p, 2, 0, 0, &unused);
    case 3: /* Append indexed edges with two endpoints and an observable mask. */
        if (!length || length % 10) {
            return 1;
        }
        for (unsigned offset = 0; offset < length; offset += 10) {
            for (uint8_t i = 0; i < 5; ++i) {
                status = command(p, 1, 3 + i,
                                 get16(data + offset + 2 * i), &unused);
                if (status) {
                    return status;
                }
            }
            status = command(p, 3, 0, 0, &unused);
            if (status) {
                return status;
            }
        }
        return 0;
    case 4: /* Commit the graph. */
    case 6: /* Discard the shot while preserving the graph. */
        if (length) {
            return 1;
        }
        return command(p, op == 4 ? 4 : 8, 0, 0, &unused);
    case 5: /* Decode packed detector bits, least-significant bit first. */
        status = metadata_read(p, metadata);
        if (status) {
            return status;
        }
        if (!metadata[7]) {
            return 2;
        }
        if (!metadata[4] || length != (metadata[4] + 7u) / 8u ||
            (metadata[4] % 8u && (data[length - 1] >> (metadata[4] % 8u)))) {
            return 1;
        }
        uint16_t before[15];
        memcpy(before, metadata, sizeof(before));
        for (unsigned i = 0; i < (length + 1u) / 2u; ++i) {
            uint16_t word = data[2 * i];
            if (2 * i + 1 < length) {
                word |= (uint16_t)data[2 * i + 1] << 8;
            }
            status = command(p, 5, (uint8_t)i, word, &unused);
            if (status) {
                return status;
            }
        }
        status = command(p, 6, 0, 0, &unused);
        if (status && status != 3) {
            return status;
        }
        int decode_status = status;
        status = metadata_read(p, metadata);
        if (status) {
            return status;
        }
        /* Require unchanged version, capacities, dimensions, validity and generation.
         * A successful decode must also report a positive cycle count. */
        if (!metadata[7] || memcmp(before, metadata, 10 * sizeof(uint16_t)) ||
            !(metadata[12] | metadata[13])) {
            return 2;
        }
        put32(output, (uint32_t)metadata[10] | (uint32_t)metadata[11] << 16);
        put32(output + 4, (uint32_t)metadata[12] | (uint32_t)metadata[13] << 16);
        output[8] = metadata[14] != 0 || decode_status == 3;
        *out_length = 9;
        return output[8] ? 3 : 0;
    default:
        return 1;
    }
}

void qec_tick(qec_parser *p, uint32_t now_ms)
{
    if (p->used && (uint32_t)(now_ms - p->last_ms) >= p->timeout_ms) {
        if (p->used >= 2) {
            respond(p, p->frame[1], 4, NULL, 0);
        }
        p->used = 0;
    }
}

void qec_feed(qec_parser *p, uint8_t byte, uint32_t now_ms)
{
    qec_tick(p, now_ms);
    if (!p->used && byte != 0xd4) {
        return;
    }
    p->last_ms = now_ms;
    p->frame[p->used++] = byte;
    if (p->used < 5) {
        return;
    }
    uint16_t length = get16(p->frame + 3);
    if (length > 512) {
        respond(p, p->frame[1], 1, NULL, 0);
        p->used = 0;
        return;
    }
    if (p->used == (size_t)length + 9) {
        uint8_t output[60];
        uint16_t out_length = 0;
        int status = 1;
        if (qec_crc32(p->frame, length + 5) == get32(p->frame + length + 5)) {
            status = dispatch(p, p->frame[2], p->frame + 5, length,
                              output, &out_length);
        }
        respond(p, p->frame[1], (uint8_t)status, output, out_length);
        p->used = 0;
    }
}

#ifndef QEC_NATIVE
#ifndef QEC_PLATFORM_HEADER
#error "Define QEC_PLATFORM_HEADER to a quoted board platform header, or QEC_NATIVE for the parser harness"
#endif
#include QEC_PLATFORM_HEADER

#ifndef QEC_FRAME_TIMEOUT_MS
#define QEC_FRAME_TIMEOUT_MS 250u
#endif
#ifndef QEC_MAILBOX_TIMEOUT_MS
#define QEC_MAILBOX_TIMEOUT_MS 1000u
#endif

/* Nonblocking UART reads keep partial-frame deadlines enforceable. */
int main(void)
{
    qec_gpio gpio;
    qec_parser parser;
    qec_platform_init();
    qec_gpio_init(&gpio, qec_platform_write_control,
                  qec_platform_read_status, qec_platform_now_ms,
                  NULL, QEC_MAILBOX_TIMEOUT_MS);
    qec_init(&parser, qec_gpio_mailbox, qec_platform_emit,
             &gpio, QEC_FRAME_TIMEOUT_MS);
    for (;;) {
        int byte = qec_platform_read_byte();
        uint32_t now = qec_platform_now_ms(NULL);
        if (byte >= 0) {
            qec_feed(&parser, (uint8_t)byte, now);
        } else {
            qec_tick(&parser, now);
        }
    }
}
#endif
