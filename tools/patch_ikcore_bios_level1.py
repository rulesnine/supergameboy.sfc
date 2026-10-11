#!/usr/bin/env python3
"""Ik Core LEVEL 1: semantics-preserving DMG/CGB pixel micro-optimizations.

Run AFTER apply_sgbpack.py, on the pinned checkout's COPY ONLY.
No skipped pixels, emulated cycles, SGB packet transfer, BIOS or SPC changes.

1. Sprite scan is read-only: do not evaluate it when the user has disabled
   OBJ display (p.show_obj=false). The result is already ignored in this case.
2. Collapse the two signed sprite-x bounds comparisons into one unsigned
   distance comparison, equivalent for x in [0,159] and sx in [-8,247].
"""
from pathlib import Path
import sys

p=Path(sys.argv[1]) if len(sys.argv)>1 else Path("supersnes9x/sgb/gb_ppu.cpp")
src=p.read_text(encoding="utf-8-sig")
original=src

def change(old,new,why):
    global src
    n=src.count(old)
    if n!=1:
        raise SystemExit(f"LEVEL1 refused {why}: expected 1 anchor, got {n}")
    src=src.replace(old,new,1)

change("""\t\tif (x < sx || x >= sx + 8) continue;""",
       """\t\t// Equivalent bounds test; keeps negative off-screen X correct.
\t\tif (static_cast<unsigned>(x - sx) >= 8u) continue;""",
       "DMG sprite overlap")

change("""\t\tif (x < sx || x >= sx + 8) continue;""",
       """\t\t// Same unsigned 8-pixel interval test for CGB sprites.
\t\tif (static_cast<unsigned>(x - sx) >= 8u) continue;""",
       "CGB sprite overlap")

change("""\tconst SpritePixelCgb sp = SampleSpritePixelCgb(p, x);
\tif (p.show_obj && sp.covered)
""",
       """\t// Sampling does not mutate the PPU. When OBJ output is hidden,
\t// the original call's value was unconditionally discarded.
\tconst SpritePixelCgb sp = p.show_obj ? SampleSpritePixelCgb(p, x)
\t                                  : SpritePixelCgb{ false, 0, 0, false, 0 };
\tif (p.show_obj && sp.covered)
""",
       "CGB hidden-OBJ scan")

change("""\tconst SpritePixel sp = SampleSpritePixel(p, x);
\tif (p.show_obj && sp.covered && (!sp.bg_over || disp_bg == 0))
""",
       """\t// Preserve exactly the old visible-sprite code and priority.
\t// Avoid only the read-only scan whose result would be ignored.
\tconst SpritePixel sp = p.show_obj ? SampleSpritePixel(p, x)
\t                               : SpritePixel{ false, 0, 0, false, false };
\tif (p.show_obj && sp.covered && (!sp.bg_over || disp_bg == 0))
""",
       "DMG hidden-OBJ scan")

assert src!=original
assert src.count("static_cast<unsigned>(x - sx) >= 8u")==2
p.write_text(src,encoding="utf-8")
print("IKCORE LEVEL1: redundant hidden-sprite scans removed in DMG/CGB; pixel/clock logic unchanged.")
