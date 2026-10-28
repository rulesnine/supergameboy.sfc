#include "ik_sgb_bridge.h"
#include <string.h>
void ik_sgb_queue_init(IkSgbQueue *queue) { if (queue) memset(queue, 0, sizeof(*queue)); }
int ik_sgb_queue_push(IkSgbQueue *queue, const IkSgbPacket *packet) {
    size_t tail;
    if (!queue || !packet) return 0;
    if (queue->count == IK_SGB_QUEUE_CAPACITY || (queue->has_last_cycles && packet->gb_cycles < queue->last_cycles)) { queue->rejected++; return 0; }
    tail = (queue->head + queue->count) % IK_SGB_QUEUE_CAPACITY;
    queue->entries[tail] = *packet;
    queue->count++; queue->accepted++; queue->last_cycles = packet->gb_cycles; queue->has_last_cycles = 1;
    return 1;
}
size_t ik_sgb_queue_consume_until(IkSgbQueue *queue, uint64_t gb_cycles, IkSgbPacketConsumer consume, void *context) {
    size_t n = 0;
    if (!queue || !consume) return 0;
    while (queue->count && queue->entries[queue->head].gb_cycles <= gb_cycles) {
        consume(&queue->entries[queue->head], context);
        queue->head = (queue->head + 1) % IK_SGB_QUEUE_CAPACITY;
        queue->count--; queue->consumed++; n++;
    }
    return n;
}
int ik_sgb_transfer_capture(IkSgbTransfer *snapshot, uint8_t command, const void *bytes, size_t size, uint64_t gb_cycles) {
    if (!snapshot || !bytes || size != IK_SGB_TRANSFER_SIZE) return 0;
    memcpy(snapshot->data, bytes, size); snapshot->command = command;
    snapshot->size = size; snapshot->gb_cycles = gb_cycles; snapshot->valid = 1;
    return 1;
}
