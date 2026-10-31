#!/usr/bin/env python3
"""Activate historical mGBA 0.10.5 SGB hardware palette presets.
Do not touch authored PAL/ATTR/CHR/PCT packets or the validated #40 audio.
mGBA gb.colors=2 selects Super Game Boy hardware color presets by ROM title.
Games that upload their own SGB palettes still own the palette at runtime.
"""
from pathlib import Path
import sys

def patch(s):
    a='''        case RETRO_ENVIRONMENT_GET_VARIABLE:
            return false; /* core falls back to its safe defaults */'''
    b='''        case RETRO_ENVIRONMENT_GET_VARIABLE: {
            struct retro_variable *var=(struct retro_variable*)data;
            if (!var || !var->key) return false;
            /* mGBA 0.10.5 key/value semantics verified in libretro.c:
             * 2 means historical Super Game Boy preset database ONLY,
             * rather than GBC presets. ROM SGB PAL packets retain priority. */
            if (!strcmp(var->key,"mgba_gb_colors_preset")) {
                var->value="2"; return true;
            }
            if (!strcmp(var->key,"mgba_sgb_borders")) {
                var->value="ON"; return true;
            }
            return false; /* leave every other core option unchanged */
        }'''
    if s.count(a)!=1:raise ValueError(f"mGBA SGB palette option anchor count={s.count(a)}")
    s=s.replace(a,b,1)
    a='''    log_printf("video path  : RGB565 Mali; borde SGB atomico, fade visual desactivado\\n");'''
    b='''    log_printf("IKSGB palette policy: hardware Super Game Boy presets ONLY (mgba_gb_colors_preset=2), game-authored PAL overrides preserved\\n");
    log_printf("video path  : RGB565 Mali; borde SGB atomico, fade visual desactivado\\n");'''
    if s.count(a)!=1:raise ValueError("video policy anchor missing")
    s=s.replace(a,b,1)
    return s

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_sgb_prod_colors.py FRONTEND.c")
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
    print("PASS: Nintendo SGB title-based palette presets; ROM PAL/ATTR and border packets untouched")
