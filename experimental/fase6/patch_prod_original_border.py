#!/usr/bin/env python3
"""Production-only original SGB1 boot border compositor.
Frame comes from the *user's* SGB1 SNES BIOS, captured by the parallel
Snes9x instance at the genuine firmware handoff.
Unlike generic mGBA sample artwork, this is the actual firmware pixels.
Only paint the 48/40px margin on 256x224 GB video frames; the game pane
and all ROM-authored PCT_TRN/CHR_TRN visuals remain untouched.
"""
from pathlib import Path
import sys
def once(s,a,b,k):
    n=s.count(a)
    if n!=1:raise ValueError(f"{k}: {n} anchors")
    return s.replace(a,b,1)

def patch(s):
    s=once(s,'static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{',
'''/* Static to avoid per-frame allocation on Cortex-A7; 112 KiB only. */
static uint16_t g_prod_border_comp[256u*224u];
static int g_prod_border_logged=0;
static const void *ik_prod_overlay_bios_border(const void *game,unsigned w,unsigned h)
{
    uint64_t pal=0,attrs=0,chr=0,pct=0,mask=0;
    unsigned y;
    if(!game || w!=256 || h!=224 ||
       !g_f6_ready || !g_f6_spc.original_border_valid ||
       !ikcore_sgb_prod_visual_stats)
        return game;

    ikcore_sgb_prod_visual_stats(&pal,&attrs,&chr,&pct,&mask);
    if(pct) return game; /* Original cart PCT always wins over BIOS bezel */
    memcpy(g_prod_border_comp,game,sizeof g_prod_border_comp);

    /* RGB565 from SNES boot frame, stored without blending or color loss. */
    for(y=0;y<224;y++) {
        const uint16_t *source=&g_f6_spc.original_border_rgb565[y*256u];
        uint16_t *dest=&g_prod_border_comp[y*256u];
        if(y<40u || y>=184u)
            memcpy(dest,source,256u*sizeof(uint16_t));
        else {
            memcpy(dest,source,48u*sizeof(uint16_t));
            memcpy(dest+208u,source+208u,48u*sizeof(uint16_t));
        }
    }
    if(!g_prod_border_logged) {
        log_printf("IKSGB BORDER display=ORIGINAL_SGB_BIOS ROM_PCT=0 RGB565=1 game_area_unmodified=1\\n");
        g_prod_border_logged=1;
    }
    return g_prod_border_comp;
}
static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)
{''','production overlay function')
    s=once(s,'        upload_rgb565_direct(packed, width, height);',
           '        upload_rgb565_direct(ik_prod_overlay_bios_border(packed,width,height), width, height);',
           'production RGB565 overlay placement')
    s=once(s,'    log_printf("video path  : RGB565 Mali; borde SGB atomico, fade visual desactivado\\n");',
           '''    log_printf("IKSGB BORDER firmware_capture=%d cache=%d\\n",
               g_f6_spc.original_border_valid,g_f6_spc.fastboot_cache_hit);
    log_printf("video path  : RGB565 Mali; borde SGB atomico, fade visual desactivado\\n");''',
           'border boot telemetry')
    return s
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_prod_original_border.py FRONTEND.c")
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
    print("PASS: authentic firmware border only for ROMs without PCT_TRN, no game pixel/palette modifications")
