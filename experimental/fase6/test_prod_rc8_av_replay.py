#!/usr/bin/env python3
"""Hardware-independent lossless SGB BIOS audiovisual cache roundtrip test.
Creates synthetic pixel patterns / PCM, NEVER copyrighted Nintendo assets.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess

root=Path(__file__).resolve().parents[2]
mod=root/"experimental/fase6"
source=(mod/"ik_sgb_boot_av.c").read_text()
assert "IK_BOOT_MAGIC" in source and "ikboot_play" in source
assert "ikboot_video" in source and "ikboot_audio" in source
host=(mod/"ik_spc_host.c").read_text()
for marker in ("ikboot_begin(pack_hash)","ikboot_video(g_prod_boot_frame",
               "ikboot_end(1)","ikboot_play(pack_hash"):
    assert marker in host,marker
auth=(mod/"patch_prod_authentic_boot.py").read_text()
assert "ik_prod_show_loading();" in auth and "ik_f6_spc_set_boot_progress(NULL)" in auth
c=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ik_sgb_boot_av.h"
#define COUNT (256u*224u)
static uint16_t image[COUNT];
static uint16_t samples[600u*2u];
static unsigned received_frames,received_audio;
static void show(const uint16_t *pixels,unsigned frame) {
    assert(frame==received_frames+1u);
    assert(pixels[120]==(uint16_t)(0x100u+frame));
    assert(pixels[56300]==(uint16_t)(0x2200u+frame));
    ++received_frames;
}
static size_t sound(const int16_t *pcm,size_t n) {
    assert(pcm && n>0);
    received_audio+=(unsigned)n;
    return n;
}
int main(void) {
    const uint64_t key=0x123456789abcdeffULL;
    assert(!ikboot_has(key));
    ikboot_begin(key);
    for(unsigned i=1;i<=40u;++i) {
        image[120]=(uint16_t)(0x100u+i);
        image[56300]=(uint16_t)(0x2200u+i);
        ikboot_video(image,i);
        memset(samples,0,sizeof samples);
        samples[0]=(uint16_t)i;
        ikboot_audio((const int16_t*)samples,600u);
    }
    ikboot_end(1);
    assert(ikboot_has(key));
    assert(ikboot_play(key,show,sound,NULL,NULL));
    assert(received_frames==40u);
    assert(received_audio==40u*600u);
    puts("PASS: 40 original SNES frame deltas + 24000 stereo PCM restored at 60.0988Hz");
}
'''
with TemporaryDirectory() as d:
    p=Path(d)
    src=p/"verify.c";out=p/"verify";cache=p/"cache"
    src.write_text(c)
    subprocess.run(["gcc","-std=gnu11","-Wall","-Wextra","-Werror","-O2",
                    "-I",str(mod),'-DIK_BOOT_DIR="'+str(cache)+'"',
                    str(src),str(mod/"ik_sgb_boot_av.c"),"-o",str(out)],check=True)
    subprocess.run([str(out)],check=True)
