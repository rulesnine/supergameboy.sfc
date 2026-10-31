/* SPDX-License-Identifier: MIT
 * Ik Core F6: SGBPACK1 firmware bootstrap and SPC-only mixed audio runtime.
 * No firmware, BIOS, ROM or SFX data is bundled with this module.
 * The experimental Snes9x #117 libretro core is loaded RTLD_LOCAL and
 * retro_run() is called ONLY during the SGB firmware boot.
 * All gameplay CPU/PPU and GB APU after that belong to mGBA.
 */
#define _GNU_SOURCE
#include "ik_spc_host.h"
#include "libretro.h"
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <unistd.h>
#include <stdarg.h>

static IkF6Log g_log;
static const char *g_system_directory="/var/lib/hakchi/sgb-native-test";
static void snes_log(enum retro_log_level level,const char *fmt, ...) {
    /* SNES core sometimes emits frequent debug messages; print errors only.
       varargs forward via temporary buffer so no format ambiguity. */
    char msg[256];
    va_list ap;
    if (!g_log || level < RETRO_LOG_WARN) return;
    va_start(ap,fmt);vsnprintf(msg,sizeof(msg),fmt,ap);va_end(ap);
    g_log("IKSPC core[%d]: %s", (int)level,msg);
}
static bool snes_environment(unsigned command,void *data) {
    if (!data) return false;
    switch(command) {
    case RETRO_ENVIRONMENT_GET_CAN_DUPE: *(bool*)data=true;return true;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char**)data=g_system_directory;return true;
    case RETRO_ENVIRONMENT_GET_LANGUAGE:
        *(unsigned*)data=RETRO_LANGUAGE_ENGLISH;return true;
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
        *(unsigned*)data=0;return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool*)data=false;return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE:
        return false;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
        ((struct retro_log_callback*)data)->log=snes_log;return true;
    case RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE:
        *(int*)data=3;return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        return true; /* silent video callback ignores RGB format */
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
        return true;
    default: return false;
    }
}
static void no_video(const void *p,unsigned w,unsigned h,size_t pitch)
{ (void)p;(void)w;(void)h;(void)pitch; }
static void no_audio(short l,short r) {(void)l;(void)r;}
static size_t no_audio_batch(const short *p,size_t frames)
{(void)p;return frames;}
static void no_input_poll(void){}
static int16_t no_input(unsigned port,unsigned device,unsigned index,unsigned id)
{(void)port;(void)device;(void)index;(void)id;return 0;}

static void *required(void *lib,const char *name) {
    void *p=dlsym(lib,name);
    if (!p && g_log) g_log("IKSPC missing symbol: %s\n",name);
    return p;
}
int ik_f6_spc_start(IkF6SpcHost *h,const char *so,const char *pack,
                    unsigned out_rate, IkF6Log log) {
    void (*set_environment)(retro_environment_t);
    void (*set_video)(retro_video_refresh_t);
    void (*set_sample)(retro_audio_sample_t);
    void (*set_batch)(retro_audio_sample_batch_t);
    void (*set_poll)(retro_input_poll_t);
    void (*set_state)(retro_input_state_t);
    bool (*load_game)(const struct retro_game_info *);
    void (*run)(void);
    void (*set_port)(unsigned,unsigned);
    struct retro_game_info game;
    unsigned i;
    if (!h || !so || !pack || !out_rate) return 0;
    memset(h,0,sizeof(*h));
    g_log=log;
    h->output_rate=out_rate;
    if(access(pack,R_OK)!=0) {
        if(log) log("IKSPC absent: SGBPACK1 not accessible: %s\n",pack);
        return 0;
    }
    h->library=dlopen(so,RTLD_NOW|RTLD_LOCAL);
    if(!h->library) {
        if(log) log("IKSPC dlopen failed: %s\n",dlerror());
        return 0;
    }
#define SYM(v,n) do {*(void**)(&v)=required(h->library,n);if(!v)goto fail;}while(0)
    SYM(set_environment,"retro_set_environment");
    SYM(set_video,"retro_set_video_refresh");
    SYM(set_sample,"retro_set_audio_sample");
    SYM(set_batch,"retro_set_audio_sample_batch");
    SYM(set_poll,"retro_set_input_poll");
    SYM(set_state,"retro_set_input_state");
    SYM(set_port,"retro_set_controller_port_device");
    SYM(h->init,"retro_init");
    SYM(h->deinit,"retro_deinit");
    SYM(h->unload_game,"retro_unload_game");
    SYM(load_game,"retro_load_game");
    SYM(run,"retro_run");
    SYM(h->boot_ready,"ikcore_spc_boot_ready");
    SYM(h->send_sound,"ikcore_spc_send_sound");
    SYM(h->send_transfer,"ikcore_spc_send_sou_trn");
    SYM(h->frame,"ikcore_spc_frame");
    SYM(h->pull,"ikcore_spc_pull_stereo");
    SYM(h->pending,"ikcore_spc_pending_frames");
#undef SYM
    set_environment(snes_environment);
    set_video(no_video);
    set_sample(no_audio);
    set_batch(no_audio_batch);
    set_poll(no_input_poll);
    set_state(no_input);
    h->init();h->initialized=1;
    set_port(0,RETRO_DEVICE_JOYPAD);
    memset(&game,0,sizeof(game));
    game.path=pack;
    if(!load_game(&game)) {
        if(log) log("IKSPC SGBPACK1 rejected: %s\n",pack);
        goto fail;
    }
    h->loaded=1;
    if(log) log("IKSPC original SGB firmware boot started (max 4800 frames)\n");
    for (i=0;i<4800;++i) {
        if(h->boot_ready()) break;
        run();
        if(log && (i+1u)%600u==0)
            log("IKSPC firmware boot frames=%u ready=%d\n",i+1u,h->boot_ready());
    }
    h->ready=h->boot_ready();
    if(!h->ready) {
        if(log) log("IKSPC firmware boot incomplete: audio SNES disabled\n");
        goto fail;
    }
    if(log) log("IKSPC initialized=1 boot_frames=%u SNES GB CPU STOPPED\n",i);
    return 1;
fail:
    ik_f6_spc_stop(h);
    return 0;
}
void ik_f6_spc_stop(IkF6SpcHost *h) {
    if(!h) return;
    if(h->loaded && h->unload_game)h->unload_game();
    if(h->initialized && h->deinit)h->deinit();
    if(h->library)dlclose(h->library);
    h->library=NULL;h->ready=0;
}
int ik_f6_spc_sound(IkF6SpcHost *h,const uint8_t packet[16]) {
    if(!h || !h->ready || !h->send_sound || !packet) return 0;
    if(h->send_sound(packet,16)) {++h->sound_sent;return 1;}
    ++h->sound_rejected;return 0;
}
int ik_f6_spc_transfer(IkF6SpcHost *h,const uint8_t *bytes,size_t size) {
    if(!h || !h->ready || !h->send_transfer || !bytes || size!=4096)return 0;
    return h->send_transfer(bytes,(unsigned)size);
}
static void queue_audio(IkF6SpcHost *h, const int16_t *samples,size_t frames) {
    size_t i;
    for(i=0;i<frames;i++) {
        size_t j;
        if(h->fifo_count>=16384u) {
            h->fifo_read=(h->fifo_read+1u)%16384u;
            --h->fifo_count;++h->buffer_overflows;
        }
        j=(h->fifo_read+h->fifo_count)%16384u;
        h->fifo[2*j]=samples[2*i];h->fifo[2*j+1]=samples[2*i+1];
        ++h->fifo_count;
    }
}
/* Fixed-point-like continuous linear stereo adaptor for 32040 SPC samples
   per second. This preserves the 60Hz cadence when ALSA is 32000/48000.
   No truncation of sample-rate by simply relabelling the PCM stream. */
