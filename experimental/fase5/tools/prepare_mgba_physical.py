#!/usr/bin/env python3
"""Create isolated mGBA ARMv7 frontend from Ik Core N2; never rewrite stable sources."""
import sys
from pathlib import Path

def replace_one(s, before, after, name):
    n = s.count(before)
    if n != 1:
        raise ValueError(f"{name}: expected one anchor, found {n}")
    return s.replace(before, after, 1)

def patch(s):
    changes = [
        ('#define IKCORE_CORE_PATH "/usr/lib/ikcore/ikcore_sgbpack_libretro.so"',
         '#define IKCORE_CORE_PATH "/usr/lib/ikcore-fase5/mgba_libretro.so"', 'libretro path'),
        ('#define IKCORE_DEFAULT_PACK IKCORE_STATE_DIR "/KOF96_SGBPACK_v1_REUPLOAD.sfc"',
         '#define IKCORE_DEFAULT_PACK "/ROM_NOT_PROVIDED.gb"', 'default ROM'),
        ('#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-sfx-only-__IKCORE_RUN_NUMBER__.log"',
         '#define IKCORE_LOG_PATH IKCORE_STATE_DIR "/ikcore-fase5-mgba-__IKCORE_RUN_NUMBER__.log"', 'log'),
        ('return strcasecmp(dot, ".sfc") == 0 ||\n           strcasecmp(dot, ".smc") == 0;',
         'return strcasecmp(dot, ".gb") == 0 ||\n           strcasecmp(dot, ".gbc") == 0;', 'extensions'),
        ('log_printf("Ik Core SGB SFX ONLY build __IKCORE_RUN_NUMBER__ (base #117) - parallel SNES audio\\n");',
         'log_printf("IK CORE FASE 5 mGBA ARMv7 BASELINE: NOT HYBRID, NO SNES SOUND\\n");', 'title'),
        ('log_printf("core mode   : BIOS boot -> SGB directo + SPC/DSP SNES retenido + borde atomico\\n");',
         'log_printf("core mode   : mGBA 0.10.5 GB libretro; no SNES SPC/DSP\\n");', 'core mode'),
        ('log_printf("audio path  : GB APU PCM rate-lock 32040 Hz + SNES SPC/DSP paralelo, ring 8192/prefill 1024\\n");',
         'log_printf("audio path  : GB APU only; SNES SOUND not available in this baseline\\n");', 'audio label'),
        ('case RETRO_ENVIRONMENT_GET_VARIABLE:\n            return false; /* core falls back to its safe defaults */',
         'case RETRO_ENVIRONMENT_GET_VARIABLE: {\n'
         '            struct retro_variable *v = (struct retro_variable *)data;\n'
         '            if (!strcmp(v->key, "mgba_gb_model")) { v->value = "Super Game Boy"; return true; }\n'
         '            if (!strcmp(v->key, "mgba_sgb_borders")) { v->value = "ON"; return true; }\n'
         '            if (!strcmp(v->key, "mgba_gb_colors_preset")) { v->value = "2"; return true; }\n'
         '            if (!strcmp(v->key, "mgba_use_bios")) { v->value = "OFF"; return true; }\n'
         '            return false;\n'
         '        }', 'sgb options'),
        ('static void (*core_retro_set_controller_port_device)(unsigned,unsigned);',
         'static void (*core_retro_set_controller_port_device)(unsigned,unsigned);\nstatic void (*ikcore_fase5_stats)(uint64_t *,uint64_t *,uint64_t *,uint64_t *);', 'stats declaration'),
        ('if (load_core() != 0) goto cleanup;',
         'if (load_core() != 0) goto cleanup;\n    *(void **)(&ikcore_fase5_stats) = dlsym(g_libcore, "ikcore_fase5_stats");\n    if (!ikcore_fase5_stats) log_printf("WARN: SGB telemetry not present\\n");', 'stats attach'),
        ('            /* Passive one-second audio meter: compare production with ALSA\'s',
         '            if (ikcore_fase5_stats) {\n                uint64_t pkts=0,sound=0,trns=0,cycles=0;\n                ikcore_fase5_stats(&pkts,&sound,&trns,&cycles);\n                log_printf("IKMGBA SGB packets=%llu SOUND=%llu TRN=%llu cycles=%llu\\n",\n                   (unsigned long long)pkts,(unsigned long long)sound,\n                   (unsigned long long)trns,(unsigned long long)cycles);\n            }\n            /* Passive one-second audio meter: compare production with ALSA\'s', 'stats report'),
    ]
    for a,b,name in changes:
        s = replace_one(s,a,b,name)
    return s

if __name__ == '__main__':
    if len(sys.argv) != 3: raise SystemExit("Usage: prepare_mgba_physical.py SRC OUT")
    out = patch(Path(sys.argv[1]).read_text())
    Path(sys.argv[2]).write_text(out)
    print("PASS: dedicated mGBA EGL frontend generated; stable Ik Core untouched")
