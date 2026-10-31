#!/usr/bin/env python3
"""RC10 regression: do not replay the second Nintendo GB logo or cut SGB
firmware's original border transitions. Test source hooks and synthetic pixels.
No copyrighted games/firmware/BIOS used.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
base=Path(__file__).resolve().parents[2]/"experimental/fase6"
host=(base/"ik_spc_host.c").read_text()
av=(base/"ik_sgb_boot_av.c").read_text()
mgba=(Path(__file__).resolve().parents[2]/
      "experimental/fase5/tools/prepare_mgba_physical.py").read_text()
assert "IK_SGB_PANE_Y 39u" in (base/"ik_sgb_boot_pane.h").read_text()
assert "ik_sgb_pane_filter(&g_rc10_pane,g_prod_boot_frame" in host
assert "ikboot_video(g_prod_boot_frame,g_prod_boot_frames)" in host
assert "ik_prod_cache_save(h,pack_hash" in host
assert "IKSGB RC10 PANEGATE:" in host
assert "ik_f6_spc_set_boot_video" in host
assert "IKAV0010" in av and "bootav-rc10" in av
assert "h->version!=10u" in av and "h.version=10u" in av
assert '"mgba_use_bios")) { v->value = "OFF"' in mgba
assert "ikboot_audio" in host and "g_boot_pcm_frames" in host

program=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "ik_sgb_boot_pane.h"
static uint16_t f[256u*224u];
int main(void) {
    IkSgbBootPane g={0};
    for(unsigned k=1;k<=80u;++k) {
        for(unsigned i=0;i<256u*224u;++i) f[i]=(uint16_t)(k+1);
        for(unsigned y=39u;y<183u;++y)
            for(unsigned x=48u;x<208u;++x) f[y*256u+x]=(uint16_t)(0x2000u+k);
        ik_sgb_pane_filter(&g,f,0,k);
        assert(f[39u*256u+48u]==(uint16_t)(0x2000u+k));
    }
    for(unsigned k=81u;k<=1217u;++k) {
        for(unsigned i=0;i<256u*224u;++i) f[i]=(uint16_t)(k+1);
        for(unsigned y=39u;y<183u;++y)
            for(unsigned x=48u;x<208u;++x) f[y*256u+x]=(uint16_t)(0x3000u+k);
        /* SNES owns real border/SGB splash during GB initialization, but
         * the second GB Nintendo logo must NEVER leak into the pane. */
        ik_sgb_pane_filter(&g,f,k>90u?0:1,k);
        assert(f[40u*256u+50u]==0x2000u+80u);
        assert(f[150u*256u+175u]==0x2000u+80u);
        assert(f[1u*256u+1u]==(uint16_t)(k+1u));
        assert(f[200u*256u+235u]==(uint16_t)(k+1u));
    }
    assert(g.has_saved && g.gb_released && g.release_frame==81);
    assert(g.pre_release_frames==80u && g.held_frames==1137u);
    puts("PASS: second internal GB logo masked; authentic SNES border transitions preserved 1217 frames");
}
'''
with TemporaryDirectory() as td:
    p=Path(td);file=p/"test.c";exe=p/"test"
    file.write_text(program)
    subprocess.run(["gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(base),str(file),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print("PASS: Ik Core RC10 retains mGBA game, audio, RESET and separate cache v10 hooks")
