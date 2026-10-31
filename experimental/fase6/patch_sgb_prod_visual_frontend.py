#!/usr/bin/env python3
"""Production-branch-only diagnostics for mGBA's native SGB border/palette path.
No transformations to native game colors, pixels, border RAM or audio.
"""
from pathlib import Path
import sys

def once(text,old,new,label):
    n=text.count(old)
    if n!=1:raise ValueError(f"{label}: expected one anchor, found {n}")
    return text.replace(old,new,1)

def patch(s):
    s=once(s,
        'static int (*ikcore_f6_pop)(IkSgbPacket *);',
        'static void (*ikcore_sgb_prod_visual_stats)(uint64_t *,uint64_t *,uint64_t *,uint64_t *,uint64_t *);\n'
        'static int (*ikcore_f6_pop)(IkSgbPacket *);',
        'visual telemetry pointer')
    s=once(s,
        '    if (!ikcore_f6_pop) log_printf("IKSPC ERROR: mGBA SGB queue unavailable\\n");',
        '''    if (!ikcore_f6_pop) log_printf("IKSPC ERROR: mGBA SGB queue unavailable\\n");
    *(void **)(&ikcore_sgb_prod_visual_stats) =
        dlsym(g_libcore,"ikcore_sgb_prod_visual_stats");
    if (!ikcore_sgb_prod_visual_stats)
        log_printf("IKSGB VISUAL ERROR: runtime instrumentation missing\\n");''',
        'visual telemetry dlsym')
    s=once(s,
        '            last_run_frames = run_frames;',
        '''            if (ikcore_sgb_prod_visual_stats) {
                uint64_t pal=0,attr=0,chr=0,pct=0,mask=0;
                ikcore_sgb_prod_visual_stats(&pal,&attr,&chr,&pct,&mask);
                log_printf("IKSGB VISUAL SGB_pal=%llu SGB_attr=%llu"
                           " CHR_TRN=%llu PCT_TRN=%llu MASK_EN=%llu"
                           " border=%s palette=%s\\n",
                           (unsigned long long)pal,
                           (unsigned long long)attr,
                           (unsigned long long)chr,
                           (unsigned long long)pct,
                           (unsigned long long)mask,
                           pct ? "ROM_CUSTOM" : "SGB_DEFAULT",
                           pal ? "ROM_CUSTOM" : "DEFAULT");
            }
            last_run_frames = run_frames;''',
        'once per second display')
    return s

if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: patch_sgb_prod_visual_frontend.py FRONTEND.c')
    path=Path(sys.argv[1]);path.write_text(patch(path.read_text()))
    print('PASS: production SGB border provenance and palette counters (no renderer changes)')
