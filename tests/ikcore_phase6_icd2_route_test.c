/* Phase6 C ABI invariants before linking actual Snes9x ICD2 implementation.
 * Test ONLY the mGBA SGB producer->router interface. Real BIOS $6002 and
 * $7000 semantics are delegated to Snes9x and validated at ARM ELF link.
 */
#include "../native_mgba/ikcore_sgb_packet_bus.h"
#include "../native_mgba/ikcore_sgb_audio_fifo.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
static int route_mode=0;  /* 0 absent BIOS; 1 accepted; -1 backpressure */
static unsigned calls,received,not_gb_commands;
static uint8_t packet[112];
int ikcore_mgba_phase6_route_icd2_packet(const uint8_t* data,unsigned len) {
    ++calls;
    if(!route_mode) return 0;
    if(route_mode<0) return -1;
    assert(len>=16 && len<=112 && (len%16)==0);
    memcpy(packet,data,len);
    received=len;
    return 1;
}
int ikcore_mgba_phase6_icd2_active(void){return route_mode!=0;}
int main(void) {
    ikcore_sgb_bus_reset();
    ikcore_sgb_audio_reset();
    uint8_t sound[16]={0};
    sound[0]=(8<<3)|1; sound[1]=0xB2;
    ikcore_sgb_packet_hook(8,sound,16);
    assert(calls==1 && ikcore_sgb_audio_count()==1);
    assert(ikcore_sgb_bus_count()==1);
    ikcore_sgb_bus_reset();ikcore_sgb_audio_reset();
    route_mode=1;
    ikcore_sgb_packet_hook(8,sound,16);
    assert(calls==2 && received==16 && packet[1]==0xB2);
    assert(ikcore_sgb_audio_count()==0);
    uint8_t multi[32]={0};
    multi[0]=(0x13<<3)|2;
    multi[16]=multi[0];
    for(int i=1;i<32;++i)if(i!=16)multi[i]=(uint8_t)i;
    ikcore_sgb_packet_hook(0x13,multi,32);
    assert(calls==3 && received==32 && packet[31]==31);
    assert(ikcore_sgb_audio_count()==0);
    route_mode=-1;
    unsigned n=ikcore_sgb_bus_dropped();
    ikcore_sgb_packet_hook(8,sound,16);
    assert(calls==4 && ikcore_sgb_bus_dropped()==n+1);
    assert(ikcore_sgb_audio_count()==0);
    route_mode=1;
    uint8_t transfer[4096]={0};
    ikcore_sgb_transfer_completed_hook(transfer,4096);
    assert(ikcore_sgb_audio_count()==0);
    route_mode=0;
    ikcore_sgb_transfer_completed_hook(transfer,4096);
    assert(ikcore_sgb_audio_count()==1);
    printf("IKCORE_PHASE6_ICD2_ROUTER_OK calls=%u last=%u legacySound=1 biosSound=0 badRouteNotDuplicated=1 multipart=2 souNoDuplicate=1\n",
           calls,received);
    (void)not_gb_commands;
    return 0;
}
