#include "../native_mgba/ikcore_sgb_packet_bus.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void push(unsigned cmd,unsigned packs,unsigned id) {
    unsigned char data[IKCORE_SGB_PACKET_BYTES]={0};
    data[0]=(uint8_t)((cmd<<3)|packs);
    data[1]=(uint8_t)id;
    for(unsigned i=16;i<packs*16;i++)data[i]=(uint8_t)(id+i);
    ikcore_sgb_packet_hook(cmd,data,packs*16);
}
int main(void) {
    ikcore_sgb_bus_reset();
    push(IKCORE_SGB_SOUND_CMD,1,0x31);
    push(IKCORE_SGB_SOU_TRN_CMD,1,0x32);
    push(0x0A,7,0x33);
    assert(ikcore_sgb_bus_count()==3&&ikcore_sgb_bus_dropped()==0);
    ikcore_sgb_packet pkt;
    assert(ikcore_sgb_bus_pop(&pkt));
    assert(pkt.command==IKCORE_SGB_SOUND_CMD&&pkt.length==16&&pkt.serial==1&&pkt.data[1]==0x31);
    assert(ikcore_sgb_bus_pop(&pkt));
    assert(pkt.command==IKCORE_SGB_SOU_TRN_CMD&&pkt.length==16&&pkt.serial==2&&pkt.data[1]==0x32);
    assert(ikcore_sgb_bus_pop(&pkt));
    assert(pkt.command==0x0A&&pkt.length==112&&pkt.serial==3&&pkt.data[1]==0x33);
    assert(pkt.data[111]==(uint8_t)(0x33+111));
    assert(!ikcore_sgb_bus_pop(&pkt));
    // Incorrect multipart and command header must be rejected, not executed.
    unsigned char bad[16]={0};
    bad[0]=(8<<3)|2;
    ikcore_sgb_packet_hook(8,bad,16);
    assert(ikcore_sgb_bus_dropped()==1&&ikcore_sgb_bus_count()==0);
    ikcore_sgb_bus_reset();
    for(unsigned i=0;i<IKCORE_SGB_PACKET_DEPTH;i++) push(8,1,i);
    assert(ikcore_sgb_bus_count()==IKCORE_SGB_PACKET_DEPTH);
    push(8,1,0xFF);
    assert(ikcore_sgb_bus_dropped()==1);
    unsigned previous=0;
    for(unsigned i=0;i<IKCORE_SGB_PACKET_DEPTH;i++) {
      assert(ikcore_sgb_bus_pop(&pkt));
      assert(pkt.serial>previous);
      previous=(unsigned)pkt.serial;
      assert(pkt.data[1]==(uint8_t)i);
    }
    assert(ikcore_sgb_bus_count()==0);
    puts("IKSGB_BUS_OK order=stable sound=8 sou_trn=9 length16_112=ok overflow=rejected");
    return 0;
}
