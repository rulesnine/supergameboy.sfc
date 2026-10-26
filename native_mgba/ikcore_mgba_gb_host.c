/* Ik Core Fase 3: mGBA-only GB CPU engine host.
 * All Game Boy execution, PPU, audio and MBC belong exclusively to mGBA.
 * SPC700/DSP and SGB graphics are attached separately by Ik Core.
 * Based on public mGBA mCore host ABI, pinned by our build.
 */
#define _POSIX_C_SOURCE 200809L
#include "ikcore_mgba_gb_host.h"
#include <mgba/core/core.h>
#include <mgba/core/config.h>
#include <mgba/gb/interface.h>
#include <mgba/internal/gb/gb.h>
#include <mgba-util/vfs.h>
#include <mgba-util/audio-buffer.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef IKCORE_MGBA_DIAGNOSTIC
#include <stdio.h>
#define IKHOST_TRACE(x) do {fprintf(stderr,"IKHOST_TRACE %s\n",x);fflush(stderr);}while(0)
#else
#define IKHOST_TRACE(x) do {}while(0)
#endif
#include <stdbool.h>

struct ikcore_mgba_host {
    struct mCore *core;
    unsigned char *rom_data;
    size_t rom_bytes;
    mColor *video;
    unsigned frame_index;
    unsigned model;
};
static double ik_time_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec*1000.0+(double)t.tv_nsec*0.000001;
}
ikcore_mgba_host *ikcore_mgba_open(const void *gb_rom,size_t rom_bytes,int sgb_mode) {
    if(!gb_rom || rom_bytes<0x150 || rom_bytes>8u*1024u*1024u)return NULL;
    ikcore_mgba_host *h=calloc(1,sizeof(*h));
    if(!h)return NULL;
    h->rom_data=malloc(rom_bytes);
    h->video=calloc((size_t)IKCORE_SGB_SCREEN_W*IKCORE_SGB_SCREEN_H,sizeof(mColor));
    if(!h->rom_data || !h->video) {ikcore_mgba_close(h);return NULL;}
    memcpy(h->rom_data,gb_rom,rom_bytes);
    h->rom_bytes=rom_bytes;
    IKHOST_TRACE("rom copied");
    /* mCoreFindVF checks for Game Boy / GBX; the caller's source stays owned. */
    struct VFile *vf=VFileFromMemory(h->rom_data,h->rom_bytes);
    if(!vf) {ikcore_mgba_close(h);return NULL;}
    IKHOST_TRACE("VFile allocated");
    h->core=mCoreFindVF(vf);
    if(!h->core) {
        vf->close(vf);
        ikcore_mgba_close(h);
        return NULL;
    }
    IKHOST_TRACE("mCore detected");
    mCoreInitConfig(h->core,NULL);
    if(!h->core->init(h->core)) {
        mCoreConfigDeinit(&h->core->config);
        h->core->deinit(h->core);
        h->core=NULL;
        vf->close(vf);
        ikcore_mgba_close(h);
        return NULL;
    }
    IKHOST_TRACE("mCore initialized");
    /* Full frame uses a single mCore framebuffer, also for SGB 256x224. */
    h->core->setVideoBuffer(h->core,h->video,IKCORE_SGB_SCREEN_W);
    h->core->opts.skipBios=true;   /* No proprietary GB boot ROM in SDK. */
    h->core->opts.useBios=false;
    h->core->opts.mute=false;
    h->core->opts.volume=0x100;
    h->core->opts.frameskip=0;
    /* The GB APU is retained. Native SGB SNES audio gets mixed by Ik Core,
       not from a second GB core. mGBA stereo rate is 131072 Hz. */
    h->core->setAudioBufferSize(h->core,IKCORE_GB_AUDIO_BUFFER_FRAMES);
    IKHOST_TRACE("mCore framebuffer and APU configured");
    if(!h->core->loadROM(h->core,vf)) {
        /* mGBA may have retained vf on failure; its unloadROM owns cleanup. */
        h->core->unloadROM(h->core);
        ikcore_mgba_close(h);
        return NULL;
    }
    IKHOST_TRACE("mCore ROM loaded");
    struct GB *gb=(struct GB*)h->core->board;
    if(sgb_mode) {
        gb->model=GB_MODEL_SGB;
        mCoreConfigSetDefaultValue(&h->core->config,"sgb.model","SGB");
    } else {
        gb->model=GB_MODEL_DMG;
        mCoreConfigSetDefaultValue(&h->core->config,"gb.model","DMG");
    }
    IKHOST_TRACE("before GB CPU reset");
    h->core->reset(h->core);
    IKHOST_TRACE("after GB CPU reset");
    h->model=(unsigned)gb->model;
    /* A reliable SGB session MUST run mGBA as SGB. Otherwise silently
       launching in DMG would drop all SGB SOUND/PAL/CHR/PCT packets. */
    if(sgb_mode && !(h->model & GB_MODEL_SGB)){
        ikcore_mgba_close(h);return NULL;
    }
    return h;
}
int ikcore_mgba_run(ikcore_mgba_host *host,uint8_t gb_keys,ikcore_mgba_frame *out) {
    if(!host || !host->core || !out)return 0;
    struct mCore *core=host->core;
    core->setKeys(core,gb_keys);
    const double t0=ik_time_ms();
    if(host->frame_index==0) IKHOST_TRACE("before first runFrame");
    core->runFrame(core); /* ONE CPU: mGBA. Snes9x GB CPU is NOT running. */
    if(host->frame_index==0) IKHOST_TRACE("after first runFrame");
    const double t1=ik_time_ms();
    unsigned w=0,ht=0;
    core->currentVideoSize(core,&w,&ht);
    if(w==0||ht==0||w>IKCORE_SGB_SCREEN_W||ht>IKCORE_SGB_SCREEN_H) return 0;
    memset(out,0,sizeof(*out));
    out->video=host->video;
    out->width=w;out->height=ht;
    out->pitch_pixels=IKCORE_SGB_SCREEN_W;
    out->pixel_bytes=(unsigned)sizeof(mColor);
    out->audio_rate=core->audioSampleRate(core);
    struct mAudioBuffer *ab=core->getAudioBuffer(core);
    size_t available=mAudioBufferAvailable(ab);
    if(available>IKCORE_GB_AUDIO_BUFFER_FRAMES)available=IKCORE_GB_AUDIO_BUFFER_FRAMES;
    if(available)out->audio_frames=(unsigned)mAudioBufferRead(ab,out->audio_stereo,available);
    out->gb_frame_ms=t1-t0;
    out->frame_number=++host->frame_index;
    out->total_gb_cpu_frames=core->frameCounter(core);
    return 1;
}
size_t ikcore_mgba_clone_sram(ikcore_mgba_host *h,void **allocated) {
    if(!allocated)return 0;
    *allocated=NULL;
    if(!h || !h->core || !h->core->savedataClone)return 0;
    return h->core->savedataClone(h->core,allocated);
}
int ikcore_mgba_restore_sram(ikcore_mgba_host *h,const void *bytes,size_t n) {
    if(!h || !h->core || !h->core->savedataRestore || (!bytes && n))return 0;
    return h->core->savedataRestore(h->core,bytes,n,true)?1:0;
}
unsigned ikcore_mgba_model(const ikcore_mgba_host *host) {
    return host?host->model:0xFFu;
}
void ikcore_mgba_close(ikcore_mgba_host *host) {
    if(!host)return;
    if(host->core) {
        IKHOST_TRACE("before mCore unload");
        host->core->unloadROM(host->core);
        IKHOST_TRACE("after mCore unload");
        mCoreConfigDeinit(&host->core->config);
        host->core->deinit(host->core);
        IKHOST_TRACE("after mCore deinit");
    }
    free(host->rom_data);
    free(host->video);
    free(host);
}
