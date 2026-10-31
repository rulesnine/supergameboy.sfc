#ifndef IK_SGB_MGBA_RELAY_H
#define IK_SGB_MGBA_RELAY_H
#include "ik_sgb_bridge.h"
#ifdef __cplusplus
extern "C" {
#endif
/* One synchronous emulation thread: producer is the native mGBA JOYP parser.
   The consumer must pop EVERY FRAME so the 64-packet ring never saturates. */
void ikcore_fase5_sgb_reset_packets(void);
void ikcore_mgba_sgb_packet(const uint8_t *data, uint64_t cycles, uint64_t frame);
int ikcore_fase5_sgb_pop_packet(IkSgbPacket *out);
void ikcore_fase5_sgb_relay_stats(uint64_t *queued, uint64_t *lost,
                                  uint64_t *sfx, uint64_t *sample_transfers);
void ikcore_fase5_stats(uint64_t *packets, uint64_t *sounds,
                        uint64_t *trns, uint64_t *cycles);
#ifdef __cplusplus
}
#endif
#endif
