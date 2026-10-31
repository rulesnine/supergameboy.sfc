#!/usr/bin/env python3
"""RC3: show a DMG-style 'CARGANDO' screen before SPC BIOS bootstrap;
suppress ALL mGBA interim visual frames until a ROM's own border PCT is
settled or the genuine SGB fallback is due. Does not block emulated frames,
the #40 SPC700 mailbox, audio callbacks, input or the selected 60fps timer.
"""
from pathlib import Path
import sys

def once(s,a,b,name):
    n=s.count(a)
    if n!=1:raise ValueError(f"{name}: expected one anchor, found {n}")
    return s.replace(a,b,1)

def patch(s,graphics):
    s=once(s,"static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{",
           graphics+"\nstatic void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{",
           "pixel-art loading UI before video callback")
    s=once(s,
        "static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{\n    double t0 = now_s();",
        '''static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)
{
    double t0 = now_s();
    /* The core still advances every frame; audio and SGB packets are untouched.
     * Only presentation remains on the Game Boy CARGANDO texture. A game
     * never exposes mGBA's temporary default art before its own PCT border. */
    if(ik_prod_load_phase && !ik_prod_gate.visible) {
        uint64_t pal=0,attrs=0,chr=0,pct=0,mask=0;
        int full=(data!=NULL && width==256u && height==224u);
        if(ikcore_sgb_prod_visual_stats)
            ikcore_sgb_prod_visual_stats(&pal,&attrs,&chr,&pct,&mask);
        if(!ik_prod_gate_frame(&ik_prod_gate,(uint32_t)pct,full)) {
            if((ik_prod_gate.frames%24u)==0u)
                ik_prod_loading_animate(ik_prod_gate.frames);
            g_video_seconds+=now_s()-t0;
            return;
        }
        log_printf("IKSGB LOADING HANDOFF frame=%u PCT_TRN=%u"
                   " source=%s border=%s\\n",
                   ik_prod_gate.frames,(unsigned)pct,
                   pct?"ROM_CUSTOM":"SGB_DEFAULT",
                   g_f6_spc.original_border_valid?"BIOS_ORIGINAL":"mGBA_FALLBACK");
    }''',
           "gate video output only, not CPU/PPU/audio")
    s=once(s,
        '''    g_padfd = open_clovercon();''',
        '''    /* Draw before mGBA/ALSA and the 35s synchronous firmware boot.
     * The already-bound EGL surface keeps this picture visible while
     * Snes9x initializes the genuine Super Game Boy's SPC700/DSP. */
    ik_prod_gate_init(&ik_prod_gate,1);
    ik_prod_show_loading();
    ik_f6_spc_set_boot_progress(ik_prod_loading_animate);
    g_padfd = open_clovercon();''',
        "display gameboy as soon as Mali EGL is up")
    s=once(s,
        '''    game_loaded = 1;''',
        '''    game_loaded = 1;
    {
        unsigned m=0,b=0,rom_sgb=0,w=0,h=0;
        if(ikcore_fase5_sgb_status)
            ikcore_fase5_sgb_status(&m,&b,&rom_sgb,&w,&h);
        ik_prod_gate_init(&ik_prod_gate,(int)rom_sgb);
        log_printf("IKSGB LOADING classification SGB=%u initial=%ux%u"
                   " max_game_frames=%u\\n",
                   rom_sgb,w,h,rom_sgb?480u:4u);
    }''',
        "classify game SGB support after ROM is loaded")
    return s

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("Usage: patch_prod_loading_screen.py GENERATED_FRONTEND.c LOADING_SCREEN.inc")
    f=Path(sys.argv[1]);gfx=Path(sys.argv[2]).read_text()
    f.write_text(patch(f.read_text(),gfx))
    print("PASS: Game Boy CARGANDO frame before BIOS boot, direct custom PCT or original default SGB handoff")
