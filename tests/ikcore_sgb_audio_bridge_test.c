#include "../native_mgba/ikcore_sgb_audio_bridge.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
static uint8_t wanted[4096], got[4096], got_sound[112];
static unsigned got_length, called_sound, called_transfer, order[4], order_count;
static void sound(const uint8_t *packet,unsigned length,void *opaque) {
    (void)opaque;
    assert(length==16 && called_sound==0);
    memcpy(got_sound,packet,length);
    got_length=length; called_sound++;
    order[order_count++]=8;
}
static void transfer(const uint8_t *data,void *opaque) {
    (void)opaque;
    memcpy(got,data,sizeof(got));
    called_transfer++;
    order[order_count++]=9;
}
static void emit_packet(unsigned command) {
    uint8_t packet[16]={0};
    packet[0]=(uint8_t)((command<<3)|1);
    packet[1]=0x11;packet[2]=0x22;packet[3]=0x33;packet[4]=0x44;
    ikcore_sgb_sound_packet_hook(command,packet,sizeof(packet));
}
static void paint_row(unsigned y,uint16_t *row) {
    memset(row,0,160*sizeof(*row));
    for (unsigned x=0;x<160;x+=8) {
        unsigned o=2*((y&7)+(y>>3)*160)+(x<<1);
        if(o+1>=4096)break;
        uint8_t lo=wanted[o],hi=wanted[o+1];
        for (unsigned p=0;p<8;++p)
            row[x+p]=(uint8_t)(((lo>>(7-p))&1)|(((hi>>(7-p))&1)<<1));
    }
}
int main(void) {
    ikcore_sgb_audio_sink sink={sound,transfer,NULL};
    ikcore_sgb_audio_reset();
    for(unsigned i=0;i<4096;++i)wanted[i]=(uint8_t)((i*41u+73u)&0xFF);
    /* Real SNES transfer has [count,destination,data] plus [0,jump]. */
    wanted[0]=3; wanted[1]=0; wanted[2]=0x10; wanted[3]=0;
    wanted[4]=0x11;wanted[5]=0x22;wanted[6]=0x33;
    wanted[7]=0;wanted[8]=0;wanted[9]=0x34;wanted[10]=0x12;
    emit_packet(9);
    emit_packet(8);
    assert(ikcore_sgb_audio_queued()==2);
    assert(!ikcore_sgb_audio_dispatch_one(&sink));
    uint16_t row[160];
    paint_row(1,row);
    ikcore_sgb_lcd_row_hook(1,row,160); /* not start until y=0 */
    assert(ikcore_sgb_audio_completed_transfers()==0);
    for(unsigned y=0;y<103;++y) {
        paint_row(y,row);
        ikcore_sgb_lcd_row_hook(y,row,160);
    }
    assert(ikcore_sgb_audio_completed_transfers()==0);
    assert(!ikcore_sgb_audio_dispatch_one(&sink));
    paint_row(103,row);ikcore_sgb_lcd_row_hook(103,row,160);
    assert(ikcore_sgb_audio_completed_transfers()==1);
    assert(ikcore_sgb_audio_dispatch_one(&sink)); /* SOU comes first */
    assert(ikcore_sgb_audio_dispatch_one(&sink)); /* SOUND follows */
    assert(order_count==2&&order[0]==9&&order[1]==8);
    assert(called_transfer==1&&called_sound==1&&got_length==16);
    assert(got_sound[1]==0x11&&got_sound[4]==0x44);
    assert(memcmp(got,wanted,4096)==0);
    assert(ikcore_sgb_audio_queued()==0);
    assert(!ikcore_sgb_audio_dispatch_one(&sink));
    /* Reject invalid packet and preserve event queue. */
    uint8_t bad[16]={0};
    bad[0]=(9<<3)|2;
    ikcore_sgb_sound_packet_hook(9,bad,16);
    assert(ikcore_sgb_audio_dropped()==1&&ikcore_sgb_audio_queued()==0);
    /* Full queue must reject without overwriting earlier commands. */
    ikcore_sgb_audio_reset();
    for(unsigned i=0;i<IKCORE_SGB_AUDIO_EVENTS;++i)emit_packet(8);
    emit_packet(8);
    assert(ikcore_sgb_audio_dropped()==1);
    assert(ikcore_sgb_audio_queued()==IKCORE_SGB_AUDIO_EVENTS);
    puts("IKSGB_AUDIO_BRIDGE_OK SOU_TRN_4096=exact SOUND_order=preserved LCD_2bpp=exact overflow=rejected");
}
