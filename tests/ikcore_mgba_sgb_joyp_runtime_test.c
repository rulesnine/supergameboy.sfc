/* Real SGB SOUND command originating from SM83 JOYP writes, not from
 * a manually invoked unit-test helper. Nothing commercial is embedded. */
#include "../native_mgba/ikcore_mgba_gb_host.h"
#include "../native_mgba/ikcore_sgb_packet_bus.h"
#include "../native_mgba/ikcore_sgb_audio_fifo.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned sound_calls, transfer_calls, seen_size;
static uint8_t last_sound[112];
static void sound_sink(const uint8_t *data,unsigned n,void *ctx) {
    (void)ctx;
    if(n>sizeof(last_sound))abort();
    memcpy(last_sound,data,n);
    seen_size=n;++sound_calls;
}
static void transfer_sink(const uint8_t *data,unsigned n,void *ctx) {
    (void)data;(void)n;(void)ctx;++transfer_calls;
}
int main(int argc,char **argv) {
    if(argc!=2)return 1;
    FILE *f=fopen(argv[1],"rb");
    if(!f)return 2;
    fseek(f,0,SEEK_END);
    long n=ftell(f);rewind(f);
    if(n<1||n>65536)return 3;
    uint8_t *buf=malloc((size_t)n);
    if(!buf||fread(buf,1,(size_t)n,f)!=(size_t)n)return 4;
    fclose(f);
    ikcore_sgb_bus_reset();
    ikcore_sgb_audio_reset();
    ikcore_mgba_host *host=ikcore_mgba_open(buf,(size_t)n,1);
    free(buf);
    if(!host){fprintf(stderr,"SGB test core open failed\n");return 5;}
    for(unsigned frame=0;frame<30;++frame) {
        ikcore_mgba_frame out;
        if(!ikcore_mgba_run(host,0,&out))return 6;
        if(ikcore_sgb_audio_count())break;
    }
    unsigned nqueued=ikcore_sgb_audio_count();
    unsigned ngeneral=ikcore_sgb_bus_count();
    unsigned drained=ikcore_sgb_audio_drain(sound_sink,transfer_sink,NULL);
    printf("IKCORE_SGB_COMMAND_TRACE general=%u audioEvents=%u dispatched=%u sound=%u transfer=%u len=%u first=%02x second=%02x last=%02x\n",
        ngeneral,nqueued,drained,sound_calls,transfer_calls,seen_size,
        last_sound[0],last_sound[1],last_sound[4]);
    ikcore_mgba_close(host);
    if(ngeneral!=1||nqueued!=1||drained!=1||sound_calls!=1||transfer_calls!=0||
        seen_size!=16||last_sound[0]!=0x41||last_sound[1]!=0x37||
        last_sound[4]!=0x13||ikcore_sgb_audio_dropped())return 7;
    puts("IKCORE_SGB_JOYP_RUNTIME_OK mGBA_SM83 => SOUND => IkCore_SPC_FIFO exactly once");
    return 0;
}
