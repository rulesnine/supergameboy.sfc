#include "ik_sgb_mgba_tap.h"
#include <string.h>
/* Only one active GB session; producer and consumer share emulation thread. */
static IkSgbQueue *g_queue;
static uint64_t g_unattached;
static uint64_t g_overflow;
void ik_sgb_mgba_tap_attach(IkSgbQueue *queue) {
    g_queue = queue;
    g_unattached = 0;
    g_overflow = 0;
}
void ik_sgb_mgba_tap_detach(void) { g_queue = 0; }
uint64_t ik_sgb_mgba_tap_unattached(void) { return g_unattached; }
uint64_t ik_sgb_mgba_tap_overflow(void) { return g_overflow; }
void ikcore_mgba_sgb_packet(const uint8_t *data, uint64_t gb_cycles, uint64_t gb_frame) {
    IkSgbPacket packet;
    if (!g_queue || !data) { ++g_unattached; return; }
    packet.gb_cycles = gb_cycles;
    packet.gb_frame = gb_frame;
    memcpy(packet.bytes, data, IK_SGB_PACKET_SIZE);
    if (!ik_sgb_queue_push(g_queue, &packet)) ++g_overflow;
}
