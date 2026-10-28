#include "ik_sgb_joyp.h"
#include <string.h>
static void start(IkSgbJoyp *d) {
    memset(d->bytes, 0, sizeof(d->bytes));
    d->bit_count = 0;
    d->phase = 1;
}
void ik_sgb_joyp_init(IkSgbJoyp *d, IkSgbQueue *q) {
    if (!d) return;
    memset(d, 0, sizeof(*d));
    d->queue = q;
    d->prev_lines = 0x30; /* idle: both high */
}
void ik_sgb_joyp_write(IkSgbJoyp *d, uint8_t joyp, uint64_t cycles, uint64_t frame) {
    uint8_t lines;
    IkSgbPacket packet;
    if (!d) return;
    lines = joyp & 0x30;
    if (cycles < d->last_cycle) {
        if (d->phase) d->aborted++;
        d->phase = 0;
    }
    d->last_cycle = cycles;
    if (lines == d->prev_lines) return; /* ignore redundant writes */
    d->prev_lines = lines;
    if (lines == 0x00) {
        if (d->phase) d->aborted++;
        start(d);
        return;
    }
    if (!d->phase) return;
    if (lines == 0x30) {
        if (d->phase == 1) d->phase = 2;
        else if (d->phase == 2) d->phase = 1;
        else if (d->phase == 3) d->phase = 2;
        return;
    }
    if (d->phase != 2) return;
    if (d->bit_count == 128) {
        if (lines != 0x20) d->bad_stop++;
        else if ((d->bytes[0] & 7u) == 0) d->invalid_header++;
        else {
            packet.gb_cycles = cycles;
            packet.gb_frame = frame;
            memcpy(packet.bytes, d->bytes, sizeof(packet.bytes));
            if (!ik_sgb_queue_push(d->queue, &packet)) d->enqueue_failed++;
            else d->complete++;
        }
        d->phase = 0;
        return;
    }
    if (lines != 0x10 && lines != 0x20) return;
    if (lines == 0x10)
        d->bytes[d->bit_count >> 3] |= (uint8_t)(1u << (d->bit_count & 7u));
    d->bit_count++;
    d->phase = 3; /* force HIGH edge before another bit */
}
