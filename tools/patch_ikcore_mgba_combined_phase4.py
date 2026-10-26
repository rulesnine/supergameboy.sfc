#!/usr/bin/env python3
"""Join Ik Core #43 SuperSnes9x and pinned mGBA into ONE libretro .so.

Run AFTER:
    tools/apply_sgbpack.py
    tools/fix_sgb_lcd_palette_transfers.py
    tools/optimize_sgb_compositor.py

This patch DOES NOT route the live frame loop to mGBA. Existing BIOS startup,
real SNES SPC audio, rendering and gameplay remain untouched. The combined
library now includes mGBA GB-only and an opt-in integration API.
Build is not a tested, installable HMOD.
"""
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1]) if len(sys.argv)>1 else Path(".")
snes = root / "supersnes9x"
core = snes / "libretro"
project = Path(__file__).resolve().parent.parent
if not (core / "Makefile").exists() or not (core / "libretro.cpp").exists():
    raise SystemExit("Expected supersnes9x/libretro working tree at " + str(root))

for name in ["ikcore_mgba_gb_host.h", "ikcore_sgb_audio_fifo.h"]:
    shutil.copyfile(project / "native_mgba" / name, core / name)
shutil.copyfile(project / "native_mgba" / "ikcore_mgba_combined_phase4.cpp",
                core / "ikcore_mgba_combined_phase4.cpp")

mk=core/"Makefile"
text=mk.read_text(encoding="utf-8")
old="OBJECTS := $(SOURCES_CXX:.cpp=.o) $(SOURCES_C:.c=.o)"
new=old+"""
# IKCORE_MGBA_COMBINED_PHASE4: part of the SAME Snes9x libretro ELF.
# mGBA host and the SPC transport object archives are built separately
# with the exact upstream mGBA CMake ABI definitions, then linked in LIBS.
OBJECTS += ikcore_mgba_combined_phase4.o
"""
assert text.count(old)==1, "Unexpected Makefile OBJECTS ABI"
assert "IKCORE_MGBA_COMBINED_PHASE4" not in text
mk.write_text(text.replace(old,new,1),encoding="utf-8")

p=core/"libretro.cpp"
text=p.read_text(encoding="utf-8")
head='''#include "sgb/sgb.h"'''
assert text.count(head)==1, "sgb/sgb.h include changed"
newhead=head+'''
#ifdef IKCORE_MGBA_COMBINED_LINK
// Linked against mGBA's GB-only static library, not a second SGB process.
extern "C" int  ikcore_mgba_phase4_link_probe(void);
extern "C" void ikcore_mgba_phase4_stop(void);
#endif'''
text=text.replace(head,newhead,1)
start="void retro_init(void)\n{"
assert text.count(start)==1, "retro_init signature changed"
newstart=start+'''
#ifdef IKCORE_MGBA_COMBINED_LINK
    // ABI/symbol probe only: does NOT run mGBA nor switch the verified
    // SuperSnes9x boot, rendering or audio code.
    if (ikcore_mgba_phase4_link_probe() != 0)
        fprintf(stderr, "IKCORE PHASE4 LINK/ABI PROBE FAILED\\n");
    else
        fprintf(stderr, "IKCORE PHASE4 COMBINED LINK OK: GB engine dormant\\n");
#endif'''
text=text.replace(start,newstart,1)
end="void retro_deinit()\n{"
assert text.count(end)==1, "retro_deinit signature changed"
newend=end+'''
#ifdef IKCORE_MGBA_COMBINED_LINK
    // When future opt-in runner starts, close its ROM/memory before unloading
    // its static mGBA object code. Never alter the #43 SGB singleton.
    ikcore_mgba_phase4_stop();
#endif'''
text=text.replace(end,newend,1)
p.write_text(text,encoding="utf-8")

# Preserve the optional phase4 ABI under Snes9x's --version-script=link.T
# and LTO -fwhole-program. These are the only extra public symbols; other
# mGBA/Snes9x internals stay hidden as in the verified #43 core.
version_script=core/"link.T"
version=version_script.read_text(encoding="utf-8")
expected="   global: retro_*;"
assert version.count(expected)==1
version=version.replace(expected,
    "   global: retro_*; ikcore_mgba_phase4_*;",1)
version_script.write_text(version,encoding="utf-8")
print("IKCORE_PHASE4 exported optional host bridge ABI via version script")
print("IKCORE_PHASE4_COMBINED patched Makefile, libretro init/deinit, mGBA symbols")
