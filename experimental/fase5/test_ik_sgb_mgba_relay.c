#include "ik_sgb_mgba_relay.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    IkSgbPacket p;
    uint8_t a[16]={0x41,0x23,0x54};
    uint8_t b[16]={0x49,0xAB,0xCD};
    uint64_t n=0,s=0,t=0,c=0,q=0,lost=0,sfx=0,sou=0;
    ikcore_fase5_sgb_reset_packets();
    ikcore_mgba_sgb_packet(a,100,5);
    ikcore_mgba_sgb_packet(b,200,6);
    a[1]=0; b[1]=0; /* copy must be independent of mGBA's reused buffer */
    ikcore_fase5_stats(&n,&s,&t,&c);
    assert(n==2 && s==2 && t==1 && c==200);
    ikcore_fase5_sgb_relay_stats(&q,&lost,&sfx,&sou);
    assert(q==2 && lost==0 && sfx==1 && sou==1);
    assert(ikcore_fase5_sgb_pop_packet(&p)==1);
    assert(p.bytes[0]==0x41 && p.bytes[1]==0x23 && p.gb_cycles==100 && p.gb_frame==5);
    assert(ikcore_fase5_sgb_pop_packet(&p)==1);
    assert(p.bytes[0]==0x49 && p.bytes[1]==0xAB && p.gb_cycles==200 && p.gb_frame==6);
    assert(ikcore_fase5_sgb_pop_packet(&p)==0);
    ikcore_fase5_sgb_relay_stats(&q,&lost,&sfx,&sou);
    assert(q==0 && lost==0);
    ikcore_fase5_sgb_reset_packets();
    for(int i=0;i<65;i++){
        uint8_t msg[16]={0x41};
        msg[1]=(uint8_t)i;
        ikcore_mgba_sgb_packet(msg,1000+(uint64_t)i,8);
    }
    ikcore_fase5_sgb_relay_stats(&q,&lost,&sfx,&sou);
    assert(q==IK_SGB_QUEUE_CAPACITY && lost==1);
    for(int i=0;i<64;i++){
        assert(ikcore_fase5_sgb_pop_packet(&p)==1 && p.bytes[1]==i);
    }
    assert(ikcore_fase5_sgb_pop_packet(&p)==0);
    ikcore_fase5_sgb_reset_packets();
    ikcore_fase5_stats(&n,&s,&t,&c);
    assert(n==0 && s==0 && t==0 && c==0);
    puts("PASS: mGBA SGB live relay packet order, data copy, counters, overflow, reset");
    return 0;
}
