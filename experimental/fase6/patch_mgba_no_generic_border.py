#!/usr/bin/env python3
"""RC4: permanently eliminate mGBA's own decorative *default* SGB frame.
This is the actual origin of the unwanted intermediate border:
GBVideoReset copied hardcoded _defaultBorderChardata / Tilemap / Palette.
Only initial graphics are reset to transparent-black; genuine SGB CHR_TRN,
PCT_TRN, PAL, ATTR packets still write into exactly the same RAM/palette.
"""
import sys
from pathlib import Path
def patch(s):
    old='''\t\tmemcpy(video->renderer->sgbCharRam, _defaultBorderChardata, sizeof(_defaultBorderChardata));'''
    new='''\t\t/* IK PROD: never seed mGBA's stock decorative border.
\t\t * ROM CHR_TRN remains authoritative and fills these same banks. */
\t\tmemset(video->renderer->sgbCharRam, 0, SGB_SIZE_CHAR_RAM);'''
    if s.count(old)!=1:raise ValueError("original default CHR reset not found")
    s=s.replace(old,new,1)
    old='''\t\tmemcpy(video->renderer->sgbMapRam, _defaultBorderTilemap, sizeof(_defaultBorderTilemap));
\t\tint i;
\t\tfor (i = 0; i < 16; ++i) {
\t\t\tSTORE_16LE(_defaultBorderPalette[i], 0x800 + i * 2, video->renderer->sgbMapRam);
\t\t}'''
    new='''\t\t/* Deliberately blank only the reset *default* tilemap and
\t\t * border palettes. The ROM PCT_TRN owns all subsequent writes. */
\t\tmemset(video->renderer->sgbMapRam, 0, SGB_SIZE_MAP_RAM);'''
    if s.count(old)!=1:raise ValueError("original default PCT reset not found")
    s=s.replace(old,new,1)
    return s
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_mgba_no_generic_border.py src/gb/video.c")
    f=Path(sys.argv[1]); f.write_text(patch(f.read_text()))
    print("PASS: mGBA generic border tiles,map,palette removed at source; custom SGB transfers untouched")
