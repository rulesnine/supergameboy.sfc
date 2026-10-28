#ifndef IK_SGB_JOYP_H
#define IK_SGB_JOYP_H
#include "ik_sgb_bridge.h"
#include <stdint.h>
typedef struct {
    IkSgbQueue *queue;
    uint8_t bytes[IK_SGB_PACKET_SIZE];
    unsigned bit_count;
    uint8_t phase; /* 0 idle, 1 awaiting HIGH, 2 awaiting data, 3 stop */
    uint8_t prev_lines;
    uint64_t last_cycle;
    uint64_t complete, bad_stop, aborted, invalid_header, enqueue_failed;
} IkSgbJoyp;
void ik_sgb_joyp_init(IkSgbJoyp *d, IkSgbQueue *q);
/* Call for every GB FF00 write, with original P14/P15 bits, before joypad normalization.
   gb_cycles is a monotonic source-clock timestamp; gb_frame is for diagnostics.
   One packet is emitted only after 128 bits followed by a ZERO stop pulse. */
void ik_sgb_joyp_write(IkSgbJoyp *d, uint8_t joyp, uint64_t gb_cycles, uint64_t gb_frame);
#endif
