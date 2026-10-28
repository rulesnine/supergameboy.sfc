#include "ik_sgb_joyp.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static uint64_t tick;
static void write_line(IkSgbJoyp *d, uint8_t v) { ik_sgb_joyp_write(d,v,++tick,0); }
static void send_packet(IkSgbJoyp *d, const uint8_t p[16], int bad_stop) {
    unsigned i;
    write_line(d,0x00); write_line(d,0x30);
    for(i=0;i<128;i++) {
        write_line(d,(p[i>>3] & (1u << (i & 7))) ? 0x10 : 0x20);
        write_line(d,0x30);
    }
    write_line(d,bad_stop ? 0x10 : 0x20);
    write_line(d,0x30);
}
int main(void) {
    IkSgbQueue q;
    IkSgbJoyp d;
    uint8_t p[16] = {0x09,0x52,0xAB,0xCD};
    ik_sgb_queue_init(&q); ik_sgb_joyp_init(&d,&q);
    send_packet(&d,p,0);
    assert(d.complete==1 && q.count==1 && !memcmp(q.entries[0].bytes,p,16));
    send_packet(&d,p,1);
    assert(d.bad_stop==1 && q.count==1);
    p[0]=0x08; send_packet(&d,p,0);
    assert(d.invalid_header==1 && q.count==1);
    p[0]=0x09; send_packet(&d,p,0);
    assert(d.complete==2 && q.count==2);
    puts("PASS: JOYP 128 bits, stop, header, reset and queue");
    return 0;
}