static void resample_push(IkF6SpcHost *h,const int16_t *p,int frames) {
    double phase,step;
    int16_t next[4096];
    int count=0;
    if(!frames)return;
    phase=h->sample_position;
    if(!h->have_prev) {
        h->prev[0]=p[0];h->prev[1]=p[1];
        phase=1.0;h->have_prev=1;
    }
    step=32040.0/(double)h->output_rate;
    while(phase<(double)frames && count<2048) {
        int base=(int)phase;
        double f=phase-(double)base;
        double ll=base?p[(base-1)*2]:h->prev[0];
        double lr=base?p[(base-1)*2+1]:h->prev[1];
        next[count*2]=(int16_t)(ll+((double)p[base*2]-ll)*f);
        next[count*2+1]=(int16_t)(lr+((double)p[base*2+1]-lr)*f);
        phase+=step;++count;
    }
    queue_audio(h,next,(size_t)count);
    h->sample_position=phase-(double)frames;
    h->prev[0]=p[(frames-1)*2];h->prev[1]=p[(frames-1)*2+1];
}
void ik_f6_spc_frame(IkF6SpcHost *h) {
    int16_t p[2048];
    int avail,n;
    if(!h||!h->ready||!h->frame||!h->pull||!h->pending)return;
    if(!h->frame()){h->ready=0;return;}
    ++h->frames_advanced;
    avail=h->pending();
    while(avail>0) {
        n=avail>1024?1024:avail;
        n=h->pull(p,n);
        if(n<=0) break;
        resample_push(h,p,n);
        avail=h->pending();
    }
}
static int16_t sat(int v,IkF6SpcHost *h) {
    if(v>32767){++h->clipped;return 32767;}
    if(v<-32768){++h->clipped;return -32768;}
    return (int16_t)v;
}
void ik_f6_spc_mix_one(IkF6SpcHost *h,int16_t *l,int16_t *r) {
    int16_t sl,sr;
    if(!h||!h->ready||!l||!r)return;
    if(!h->fifo_count){++h->silence;return;}
    sl=h->fifo[h->fifo_read*2u];
    sr=h->fifo[h->fifo_read*2u+1];
    h->fifo_read=(h->fifo_read+1u)%16384u;
    --h->fifo_count;
    /* Preserve original GB music at 0.80 and SPC effects at 0.70.
       Gains are conservative until a real KOF96 audio reference is heard. */
    *l=sat((int)*l*4/5+(int)sl*7/10,h);
    *r=sat((int)*r*4/5+(int)sr*7/10,h);
    ++h->mixed;
}
