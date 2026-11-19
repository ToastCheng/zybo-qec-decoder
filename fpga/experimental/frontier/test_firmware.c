/* Native parser/GPIO checks for the experimental 17-word frontier metadata. */
#define QEC_NATIVE 1
#include "firmware/main.c"
#include <assert.h>
#include <stdio.h>

static uint16_t metadata[17] = {0xd505, 128, 1024, 1, 72, 700, 1, 1, 3, 0, 1, 0, 100, 0, 0, 0xb1c2, 0xd438};
static uint8_t reply[521];
static size_t reply_length;
static int tamper_crc;

static int mailbox(void *user, uint8_t op, uint8_t index, uint16_t data, uint16_t *value)
{
    (void)user;
    (void)data;
    if (op == 7) {
        assert(index < 17);
        *value = metadata[index];
        return 0;
    }
    if (op == 6 && tamper_crc) {
        metadata[15] ^= 1;
    }
    return 0;
}

static void emit(void *user, const uint8_t *data, size_t length)
{
    (void)user;
    memcpy(reply, data, length);
    reply_length = length;
}

static void send_frame(qec_parser *parser, uint8_t seq, uint8_t op, const uint8_t *payload, uint16_t length)
{
    uint8_t frame[521] = {0xd4, seq, op, length & 255, length >> 8};
    if (length) {
        memcpy(frame + 5, payload, length);
    }
    put32(frame + 5 + length, qec_crc32(frame, 5 + length));
    reply_length = 0;
    for (size_t i = 0; i < (size_t)length + 9; ++i) {
        qec_feed(parser, frame[i], i);
    }
    assert(reply_length >= 9 && reply[0] == 0x4d && reply[1] == seq);
}

int main(void)
{
    qec_parser parser;
    qec_init(&parser, mailbox, emit, NULL, 250);
    send_frame(&parser, 1, 1, NULL, 0);
    assert(reply[2] == 0 && reply_length == 77);
    assert(get32(reply + 5) == 0xd505 && get32(reply + 65) == 0xb1c2u && get32(reply + 69) == 0xd438u);
    uint8_t shot[9] = {1};
    send_frame(&parser, 2, 5, shot, sizeof(shot));
    assert(reply[2] == 0 && reply_length == 18);
    tamper_crc = 1;
    send_frame(&parser, 3, 5, shot, sizeof(shot));
    assert(reply[2] == 2);
    printf("PASS native frontier firmware: 17 metadata words, d5 shot, CRC change rejection\n");
    return 0;
}
