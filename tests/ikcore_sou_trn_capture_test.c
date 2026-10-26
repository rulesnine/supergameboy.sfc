#include "../native_mgba/ikcore_sou_trn_capture.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static unsigned got_count,got_len;
static uint8_t last_data[IKCORE_SOU_BYTES];
static void capture_sink(const uint8_t* data,unsigned len,void*ctx) {
    (void)ctx;
    ++got_count;got_len=len;
    memcpy(last_data,data,len);
}
static void frame(ikcore_sou_capture* c,bool populate) {
    uint16_t row[160];
    for(int y=0;y<144;y++) {
        for(int x=0;x<160;x++)
            row[x]=(uint16_t)(x&3u);
        if(populate)ikcore_sou_capture_scanline(c,y,row,160);
    }
    (void)ikcore_sou_capture_end_frame(c,capture_sink,NULL);
}
int main(void) {
    ikcore_sou_capture c;
    ikcore_sou_capture_reset(&c);
    assert(c.completed==0&&!c.recording&&!c.pending);
    ikcore_sou_capture_arm(&c);
    for(int i=0;i<IKCORE_SOU_SKIP_FRAMES;i++) {
        frame(&c,true);
        assert(!c.completed&&!got_count);
    }
    assert(c.recording && c.frames_to_skip==0);
    frame(&c,true);
    assert(c.completed==1&&!c.incomplete&&!c.pending&&!c.recording);
    assert(got_count==1&&got_len==IKCORE_SOU_BYTES);
    assert(last_data[0]==0x55&&last_data[1]==0x33);
    assert(last_data[304]==0x55&&last_data[305]==0x33);
    assert(last_data[320]==0x55&&last_data[321]==0x33);
    assert(last_data[4094]==0x55&&last_data[4095]==0x33);
    assert(!ikcore_sou_capture_end_frame(&c,capture_sink,NULL));
    assert(got_count==1);
    /* Incomplete LCD/black screen transfer must not start garbage SPC code. */
    ikcore_sou_capture_arm(&c);
    for(int i=0;i<IKCORE_SOU_SKIP_FRAMES;i++)frame(&c,false);
    frame(&c,false);
    assert(c.incomplete==1&&c.completed==1&&got_count==1);
    /* Repeated SOU_TRN preempts the pending first capture; no ghost upload. */
    ikcore_sou_capture_arm(&c);
    frame(&c,false);
    ikcore_sou_capture_arm(&c);
    assert(c.interrupted==1);
    for(int i=0;i<IKCORE_SOU_SKIP_FRAMES;i++)frame(&c,false);
    frame(&c,true);
    assert(c.completed==2&&got_count==2&&c.incomplete==1);
    ikcore_sou_capture_reset(&c);
    assert(!c.pending&&!c.recording&&c.completed==0&&c.incomplete==0);
    puts("IKSOU_CAPTURE_OK 4096bytes tile-planar delay6-frame 2bit=0x55/0x33 incomplete-blocked restart-atomic");
    return 0;
}
