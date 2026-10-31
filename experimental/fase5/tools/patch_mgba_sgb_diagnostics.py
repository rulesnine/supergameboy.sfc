#!/usr/bin/env python3
"""Export machine/video SGB state from mGBA 0.10.5 for real ARMv7 diagnostics."""
import sys
from pathlib import Path
ANCHOR="void retro_unload_game(void) {"
REPLACEMENT='''/* Ik Core Fase 5 SGB diagnostics, ABI-local to experimental .so. */
void ikcore_fase5_sgb_status(unsigned *model, unsigned *border,
                            unsigned *rom_sgb, unsigned *width,
                            unsigned *height) {
    unsigned w=0,h=0, m=0,b=0,s=0;
#ifdef M_CORE_GB
    if (core && core->platform(core) == mPLATFORM_GB) {
        struct GB *gb = (struct GB*)core->board;
        if (gb) {
            m=(unsigned)gb->model;
            b=gb->video.sgbBorders ? 1u : 0u;
            if (gb->memory.rom)
                s=(GBValidModels(gb->memory.rom)&GB_MODEL_SGB) ? 1u : 0u;
            core->desiredVideoDimensions(core, &w, &h);
        }
    }
#endif
    if (model) *model=m;
    if (border) *border=b;
    if (rom_sgb) *rom_sgb=s;
    if (width) *width=w;
    if (height) *height=h;
}

''' + ANCHOR
def patch(s):
    if s.count(ANCHOR)!=1: raise ValueError("libretro.c reset hook not unique")
    out = s.replace(ANCHOR, REPLACEMENT, 1)
    load_anchor = "bool retro_load_game(const struct retro_game_info* game) {"
    if out.count(load_anchor) != 1:
        raise ValueError("libretro.c load hook not unique")
    out = out.replace(load_anchor,
                      "extern void ikcore_fase5_sgb_reset_packets(void);\n"
                      + load_anchor
                      + "\n    ikcore_fase5_sgb_reset_packets();", 1)
    return out
if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_mgba_sgb_diagnostics.py SRC_LIBRETRO_C")
    f=Path(sys.argv[1]); f.write_text(patch(f.read_text()))
    print("PASS: mGBA libretro SGB status exported")
