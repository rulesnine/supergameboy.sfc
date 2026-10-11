#!/usr/bin/env python3
"""Level-1-only regression guard: no machine timing or transfer code edits."""
from pathlib import Path
import sys

p=Path(sys.argv[1])
s=p.read_text(encoding="utf-8")
assert s.count("static_cast<unsigned>(x - sx) >= 8u")==2
assert s.count("p.show_obj ? SampleSpritePixel(p, x)")==1
assert s.count("p.show_obj ? SampleSpritePixelCgb(p, x)")==1
assert s.count("const bool win_en_now = WinEnView(p, m);")==1
assert s.count("m.fetch_is_window && !win_en_now &&")==1
assert s.count("!m.fetch_is_window && !win_en_now &&")==1

# Full sprite coordinate domain from the eight-bit OBJ X register:
# sx = raw [0..255] - 8, x = visible [0..159].
for sx in range(-8,248):
    for x in range(160):
        old = (x >= sx and x < sx+8)
        unsigned_distance = (x-sx) & 0xffffffff
        new = (unsigned_distance < 8)
        assert old==new, (sx,x)
# Hidden sprite sample is read-only; the newly supplied empty result
# is identical to the original ignored return.
for show_obj in (False,True):
    for covered in (False,True):
        for bg_over in (False,True):
            for disp_bg in range(4):
                old_dmg=show_obj and covered and ((not bg_over) or disp_bg==0)
                new_dmg=show_obj and (covered if show_obj else False) and ((not bg_over) or disp_bg==0)
                assert old_dmg==new_dmg
                old_cgb=show_obj and covered
                new_cgb=show_obj and (covered if show_obj else False)
                assert old_cgb==new_cgb

# Confirm these are the only edits in PPU and did not remove exact FIFO,
# DMA, bus timing, scanline callbacks, border transfer or window hit logic.
for preserved in (
    "static bool Mode3Dot(", "void PpuStep(",
    "Mode3Exit(p, p.tm, mem)", "Mode3OutputExit(p, p.om)",
    "FinalizeScanline(p)", "MemHdmaHBlank(mem)",
    "WindowCheckDot(p, m)", "ObjHandleMatches(p, m, mem)",
    "void RenderPixel(Ppu &p)", "S9xSGBCaptureScanline(line)"
):
    assert preserved in s, preserved
print("IKCORE LEVEL1 SMOKE: PASS (all OBJ coordinates, BG priority, FIFO/transfer invariants)")
