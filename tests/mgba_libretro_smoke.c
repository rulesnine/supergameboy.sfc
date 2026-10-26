// Ik Core GB core proof-of-viability (original code, no game ROM or BIOS).
// dlopen() mGBA libretro, present synthetic ROM, execute N GB frames,
// report video/audio delivery and deterministic output fingerprint.
// This does NOT yet connect SPC700: intentionally no "SGB audio works" claim.
#define _GNU_SOURCE
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
#include <time.h>
#include "libretro.h"

static uint64_t video_frames, audio_frames;
static uint32_t video_digest=2166136261u;
static const char* system_path=".";
static bool environment(unsigned command,void *data) {
    switch(command) {
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return *(enum retro_pixel_format*)data==RETRO_PIXEL_FORMAT_RGB565;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char**)data=system_path; return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE:
        *(bool*)data=true; return true;
    default: return false;
    }
}
static void video_cb(const void *pixels,unsigned w,unsigned h,size_t pitch) {
    if(!pixels) return;
    ++video_frames;
    if(!w||!h||pitch<2*w) {fprintf(stderr,"bad video geometry\n");exit(11);}
    const uint8_t *p=pixels;
    for(unsigned i=0;i<32 && i<w*2;++i)
        video_digest=(video_digest^(uint32_t)p[i])*16777619u;
}
static void audio_cb(int16_t left,int16_t right) { (void)left;(void)right; ++audio_frames; }
static size_t audio_batch(const int16_t *pcm,size_t n) {(void)pcm;audio_frames+=n;return n;}
static void input_poll(void) {}
static int16_t input_state(unsigned port,unsigned dev,unsigned idx,unsigned id)
{(void)port;(void)dev;(void)idx;(void)id;return 0;}
#define SYM(N) __typeof__(&N) p_##N=(__typeof__(&N))dlsym(lib,#N);if(!p_##N){fprintf(stderr,"missing %s: %s\n",#N,dlerror());return 3;}
static double monotonic(void){
    struct timespec s;
    clock_gettime(CLOCK_MONOTONIC,&s);
    return (double)s.tv_sec+1e-9*(double)s.tv_nsec;
}
static unsigned char *load_file(const char *name,size_t *len) {
    FILE *f=fopen(name,"rb"); if(!f)return NULL;
    if(fseek(f,0,SEEK_END)) {fclose(f);return NULL;}
    long n=ftell(f); if(n<0){fclose(f);return NULL;}
    rewind(f);
    unsigned char *p=malloc((size_t)n);if(!p){fclose(f);return NULL;}
    if(fread(p,1,(size_t)n,f)!=(size_t)n){free(p);fclose(f);return NULL;}
    fclose(f); *len=(size_t)n; return p;
}
int main(int argc,char **argv) {
    if(argc<3){fprintf(stderr,"usage: smoke <mgba_libretro.so> <synthetic.gb> [frames]\n");return 2;}
    unsigned frames=argc>3?(unsigned)strtoul(argv[3],NULL,10):240;
    if(frames<1||frames>2400)return 2;
    void *lib=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
    if(!lib){fprintf(stderr,"dlopen: %s\n",dlerror());return 3;}
    SYM(retro_set_environment)
    SYM(retro_set_video_refresh)
    SYM(retro_set_audio_sample)
    SYM(retro_set_audio_sample_batch)
    SYM(retro_set_input_poll)
    SYM(retro_set_input_state)
    SYM(retro_init)
    SYM(retro_deinit)
    SYM(retro_load_game)
    SYM(retro_unload_game)
    SYM(retro_run)
    SYM(retro_get_system_av_info)
    size_t rom_size=0;
    unsigned char *rom=load_file(argv[2],&rom_size);
    if(!rom)return 4;
    p_retro_set_environment(environment);
    p_retro_set_video_refresh(video_cb);
    p_retro_set_audio_sample(audio_cb);
    p_retro_set_audio_sample_batch(audio_batch);
    p_retro_set_input_poll(input_poll);
    p_retro_set_input_state(input_state);
    p_retro_init();
    struct retro_game_info game={argv[2],rom,rom_size,NULL};
    if(!p_retro_load_game(&game)){fprintf(stderr,"load synthetic GB ROM failed\n");return 5;}
    struct retro_system_av_info info={0};
    p_retro_get_system_av_info(&info);
    fprintf(stdout,"IKMGBA model video=%ux%u fps=%0.5f sampleHz=%0.2f\n",
        info.geometry.base_width,info.geometry.base_height,
        info.timing.fps,info.timing.sample_rate);
    double t0=monotonic();
    for(unsigned i=0;i<frames;++i)p_retro_run();
    double delta=monotonic()-t0;
    fprintf(stdout,"IKMGBA_OK runs=%u delivered_video=%llu audio_samples=%llu "
        "video_hash=%08X speed_unthrottled=%.2f fps cpu_ms_per_frame=%.3f\n",
        frames,(unsigned long long)video_frames,
        (unsigned long long)audio_frames,video_digest,
        (double)frames/delta,1000.0*delta/(double)frames);
    p_retro_unload_game();
    p_retro_deinit();
    free(rom);
    dlclose(lib);
    if(video_frames==0||audio_frames==0||info.geometry.base_width==0)return 6;
    return 0;
}
