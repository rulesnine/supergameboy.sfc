#include "../native_mgba/ikcore_sgb_audio_fifo.h"
#include "../native_mgba/ikcore_sgb_packet_bus.h"
#include "../native_mgba/ikcore_sou_trn_capture.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static unsigned count;
static unsigned kinds[8];
static void receive_sound(const uint8_t* data,unsigned len,void* u) {
    (void)u;
    assert(count<8 && len==16 && data[0]==((8<<3)|1));
    assert(data[1]==0x44 || data[1]==0x66);
    kinds[count++]=1;
}
static void receive_transfer(const uint8_t* data,unsigned len,void* u) {
    (void)u;
    assert(count<8 && len==4096);
    assert(data[0]==0xAA && data[4095]==0x55);
    kinds[count++]=2;
}
int main(void) {
    ikcore_sgb_bus_reset();ikcore_sgb_audio_reset();
    uint8_t cmd[16]={0};cmd[0]=(8<<3)|1;cmd[1]=0x44;
    ikcore_sgb_packet_hook(8,cmd,16);
    uint8_t transfer[4096]={0};transfer[0]=0xAA;transfer[4095]=0x55;
    ikcore_sgb_transfer_completed_hook(transfer,4096);
    cmd[1]=0x66;
    ikcore_sgb_packet_hook(8,cmd,16);
    assert(ikcore_sgb_audio_count()==3);
    assert(!ikcore_sgb_audio_drain(NULL,receive_transfer,NULL));
    assert(ikcore_sgb_audio_count()==3);
    assert(ikcore_sgb_audio_drain(receive_sound,receive_transfer,NULL)==3);
    assert(count==3&&kinds[0]==1&&kinds[1]==2&&kinds[2]==1);
    assert(!ikcore_sgb_audio_count()&&!ikcore_sgb_audio_dropped());
    /* Backpressure: bounded memory and explicit overflow counter. */
    ikcore_sgb_audio_reset();
    for(int i=0;i<IKCORE_SGB_AUDIO_CAPACITY;++i)
      assert(ikcore_sgb_audio_queue_sound(cmd,16));
    assert(!ikcore_sgb_audio_queue_transfer(transfer,4096));
    assert(ikcore_sgb_audio_dropped()==1);
    ikcore_sgb_audio_reset();
    /* Incorrect SOUND packet header, incomplete transfer never dispatched. */
    cmd[0]=1;
    assert(!ikcore_sgb_audio_queue_sound(cmd,16));
    assert(!ikcore_sgb_audio_queue_transfer(transfer,4095));
    assert(ikcore_sgb_audio_count()==0&&ikcore_sgb_audio_dropped()==2);
    puts("IKSGB_SPC_FIFO_OK SOUND-SOU_TRN-SOUND order=1,2,1 exact4096, queue16, overflow/reject safe");
    return 0;
}
