#include "../native_mgba/ikcore_mgba_gb_host.h"
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifdef IKCORE_MGBA_DIAGNOSTIC
#include <signal.h>
#include <execinfo.h>
static void on_crash(int sig) {
  void *frames[48]={0};
  int n=backtrace(frames,48);
  fprintf(stderr,"IKHOST_CRASH signal=%d frames=%d\n",sig,n);
  backtrace_symbols_fd(frames,n,2);
  _Exit(128+sig);
}
#endif
static unsigned char *read_rom(const char *path,size_t *length) {
    FILE *f=fopen(path,"rb");
    if(!f)return NULL;
    if(fseek(f,0,SEEK_END)){fclose(f);return NULL;}
    long n=ftell(f);
    if(n<0 || n>8*1024*1024){fclose(f);return NULL;}
    rewind(f);
    unsigned char *buf=malloc((size_t)n);
    if(!buf){fclose(f);return NULL;}
    if(fread(buf,1,(size_t)n,f)!=(size_t)n){free(buf);fclose(f);return NULL;}
    fclose(f);*length=(size_t)n;return buf;
}
static int run_test(const void *data,size_t bytes,int sgb) {
    ikcore_mgba_host *h=ikcore_mgba_open(data,bytes,sgb);
    if(!h){fprintf(stderr,"ikcore_mgba_open failed for sgb=%d\n",sgb);return 2;}
    if(sgb && !(ikcore_mgba_model(h)&0x20u)) {
        fprintf(stderr,"SGB model flag not active\n");ikcore_mgba_close(h);return 3;
    }
    const int n=sgb?24:240;
    unsigned audio=0;double frame_ms=0;
    for(int i=0;i<n;i++) {
        ikcore_mgba_frame out;
        uint8_t input=(uint8_t)((i%40==0)?IKCORE_GB_A:0);
        if(!ikcore_mgba_run(h,input,&out)) {
            fprintf(stderr,"ikcore_mgba_run failed at %d\n",i);return 4;
        }
        if(!out.video||out.width<160||out.height<144 ||
           out.width>256||out.height>224||!out.audio_rate ||
           out.audio_frames>IKCORE_GB_AUDIO_BUFFER_FRAMES ||
           out.frame_number!=(unsigned)i+1) {
            fprintf(stderr,"incorrect output geometry or sample count: %ux%u rate=%u audio=%u frame=%u\n",
                out.width,out.height,out.audio_rate,out.audio_frames,out.frame_number);
            return 5;
        }
        audio+=out.audio_frames;
        frame_ms+=out.gb_frame_ms;
    }
    void *sram=NULL;
    size_t save_bytes=ikcore_mgba_clone_sram(h,&sram);
    if(sram)free(sram);
    printf("IKCORE_MCORE_HOST_OK model=%s frames=%d avgGBFrameMs=%.4f totalAudio=%u sram=%zu\n",
        sgb?"SGB":"DMG",n,frame_ms/n,audio,save_bytes);
    ikcore_mgba_close(h);
    return 0;
}
int main(int argc,char **argv) {
#ifdef IKCORE_MGBA_DIAGNOSTIC
    signal(SIGSEGV,on_crash);
    signal(SIGABRT,on_crash);
#endif
    if(argc<2)return 1;
    size_t len=0;unsigned char *data=read_rom(argv[1],&len);
    if(!data)return 1;
    int dm=run_test(data,len,0);
    int sg=dm?0:run_test(data,len,1);
    free(data);
    return dm?dm:sg;
}
