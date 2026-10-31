#!/usr/bin/env python3
"""Production-only introspection: sample genuine stock SGB BIOS border
BEFORE a game-owned PCT_TRN is committed. Not part of #40.
"""
from pathlib import Path
import sys
def patch(s):
    a='''/* Ik Core production: game-authored SGB PCT map completion counter. */
extern "C" __attribute__((visibility("default")))
unsigned ikcore_spc_bios_border_pct_count(void) {
    return SGB::Instance().BorderPctCount();
}
extern "C" __attribute__((visibility("default")))
int ikcore_spc_bios_gb_released(void) {
    return S9xSGBBIOSGBIsReleased() ? 1 : 0;
}
'''
    if "ikcore_spc_bios_border_pct_count" in s:raise ValueError("already patched")
    return s+"\n"+a
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_snes9x_original_border.py Snes9x/sgb/sgb.cpp")
    p=Path(sys.argv[1]);p.write_text(patch(p.read_text()))
    print("PASS: original BIOS frame selection aware of actual PCT_TRN commits")
