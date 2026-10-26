#include "../native_mgba/ikcore_sgb_audio_fifo.h"
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cassert>
static unsigned received[8]={},count=0,first=0,last=0;
void S9xSGBPerfSoundCommand(const uint8_t *packet,uint32_t length) {
  assert(length==16&&count<8&&(packet[0]>>3)==8);
  received[count++]=1;
}
void S9xSGBPerfSouTrn(const uint8_t *data_4k) {
  assert(count<8);
  first=data_4k[0];last=data_4k[4095];
  received[count++]=2;
}
extern "C" unsigned ikcore_sgb_spc_dispatch_frame(void);
int main() {
  ikcore_sgb_audio_reset();
  uint8_t sound[16]={0};sound[0]=(8<<3)|1;
  uint8_t sou[4096]={0};sou[0]=0x12;sou[4095]=0x34;
  assert(ikcore_sgb_audio_queue_sound(sound,16));
  assert(ikcore_sgb_audio_queue_transfer(sou,4096));
  assert(ikcore_sgb_audio_queue_sound(sound,16));
  assert(ikcore_sgb_spc_dispatch_frame()==3);
  assert(count==3&&received[0]==1&&received[1]==2&&received[2]==1);
  assert(first==0x12&&last==0x34);
  assert(ikcore_sgb_spc_dispatch_frame()==0);
  puts("IKSPC_SINK_OK C++ Snes9x sound->SOU_TRN->sound dispatch isolated from audio implementation");
  return 0;
}
