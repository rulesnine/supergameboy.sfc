#include "ik_sgb_spc_route.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
typedef struct { unsigned sounds, transfers; uint8_t last[16]; uint64_t cycle; } Trace;
static int send_sound(const uint8_t *b, uint64_t t, void *ctx) {
    Trace *v=ctx; ++v->sounds; memcpy(v->last,b,16); v->cycle=t; return 1;
}
static int send_transfer(const uint8_t *b, uint64_t t, void *ctx) {
    Trace *v=ctx; ++v->transfers; assert(b[0]==0xAB && b[4095]==0xCD); v->cycle=t; return 1;
}
int main(void){
  IkSgbSpcRoute r;
  IkSgbPacket p={0};
  IkSgbTransfer tr={0};
  Trace t={0};
  ik_sgb_spc_route_init(&r,send_sound,send_transfer,&t);
  p.bytes[0]=0x41; p.bytes[1]=7; p.bytes[2]=9; p.bytes[3]=3; p.bytes[4]=4; p.gb_cycles=100;
  ik_sgb_spc_route_packet(&r,&p);
  assert(t.sounds==1 && r.sound_delivered==1 && r.sound_packets==1);
  assert(t.last[0]==0x41 && t.last[1]==7 && t.last[4]==4 && t.cycle==100);
  p.bytes[0]=0x49; p.gb_cycles=120;
  ik_sgb_spc_route_packet(&r,&p);
  assert(r.transfer_pending && r.transfer_requested==1 && t.transfers==0);
  tr.command=0x09; tr.valid=1; tr.size=4096; tr.gb_cycles=150;
  tr.data[0]=0xAB; tr.data[4095]=0xCD;
  assert(ik_sgb_spc_route_transfer(&r,&tr)==1);
  assert(t.transfers==1 && r.transfer_delivered==1 && !r.transfer_pending);
  assert(ik_sgb_spc_route_transfer(&r,&tr)==0);
  p.bytes[0]=0x01;ik_sgb_spc_route_packet(&r,&p);
  assert(r.other_packets==1);
  p.bytes[0]=0x40;ik_sgb_spc_route_packet(&r,&p);
  assert(r.invalid_packets==1);
  ik_sgb_spc_route_init(&r,0,0,0);
  p.bytes[0]=0x41;ik_sgb_spc_route_packet(&r,&p);
  assert(r.sound_no_backend==1 && r.sound_delivered==0);
  p.bytes[0]=0x49;ik_sgb_spc_route_packet(&r,&p);
  assert(!ik_sgb_spc_route_transfer(&r,&tr) && r.transfer_no_backend==1);
  puts("PASS: SOUND distinct from SOU_TRN; exact packet routing; 4KiB data gated; no backend no audio");
  return 0;
}
