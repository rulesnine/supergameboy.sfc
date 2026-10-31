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
#include <time.h>
#include <sys/stat.h>
#include <limits.h>
#include <errno.h>
/* The SGB firmware cache contains a user-owned machine state; never shipped. */
#define IK_PROD_CACHE_DIR "/var/lib/hakchi/sgb-native-test/ikcore-sgb-prod-cache"
#define IK_PROD_CACHE_MAGIC 0x53474250524f4403ULL
#define IK_PROD_MAX_STATE (48u * 1024u * 1024u)
#define IK_PROD_BORDER_PIXELS (256u * 224u)
static uint16_t g_prod_boot_frame[IK_PROD_BORDER_PIXELS];
static unsigned g_prod_boot_frames;
static uint16_t g_prod_stock_border[IK_PROD_BORDER_PIXELS];
static int g_prod_stock_valid;
static enum retro_pixel_format g_prod_boot_format = RETRO_PIXEL_FORMAT_0RGB1555;
struct IkProdCacheHeader {
    uint64_t magic, pack_fingerprint;
    uint32_t serialized_bytes, border_valid;
    uint32_t boot_frames, reserved;
};
static uint64_t ik_prod_hash_pack(const char *path) {
    FILE *fp=fopen(path,"rb");
    unsigned char data[8192];size_t n,j;
    uint64_t h=14695981039346656037ULL;
    if(!fp)return 0;
    while((n=fread(data,1,sizeof data,fp))>0) {
        for(j=0;j<n;j++) {h^=data[j];h*=1099511628211ULL;}
    }
    if(ferror(fp))h=0;
    fclose(fp);
    return h;
}
static void ik_prod_cache_path(char *out,size_t len,uint64_t hash) {
    snprintf(out,len,IK_PROD_CACHE_DIR "/boot-%016llx.cache",
             (unsigned long long)hash);
}
static int ik_prod_border_usable(const uint16_t *p) {
    size_t k;unsigned changes=0; uint16_t first;
    if(g_prod_boot_frames==0)return 0;
    first=p[0];
    /* Reject black/flat splash and boot screens. The user owns the actual
     * firmware art. Only outer 48px/40px are presented; never game pixels. */
    for(k=0;k<IK_PROD_BORDER_PIXELS;k+=47) {
        unsigned y=(unsigned)(k/256),x=(unsigned)(k%256);
        if(x>=48&&x<208&&y>=40&&y<184)continue;
        if(p[k]!=first && ++changes>24) return 1;
    }
    return 0;
}
static int ik_prod_cache_load(IkF6SpcHost *h,uint64_t hash,
                              size_t (*get_size)(void),
                              bool (*restore)(const void *,size_t),
                              int (*resume)(void),IkF6Log log) {
    struct IkProdCacheHeader hdr;
    char path[256];FILE *fp=NULL;uint8_t *buf=NULL;
    size_t size;int ok=0;
    if(!hash||!get_size||!restore||!resume)return 0;
    ik_prod_cache_path(path,sizeof path,hash);
    fp=fopen(path,"rb");
    if(!fp) {
        if(log)log("IKSPC FASTBOOT cache=ABSENT errno=%d (pack-dependent cold boot)\\n",errno);
        return 0;
    }
    if(fread(&hdr,1,sizeof hdr,fp)!=sizeof hdr ||
       hdr.magic!=IK_PROD_CACHE_MAGIC || hdr.pack_fingerprint!=hash ||
       hdr.serialized_bytes<4096 || hdr.serialized_bytes>IK_PROD_MAX_STATE ||
       hdr.serialized_bytes!=get_size() || hdr.border_valid>1)goto done;
    size=hdr.serialized_bytes;
    buf=(uint8_t*)malloc(size);if(!buf)goto done;
    if(fread(buf,1,size,fp)!=size)goto done;
    if(fread(h->original_border_rgb565,sizeof(uint16_t),
             IK_PROD_BORDER_PIXELS,fp)!=IK_PROD_BORDER_PIXELS)goto done;
    if(!restore(buf,size))goto done;
    if(!resume())goto done;
    h->original_border_valid=(int)hdr.border_valid;
    h->boot_frames=hdr.boot_frames;
    h->fastboot_cache_hit=1;
    ok=1;
    if(log)log("IKSPC FASTBOOT cache=HIT saved_boot_frames=%u border=%s\n",
               h->boot_frames,h->original_border_valid?"BIOS_ORIGINAL":"UNVERIFIED");
done:
    free(buf);fclose(fp);
    if(!ok && log)log("IKSPC FASTBOOT cache=MISSED_OR_INVALID; full firmware boot used\n");
    return ok;
}
static void ik_prod_cache_save(IkF6SpcHost *h,uint64_t hash,
                               size_t (*get_size)(void),
                               bool (*save)(void *,size_t),IkF6Log log) {
    struct IkProdCacheHeader hdr;char path[256],tmp[280];
    uint8_t *buf=NULL;FILE *fp=NULL;
    size_t size;
    if(!hash||!get_size||!save)return;
    size=get_size();
    if(size<4096||size>IK_PROD_MAX_STATE)return;
    buf=(uint8_t*)malloc(size);if(!buf)return;
    if(!save(buf,size))goto done;
    (void)mkdir(IK_PROD_CACHE_DIR,0700);
    ik_prod_cache_path(path,sizeof path,hash);
    snprintf(tmp,sizeof tmp,"%s.tmp-%ld",path,(long)getpid());
    fp=fopen(tmp,"wb");if(!fp)goto done;
    memset(&hdr,0,sizeof hdr);
    hdr.magic=IK_PROD_CACHE_MAGIC;hdr.pack_fingerprint=hash;
    hdr.serialized_bytes=(uint32_t)size;
    hdr.border_valid=h->original_border_valid;
    hdr.boot_frames=h->boot_frames;
    if(fwrite(&hdr,1,sizeof hdr,fp)!=sizeof hdr ||
       fwrite(buf,1,size,fp)!=size ||
       fwrite(h->original_border_rgb565,sizeof(uint16_t),
               IK_PROD_BORDER_PIXELS,fp)!=IK_PROD_BORDER_PIXELS ||
       fflush(fp)!=0) {fclose(fp);fp=NULL;unlink(tmp);goto done;}
    if(fclose(fp)!=0){fp=NULL;unlink(tmp);goto done;}
    fp=NULL;
    if(rename(tmp,path)!=0){unlink(tmp);goto done;}
    if(log)log("IKSPC FASTBOOT cache=SAVED bytes=%lu border=%s\n",
               (unsigned long)size,
               h->original_border_valid?"BIOS_ORIGINAL":"UNVERIFIED");
done:
    if(fp){fclose(fp);unlink(tmp);}
    free(buf);
}

