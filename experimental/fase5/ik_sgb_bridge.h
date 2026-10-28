#ifndef IK_SGB_BRIDGE_H
#define IK_SGB_BRIDGE_H
#include <stddef.h>
#include <stdint.h>
#define IK_SGB_PACKET_SIZE 16u
#define IK_SGB_QUEUE_CAPACITY 64u
#define IK_SGB_TRANSFER_SIZE 4096u
typedef struct { uint64_t gb_cycles; uint64_t gb_frame; uint8_t bytes[IK_SGB_PACKET_SIZE]; } IkSgbPacket;
typedef struct { IkSgbPacket entries[IK_SGB_QUEUE_CAPACITY]; size_t head, count; uint64_t accepted, rejected, consumed; uint64_t last_cycles; int has_last_cycles; } IkSgbQueue;
typedef void (*IkSgbPacketConsumer)(const IkSgbPacket *packet, void *context);
void ik_sgb_queue_init(IkSgbQueue *queue);
int ik_sgb_queue_push(IkSgbQueue *queue, const IkSgbPacket *packet);
size_t ik_sgb_queue_consume_until(IkSgbQueue *queue, uint64_t gb_cycles, IkSgbPacketConsumer consume, void *context);
typedef struct { uint64_t gb_cycles; uint8_t command; uint8_t data[IK_SGB_TRANSFER_SIZE]; size_t size; int valid; } IkSgbTransfer;
int ik_sgb_transfer_capture(IkSgbTransfer *snapshot, uint8_t command, const void *bytes, size_t size, uint64_t gb_cycles);
#endif
