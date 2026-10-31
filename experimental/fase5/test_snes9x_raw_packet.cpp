/* Host test against pinned SuperSnes9x sgb_packet.cpp; no commercial content. */
#include "sgb_packet.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
using namespace SGB;
static uint8_t last[112];
static unsigned calls, last_command, last_length;
static void on_command(uint8_t cmd, const uint8_t *p, uint32_t size) {
    assert(size <= sizeof last);
    ++calls;
    last_command = cmd;
    last_length = size;
    memcpy(last, p, size);
}
static void deliver(PacketState &ps, const uint8_t bytes[16]) {
    PacketFeed(ps, 0);
    PacketFeed(ps, 0x30);
    for (int i=0;i<128;++i) {
        PacketFeed(ps, (bytes[i>>3] & (1u << (i&7))) ? 0x10 : 0x20);
        PacketFeed(ps, 0x30);
    }
}
int main() {
    PacketState ps;
    uint8_t one[16]={0x41,0x12,0x34}; /* SOUND command, 1 packet */
    uint8_t a[16]={0x9A,0x21}, b[16]={0xAB,0xCD}; /* CHR_TRN, 2 packets */
    PacketReset(ps);
    SetSgbCommandCallback(on_command);
    deliver(ps,one);
    assert(calls==1 && last_command==8 && last_length==16);
    assert(!memcmp(last,one,16));
    deliver(ps,a);
    assert(calls==1);
    deliver(ps,b);
    assert(calls==2 && last_command==19 && last_length==32);
    assert(!memcmp(last,a,16) && !memcmp(last+16,b,16));
    puts("PASS: injecting mGBA packet bytes through Snes9x SGB decoder (single + chained)");
}