static IkF6Log g_log;
static void (*g_prod_boot_progress)(unsigned);
void ik_f6_spc_set_boot_progress(void (*callback)(unsigned)) {
    g_prod_boot_progress=callback;
}
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
        if ((*(enum retro_pixel_format*)data)==RETRO_PIXEL_FORMAT_RGB565 ||
            (*(enum retro_pixel_format*)data)==RETRO_PIXEL_FORMAT_0RGB1555) {
            g_prod_boot_format=*(enum retro_pixel_format*)data;
            return true;
        }
        return false;
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
        return true;
    default: return false;
    }
}
static void no_video(const void *p,unsigned w,unsigned h,size_t pitch)
{
    unsigned y;const uint8_t *src=(const uint8_t*)p;
    if(!p || w!=256 || h<224 || pitch<512 || pitch>8192)return;
    for(y=0;y<224;y++) {
        uint16_t *dst=&g_prod_boot_frame[(size_t)y*256u];
        const uint16_t *row=(const uint16_t*)(const void*)(src+(size_t)y*pitch);
        unsigned x;
        if(g_prod_boot_format==RETRO_PIXEL_FORMAT_RGB565) {
            memcpy(dst,row,512);
        } else if(g_prod_boot_format==RETRO_PIXEL_FORMAT_0RGB1555) {
            for(x=0;x<256;x++) {
                uint16_t p=row[x];
                unsigned r=(p>>10u)&31u,gg=(p>>5u)&31u,bb=p&31u;
                unsigned g6=(gg<<1u)|(gg>>4u);
                dst[x]=(uint16_t)((r<<11u)|(g6<<5u)|bb);
            }
        } else return;
    }
    ++g_prod_boot_frames;
}
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
                    unsigned out_rate, double gb_fps, IkF6Log log) {
    void (*set_environment)(retro_environment_t);
    void (*set_video)(retro_video_refresh_t);
    void (*set_sample)(retro_audio_sample_t);
    void (*set_batch)(retro_audio_sample_batch_t);
    void (*set_poll)(retro_input_poll_t);
    void (*set_state)(retro_input_state_t);
    bool (*load_game)(const struct retro_game_info *);
    void (*run)(void);
    void (*set_port)(unsigned,unsigned);
    size_t (*serialize_size)(void)=NULL;
    bool (*serialize)(void *,size_t)=NULL;
    bool (*unserialize)(const void *,size_t)=NULL;
    int (*resume)(void)=NULL;
    unsigned (*bios_pct_count)(void)=NULL;
    int (*bios_gb_released)(void)=NULL;
    uint64_t pack_hash=0;
    struct timespec boot_start_wall={0,0}, boot_end_wall={0,0};
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
    SYM(h->set_frame_fps,"ikcore_spc_set_frame_fps");
    SYM(h->mailbox_stats,"ikcore_spc_mailbox_stats");
    SYM(h->send_sound,"ikcore_spc_send_sound");
    SYM(h->send_transfer,"ikcore_spc_send_sou_trn");
    SYM(h->frame,"ikcore_spc_frame");
    SYM(h->pull,"ikcore_spc_pull_stereo");
    SYM(h->pending,"ikcore_spc_pending_frames");
    SYM(serialize_size,"retro_serialize_size");
    SYM(serialize,"retro_serialize");
    SYM(unserialize,"retro_unserialize");
    SYM(resume,"ikcore_spc_cache_restore_activate");
    SYM(bios_pct_count,"ikcore_spc_bios_border_pct_count");
    SYM(bios_gb_released,"ikcore_spc_bios_gb_released");
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
    clock_gettime(CLOCK_MONOTONIC,&boot_start_wall);
    g_prod_boot_frames=0;g_prod_stock_valid=0;
    memset(g_prod_boot_frame,0,sizeof g_prod_boot_frame);
    memset(g_prod_stock_border,0,sizeof g_prod_stock_border);
    pack_hash=ik_prod_hash_pack(pack);
    if(ik_prod_cache_load(h,pack_hash,serialize_size,unserialize,resume,log))
        goto boot_done;
    if(log) log("IKSPC original SGB firmware boot started (max 4800 frames)\n");
    for (i=0;i<4800;++i) {
        if(h->boot_ready()) break;
        run();
        if(g_prod_boot_progress && (i % 120u)==119u)
            g_prod_boot_progress(i+1u);
        /* Do not confuse the game's own SGB border with BIOS default.
         * Capture after SGB releases GB but BEFORE the first game PCT_TRN.
         * Once PCT arrives, freeze the last genuine BIOS border. */
        if(bios_gb_released && bios_pct_count &&
           bios_gb_released() && bios_pct_count()==0 &&
           ik_prod_border_usable(g_prod_boot_frame)) {
            memcpy(g_prod_stock_border,g_prod_boot_frame,
                   sizeof g_prod_stock_border);
            g_prod_stock_valid=1;
        }
        if(log && (i+1u)%600u==0)
            log("IKSPC firmware boot frames=%u ready=%d\n",i+1u,h->boot_ready());
    }
    h->ready=h->boot_ready();
    h->boot_frames=i;
    if(!h->ready) {
        if(log) log("IKSPC firmware boot incomplete: audio SNES disabled\n");
        goto fail;
    }
    if(g_prod_stock_valid) {
        memcpy(h->original_border_rgb565,g_prod_stock_border,
               sizeof h->original_border_rgb565);
        h->original_border_valid=1;
        if(log)log("IKSGB BORDER source=BIOS_STOCK_BEFORE_GAME_PCT pixels=256x224\n");
    } else if(bios_pct_count && bios_pct_count()==0 &&
              ik_prod_border_usable(g_prod_boot_frame)) {
        /* A game without custom PCT: last BIOS frame is still the default. */
        memcpy(h->original_border_rgb565,g_prod_boot_frame,
               sizeof h->original_border_rgb565);
        h->original_border_valid=1;
        if(log)log("IKSGB BORDER source=BIOS_STOCK_NO_PCT pixels=256x224\n");
    } else if(log) {
        log("IKSGB BORDER source=FALLBACK (stock BIOS frame not safely captured)\n");
    }
    ik_prod_cache_save(h,pack_hash,serialize_size,serialize,log);
boot_done:
    h->ready=h->boot_ready();
    if (!h->set_frame_fps(gb_fps)) {
        if(log) log("IKSPC ERROR: invalid GB fps=%f\n",gb_fps);
        goto fail;
    }
    if(log) log("IKSPC initialized=1 boot_frames=%u GB_fps=%.5f SPC_cycles_per_frame=%.2f SNES GB CPU STOPPED\n",
                h->boot_frames, gb_fps, 1024000.0/gb_fps);
    clock_gettime(CLOCK_MONOTONIC,&boot_end_wall);
    if(log)log("IKSPC FASTBOOT hit=%d border_valid=%d startup_ms=%lu\n",
              h->fastboot_cache_hit,h->original_border_valid,
              (unsigned long)((boot_end_wall.tv_sec-boot_start_wall.tv_sec)*1000L+
              (boot_end_wall.tv_nsec-boot_start_wall.tv_nsec)/1000000L));
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
        {
            int j;
            for(j=0;j<n*2;j++)
                if(p[j]!=0) ++h->spc_nonzero;
        }
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
