#ifndef IK_SGB_MGBA_TAP_H
#define IK_SGB_MGBA_TAP_H
#include "ik_sgb_bridge.h"
/* Single-threaded experimental bridge. Register on emulation thread. */
void ik_sgb_mgba_tap_attach(IkSgbQueue *queue);
void ik_sgb_mgba_tap_detach(void);
void ikcore_mgba_sgb_packet(const uint8_t *data, uint64_t gb_cycles, uint64_t gb_frame);
uint64_t ik_sgb_mgba_tap_unattached(void);
uint64_t ik_sgb_mgba_tap_overflow(void);
#endif
