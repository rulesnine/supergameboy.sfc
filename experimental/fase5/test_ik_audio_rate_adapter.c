#include "ik_audio_rate_adapter.h"
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
static void run(unsigned in_hz,unsigned out_hz,size_t slice) {
    IkAudioRateAdapter r;
    int16_t in[256 * 2],out[1024 * 2];
    size_t i, pos=0,total=0;
    uint64_t sum=0;
    ik_audio_rate_init(&r,in_hz,out_hz);
    while (pos < in_hz) {
        size_t n=in_hz-pos;
        if (n>slice)n=slice;
        for (i=0;i<n;i++){
            in[2*i]=(int16_t)((pos+i)%10000);
            in[2*i+1]=-(int16_t)((pos+i)%10000);
        }
        size_t made=ik_audio_rate_convert(&r,in,n,out,1024);
        assert(made!=SIZE_MAX && made<1024);
        for (i=0;i<made;i++) {
            assert(out[2*i]>=0 && out[2*i]<=10000);
            assert(out[2*i+1]<=0 && out[2*i+1]>=-10000);
            sum+=(uint16_t)out[2*i];
        }
        total+=made;pos+=n;
    }
    /* One-sample start boundary is held until a second sample arrives. */
    assert(total>out_hz-4 && total<=out_hz+2);
    assert(sum>0);
}
int main(void) {
    IkAudioRateAdapter r;
    int16_t in[]={120,-120,121,-121,122,-122},out[12];
    ik_audio_rate_init(&r,32768,32768);
    assert(ik_audio_rate_convert(&r,in,3,out,3)==3);
    assert(!memcmp(in,out,sizeof(in)));
    assert(ik_audio_rate_convert(&r,in,3,out,2)==SIZE_MAX);
    run(32768,32040,256);
    run(32768,32000,256);
    run(32768,48000,256);
    run(32768,44100,128);
    puts("PASS: audio rate adapter 32768 to 32040/32000/48000/44100");
    return 0;
}
