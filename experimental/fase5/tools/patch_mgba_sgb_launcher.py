#!/usr/bin/env python3
"""Isolate physical SGB preview from the audio-only Fase5 mGBA / stable Ik Core.
Apply to the *generated* frontend after ALSA resampler patch.
"""
import sys
from pathlib import Path
def once(s,a,b,label):
    if s.count(a)!=1: raise ValueError(f"{label}: expected one anchor, got {s.count(a)}")
    return s.replace(a,b,1)
def patch(s):
    s=once(s,'#define IKCORE_CORE_PATH "/usr/lib/ikcore-fase5/mgba_libretro.so"',
        '#define IKCORE_CORE_PATH "/usr/lib/ikcore-fase5-sgb/mgba_libretro.so"','core path')
    s=once(s,'#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-fase5-mgba-__IKCORE_RUN_NUMBER__.log"',
        '#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-fase5-sgb-__IKCORE_RUN_NUMBER__.log"','log path')
    s=once(s,'static void (*ikcore_fase5_stats)(uint64_t *,uint64_t *,uint64_t *,uint64_t *);',
        'static void (*ikcore_fase5_stats)(uint64_t *,uint64_t *,uint64_t *,uint64_t *);\n'
        'static void (*ikcore_fase5_sgb_status)(unsigned *,unsigned *,unsigned *,unsigned *,unsigned *);',
        'SGB reporter signature')
    s=once(s,'if (!ikcore_fase5_stats) log_printf("WARN: SGB telemetry not present\\n");',
        'if (!ikcore_fase5_stats) log_printf("WARN: SGB telemetry not present\\n");\n'
        '    *(void **)(&ikcore_fase5_sgb_status) = dlsym(g_libcore, "ikcore_fase5_sgb_status");\n'
        '    if (!ikcore_fase5_sgb_status) log_printf("WARN: SGB mode status not present\\n");',
        'SGB reporter attach')
    s=once(s,'    core_retro_get_system_av_info(&avinfo);\n',
        '    core_retro_get_system_av_info(&avinfo);\n'
        '    if (ikcore_fase5_sgb_status) {\n'
        '        unsigned model=0,border=0,romsgb=0,w=0,h=0;\n'
        '        ikcore_fase5_sgb_status(&model,&border,&romsgb,&w,&h);\n'
        '        log_printf("IKSGB model=%u SGB=%u border=%u rom_sgb=%u geometry=%ux%u\\n",\n'
        '                   model, (model & 0x20u) ? 1u : 0u, border, romsgb, w, h);\n'
        '    }\n',
        'SGB on-load status')
    s=once(s,'log_printf("IK CORE FASE 5 mGBA ARMv7 BASELINE: NOT HYBRID, NO SNES SOUND\\n");',
        'log_printf("IK CORE FASE5 SGB PREVIEW - mGBA + automatic SGB border, SNES SPC not connected\\n");',
        'title')
    return s
if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit('Usage: patch_mgba_sgb_launcher.py GENERATED_FRONTEND.c')
    f=Path(sys.argv[1]); f.write_text(patch(f.read_text()))
    print('PASS: independent SGB preview executable and mode diagnostic')
