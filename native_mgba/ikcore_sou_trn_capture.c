/* Ik Core SGB 4KiB LCD transfer sampler.
 *
 * This does not emulate, synthesize or change SGB SNES audio. It captures the
 * original 2-bit pixel stream in the same tile-planar order as SGB PAL_TRN
 * (mGBA software renderer) and as the verified Ik Core #43 border decoder.
 * No expensive sampling outside the one SOU_TRN transfer frame.
 *
 * Important: audio SPC execution must consume completed payload on the host
 * thread via a bounded, ordered FIFO. This file only produces validated data.
 */
#include "ikcore_sou_trn_capture.h"
#include <string.h>

void ikcore_sou_capture_reset(ikcore_sou_capture *c) {
    if (c) memset(c,0,sizeof(*c));
}
void ikcore_sou_capture_arm(ikcore_sou_capture *c) {
    if(!c)return;
    if(c->pending || c->recording) ++c->interrupted;
    c->pending=true;
    c->recording=false;
    c->frames_to_skip=IKCORE_SOU_SKIP_FRAMES;
    c->complete_bytes=0;
    memset(c->seen,0,sizeof(c->seen));
    memset(c->payload,0,sizeof(c->payload));
}
void ikcore_sou_capture_scanline(ikcore_sou_capture *c,int y,
                                const uint16_t *pixels,unsigned width) {
    if(!c || !c->recording || !pixels || width<IKCORE_SOU_PIXELS ||
       y<0 || y>=144)return;
    /* SNES 2bpp tile order: 20 tiles/row *16 bytes/tile, 8 LCD lines/tile row.
       Each scanline writes two bytes of each 8x8 tile, not 40 contiguous bytes. */
    const unsigned row=(unsigned)y;
    const unsigned offset=2u*((row&7u)+(row>>3u)*IKCORE_SOU_PIXELS);
    for(unsigned tile_x=0;tile_x<IKCORE_SOU_PIXELS;tile_x+=8u) {
        const unsigned addr=offset+tile_x*2u;
        if(addr+1u>=IKCORE_SOU_BYTES)break;
        uint8_t low=0,high=0;
        for(unsigned n=0;n<8u;++n) {
            const uint8_t color=(uint8_t)(pixels[tile_x+n]&3u);
            low|=(uint8_t)((color&1u)<<(7u-n));
            high|=(uint8_t)(((color>>1u)&1u)<<(7u-n));
        }
        c->payload[addr]=low;
        c->payload[addr+1u]=high;
        if(!c->seen[addr]) {c->seen[addr]=1;++c->complete_bytes;}
        if(!c->seen[addr+1u]) {c->seen[addr+1u]=1;++c->complete_bytes;}
    }
}
bool ikcore_sou_capture_end_frame(ikcore_sou_capture *c,
                                  ikcore_sou_complete_cb cb,void *ctx) {
    if(!c || !c->pending)return false;
    if(!c->recording) {
        if(c->frames_to_skip) {
            --c->frames_to_skip;
            if(!c->frames_to_skip) c->recording=true;
        }
        return false;
    }
    c->pending=false;
    c->recording=false;
    if(c->complete_bytes!=IKCORE_SOU_BYTES) {
        ++c->incomplete;
        return false;
    }
    ++c->completed;
    if(cb)cb(c->payload,IKCORE_SOU_BYTES,ctx);
    return true;
}

/* Optional weak host callback: preserves both standalone mGBA and unit
 * test availability without pulling Ik Core/Snes9x into the GB library. */
#if defined(__GNUC__)
extern void ikcore_sgb_transfer_completed_hook(const uint8_t *payload,
    unsigned size) __attribute__((weak));
#endif
static ikcore_sou_capture singleton;
static void ikcore_sou_emit(const uint8_t *payload,unsigned size,void *ctx) {
    (void)ctx;
#if defined(__GNUC__)
    if(ikcore_sgb_transfer_completed_hook)
        ikcore_sgb_transfer_completed_hook(payload,size);
#else
    (void)payload; (void)size;
#endif
}
void ikcore_sgb_transfer_reset_hook(void) {
    ikcore_sou_capture_reset(&singleton);
}
void ikcore_sgb_transfer_command_hook(unsigned command) {
    if(command==9u)ikcore_sou_capture_arm(&singleton); /* SOU_TRN */
}
void ikcore_sgb_transfer_scanline_hook(int y,const uint16_t *pixels,unsigned width) {
    ikcore_sou_capture_scanline(&singleton,y,pixels,width);
}
void ikcore_sgb_transfer_frame_hook(void) {
    (void)ikcore_sou_capture_end_frame(&singleton,ikcore_sou_emit,0);
}
