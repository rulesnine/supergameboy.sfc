#!/usr/bin/env python3
"""RC9: verify source-level GB handoff and synthetic gating without any ROM."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
root=Path(__file__).resolve().parents[2]
mod=root/"experimental/fase6"
host=(mod/"ik_spc_host.c").read_text()
snes=(mod/"patch_snes9x_spc_exports.py").read_text()
av=(mod/"ik_sgb_boot_av.c").read_text()
launcher=(mod/"ikcore-rc9-launcher.sh").read_text()
for token in (
  'SYM(g_prod_cart_started,"ikcore_spc_bios_cart_started")',
  "if(!ik_prod_intro_allowed())return;",
  "if(!ik_prod_intro_allowed())return frames;",
  "ik_sgb_intro_note_video(&g_prod_intro_gate)",
  'IKSPC BOOT CUT: intro_frames=',
):
    assert token in host,token
assert "S9xSGBBootHandoffCaptured() ? 1 : 0" in snes
assert "IKAV0002" in av and "bootav-rc9" in av
assert "h->version!=2u" in av and "h.version=2u" in av
assert "ikcore-sgb-rc9" in launcher and "ik_stop_child" in launcher
assert "ik_prod_cache_save(h,pack_hash" in host # SNES/SPC final state untouched
assert "ik_f6_spc_stop" in host
subprocess.run(["sh","-n",str(mod/"ikcore-rc9-launcher.sh")],check=True)
test=r'''
#include <assert.h>
#include <stdio.h>
#include "ik_sgb_intro_gate.h"
int main(void) {
  IkSgbIntroGate g={0};
  for(unsigned f=1;f<=80;f++) {
    assert(ik_sgb_intro_allow(&g,0,f));
    ik_sgb_intro_note_video(&g);
    ik_sgb_intro_note_audio(&g);
  }
  /* This is the real GB boot-ROM to cart-code handoff, not a magic frame. */
  assert(!ik_sgb_intro_allow(&g,1,81));
  assert(g.cart_started && g.cut_boot_frame==81 && g.intro_video_frames==80);
  /* Snes9x continues bootstrap/SPC until frame 1217, but MUST NOT expose
   * cartridge video/audio: mGBA is the sole visible GB cart runtime. */
  for(unsigned f=82;f<=1217;f++) {
    assert(!ik_sgb_intro_allow(&g,0,f));
    assert(!ik_sgb_intro_allow(&g,1,f));
  }
  assert(g.cut_boot_frame==81 && g.intro_audio_callbacks==80);
  puts("PASS: SGB-only intro ends at GB cartridge handoff; no duplicate ROM boot");
  return 0;
}
'''
with TemporaryDirectory() as td:
    d=Path(td);c=d/"gate.c";exe=d/"gate"
    c.write_text(test)
    subprocess.run(["gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(mod),str(c),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print("PASS: RC9 split cache v2 and clean RESET launcher regressions")
