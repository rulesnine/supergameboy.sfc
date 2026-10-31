#include "ik_sgb_mgba_relay.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    uint8_t row[160], payload[IK_SGB_TRANSFER_SIZE];
    uint64_t frame=0;
    unsigned y,x;
    ikcore_fase5_sgb_reset_packets();
    for(x=0;x<160;x++) row[x]=(uint8_t)(x&3);
    for(y=0;y<128;y++) ikcore_mgba_sou_trn_scanline(y,row);
    ikcore_mgba_sou_trn_complete(22);
    assert(ikcore_fase6_sou_trn_pop(payload,sizeof(payload),&frame)==1);
    assert(frame==22);
    assert(payload[0]==0x55 && payload[1]==0x33);
    assert(payload[320]==0x55 && payload[321]==0x33);
    assert(ikcore_fase6_sou_trn_pop(payload,sizeof(payload),&frame)==0);
    assert(ikcore_fase6_sou_trn_dropped()==0);
    ikcore_fase5_sgb_reset_packets();
    assert(ikcore_fase6_sou_trn_pop(payload,sizeof(payload),&frame)==0);
    puts("PASS: real SOU_TRN SGB LCD 2bpp packing, 4KiB snapshot, and reset");
    return 0;
}
