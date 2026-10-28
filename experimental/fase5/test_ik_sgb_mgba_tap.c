#include "ik_sgb_mgba_tap.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
int main(void) {
    IkSgbQueue q;
    uint8_t p[16] = {0x09,0x42,0x87};
    ik_sgb_queue_init(&q);
    ik_sgb_mgba_tap_attach(&q);
    ikcore_mgba_sgb_packet(p, 300, 2);
    p[1]=0x55;
    assert(q.count==1 && q.entries[0].bytes[1]==0x42);
    assert(q.entries[0].gb_cycles==300 && q.entries[0].gb_frame==2);
    ikcore_mgba_sgb_packet(p,299,2);
    assert(ik_sgb_mgba_tap_overflow()==1 && q.rejected==1);
    ik_sgb_mgba_tap_detach();
    ikcore_mgba_sgb_packet(p, 301, 2);
    assert(ik_sgb_mgba_tap_unattached()==1 && q.count==1);
    puts("PASS: mGBA callback, copy, ordering error, detach");
    return 0;
}
