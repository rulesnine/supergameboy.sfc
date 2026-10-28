#include "ik_sgb_bridge.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void capture(const IkSgbPacket *p, void *ctx) {
    uint64_t *last = ctx;
    assert(p->gb_cycles >= *last);
    *last = p->gb_cycles;
}
int main(void) {
    IkSgbQueue q;
    IkSgbPacket p;
    IkSgbTransfer t = {0};
    uint8_t source[IK_SGB_TRANSFER_SIZE];
    uint64_t last = 0;
    unsigned i;
    memset(&p, 0, sizeof(p)); ik_sgb_queue_init(&q);
    for (i = 0; i < IK_SGB_QUEUE_CAPACITY; i++) {
        p.gb_cycles = i * 2u; p.bytes[0] = (uint8_t)i;
        assert(ik_sgb_queue_push(&q, &p));
    }
    assert(!ik_sgb_queue_push(&q, &p)); assert(q.rejected == 1);
    assert(ik_sgb_queue_consume_until(&q, 62, capture, &last) == 32);
    assert(ik_sgb_queue_consume_until(&q, 9999, capture, &last) == 32);
    assert(q.consumed == IK_SGB_QUEUE_CAPACITY);
    p.gb_cycles = 1; assert(!ik_sgb_queue_push(&q, &p));
    p.gb_cycles = 128; assert(ik_sgb_queue_push(&q, &p));
    assert(ik_sgb_queue_consume_until(&q, 128, capture, &last) == 1);
    for (i = 0; i < IK_SGB_TRANSFER_SIZE; i++) source[i] = (uint8_t)(i ^ (i >> 8));
    assert(!ik_sgb_transfer_capture(&t, 0x13, source, 1024, 200));
    assert(ik_sgb_transfer_capture(&t, 0x13, source, sizeof(source), 200));
    memset(source, 0, sizeof(source));
    for (i = 0; i < IK_SGB_TRANSFER_SIZE; i++) assert(t.data[i] == (uint8_t)(i ^ (i >> 8)));
    assert(t.valid && t.size == 4096 && t.gb_cycles == 200);
    puts("PASS: queue ordering, overflow, delayed consume and 4096-byte snapshot");
    return 0;
}
