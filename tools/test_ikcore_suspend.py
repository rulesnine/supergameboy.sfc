#!/usr/bin/env python3
"""Test the exact new suspend C implementation (no real ROM required).

Tests Clover arg extraction, per-ROM isolation, snapshot+PNG, CRC validation,
and load through pinned libretro function signatures with a synthetic core.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import struct
import zlib

frontend = Path(sys.argv[1]).read_text(encoding="utf-8")
start = frontend.index("/*\n * Ik Core native-only Clover suspendpoint v1.")
end = frontend.index("\nint main(int argc, char **argv)\n{", start)
helper = frontend[start:end]
# The screenshot globals are declared before video_cb for native C linkage.
# Include those same definitions in the synthetic C test harness.
globals_start = frontend.index("static const void *ik_suspend_last_frame = NULL;")
globals_end = frontend.index("\nstatic void video_cb(", globals_start)
frame_globals = frontend[globals_start:globals_end]

for required in [
    "LOAD_CORE(retro_serialize_size)",
    "LOAD_CORE(retro_serialize)",
    "LOAD_CORE(retro_unserialize)",
    "ik_suspend_initialize(argc, argv, pack_path)",
    "ik_suspend_maybe_restore();",
    "ik_suspend_finish();",
    "if (game_loaded) ik_suspend_save();",
    "if (game_loaded) ik_sram_flush(1);",
]:
    assert required in frontend, f"missing main integration {required}"
assert (frontend.index("if (game_loaded) ik_suspend_save();")
        < frontend.index("if (game_loaded) ik_sram_flush(1);")
        < frontend.index("if (game_loaded && core_retro_unload_game)")), "save must precede unload"

start_id = frontend.index("static int ikcore_extract_clv_id(")
end_id = frontend.index("static char ikcore_resolved_pack[", start_id)
extract_id = frontend[start_id:end_id]

with tempfile.TemporaryDirectory(prefix="ikcore-suspend-smoke-") as tmp:
    base=Path(tmp)
    image=base/"game.sfc"
    image.write_bytes(b"FAKE GAME CONTENT" * 40 + b"SGBPACK1" + b"\0"*248)
    second=base/"changed.sfc"
    second.write_bytes(b"OTHER GAME CONTENT" * 40 + b"SGBPACK1" + b"\0"*248)
    state=base/"CLV-U-BVEMA"/"0.state"
    png=base/"CLV-U-BVEMA"/"0.state.png"
    tampered=base/"corrupt.state"
    code=r'''
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
enum { RETRO_PIXEL_FORMAT_0RGB1555=0,RETRO_PIXEL_FORMAT_XRGB8888=1,
       RETRO_PIXEL_FORMAT_RGB565=2 };
static int g_pixel_format=RETRO_PIXEL_FORMAT_RGB565;
static unsigned long g_video_frames=1;
static double now_s(void) { return 1.0; }
static uint8_t fake_state[128];
static int load_count=0;
static int fake_direct_mode=1;
static size_t fake_serialize_size(void) {
    return fake_direct_mode ? sizeof(fake_state) : 256u;
}
static void fake_set_sgb_header(void) {
    memcpy(fake_state,"SGB!",4);
    fake_state[4]=11;fake_state[5]=fake_state[6]=fake_state[7]=0;
    fake_state[8]=116;fake_state[9]=fake_state[10]=fake_state[11]=0;
}
static bool fake_serialize(void *data,size_t len) {
    if(len!=sizeof fake_state)return false;
    memcpy(data,fake_state,len);
    return true;
}
static bool fake_unserialize(const void *data,size_t len) {
    if(len!=sizeof fake_state)return false;
    memcpy(fake_state,data,len);
    load_count++;
    return true;
}
static size_t (*core_retro_serialize_size)(void)=fake_serialize_size;
static bool (*core_retro_serialize)(void *,size_t)=fake_serialize;
static bool (*core_retro_unserialize)(const void *,size_t)=fake_unserialize;
#define RETRO_MEMORY_SAVE_RAM 0
static unsigned char *ik_sram_shadow=NULL;
static size_t ik_sram_size=0;
static int ik_sram_disabled=0;
static void *fake_get_memory(unsigned type) { (void)type;return NULL; }
static size_t fake_get_size(unsigned type) { (void)type;return 0; }
static void *(*core_retro_get_memory_data)(unsigned)=fake_get_memory;
static size_t (*core_retro_get_memory_size)(unsigned)=fake_get_size;
static void log_printf(const char *fmt,...) {
    va_list ap;
    va_start(ap,fmt);
    vfprintf(stderr,fmt,ap);
    va_end(ap);
}
'''
    code+="\n"+extract_id+"\n"+frame_globals+"\n"+helper+"\n"
    code+=r'''
static int check(int b,const char *message) {
    if(!b){fprintf(stderr,"ASSERT: %s\n",message);return 0;}
    return 1;
}
int main(int argc,char **argv) {
    uint16_t pixels[4] = {0xf800,0x07e0,0x001f,0xffff};
    char *game_args[8], *load_args[8];
    size_t j;
    if(argc!=5)return 2;
    /* Exercise ownership flags in synthetic harness (callback is independent). */
    if(ik_suspend_framebuffer || ik_suspend_framebuffer_capacity ||
       ik_suspend_capture_enabled || ik_suspend_next_capture ||
       g_pixel_format != RETRO_PIXEL_FORMAT_RGB565) return 2;
    for(j=0;j<sizeof fake_state;j++)fake_state[j]=(uint8_t)(j ^ 0x5a);
    fake_set_sgb_header();
    ik_suspend_last_frame=pixels;
    ik_suspend_frame_width=2;
    ik_suspend_frame_height=2;
    ik_suspend_frame_pitch=4;
    game_args[0]="ikcore";
    game_args[1]="--save-on-quit";
    game_args[2]=argv[2];
    game_args[3]="--save-screenshot-on-quit";
    game_args[4]=argv[3];
    game_args[5]="--save-data-backing-file";
    game_args[6]="/var/lib/clover/profiles/0/CLV-U-BVEMA/save.sram";
    game_args[7]=NULL;

    ik_suspend_initialize(7,game_args,argv[1]);
    if(!check(ik_suspend_ready,"suspend initialized"))return 3;
    ik_suspend_save();
    if(!check(access(argv[2],F_OK)==0,"Clover state created") ||
       !check(access(argv[3],F_OK)==0,"Clover screenshot created"))return 4;

    ik_suspend_ready=0;
    memset(ik_suspend_output,0,sizeof ik_suspend_output);
    memset(ik_suspend_input,0,sizeof ik_suspend_input);
    memset(ik_suspend_png,0,sizeof ik_suspend_png);
    memset(ik_suspend_clv,0,sizeof ik_suspend_clv);
    ik_suspend_rom_hash=0;
    memset(fake_state,0,sizeof fake_state);
    load_args[0]="ikcore";
    load_args[1]="--load-state-file";
    load_args[2]=argv[2];
    load_args[3]="--save-on-quit";
    load_args[4]=argv[2];
    load_args[5]="--save-data-backing-file";
    load_args[6]="/var/lib/clover/profiles/0/CLV-U-BVEMA/save.sram";
    load_args[7]=NULL;
    fake_direct_mode=0; /* BIOS phase: the SGB direct state is not yet valid */
    ik_suspend_initialize(7,load_args,argv[1]);
    if(!check(load_count==0 && ik_suspend_pending,
              "valid state deferred until core switches from BIOS"))return 5;
    ik_suspend_probe_at=0.0;
    ik_suspend_maybe_restore();
    if(!check(load_count==0 && ik_suspend_pending,
              "SNES BIOS serializer never receives GB state"))return 5;
    fake_direct_mode=1;
    fake_set_sgb_header(); /* same core now switched into direct SGB */
    ik_suspend_probe_at=0.0;
    ik_suspend_maybe_restore();
    if(!check(load_count==1 && !ik_suspend_pending,
              "state restored only after SGB mode switch") ||
       !check(fake_state[17]==(uint8_t)(17 ^ 0x5a),"serialized bytes restored"))
        return 5;
    ik_suspend_finish();
    /* A different binary assigned to the same CLV game must NOT load it. */
    memset(fake_state,0,sizeof fake_state);
    load_count=0;
    ik_suspend_ready=0;
    memset(ik_suspend_clv,0,sizeof ik_suspend_clv);
    ik_suspend_initialize(7,load_args,argv[4]);
    if(!check(load_count==0 && !ik_suspend_pending,"different ROM rejected") ||
       !check(fake_state[17]==0,"unchanged fresh state"))return 6;
    puts("SUSPEND C SMOKE: PASS (BIOS wait, SGB resume, ID+ROM validation, PNG)");
    return 0;
}
'''
    s=base/"suspend_smoke.c"
    s.write_text(code,encoding="utf-8")
    exe=base/"suspend_smoke"
    subprocess.run(["gcc","-std=gnu11","-O2","-Wall","-Wextra",
                    "-Werror",str(s),"-o",str(exe)],check=True)
    subprocess.run([str(exe),str(image),str(state),str(png),str(second)],check=True)

    result=state.read_bytes()
    assert len(result)==40+128
    assert result[:8]==b"IKCSUSP1"
    assert struct.unpack_from("<I",result,8)[0]==128
    assert result[20:32]==b"CLV-U-BVEMA\0"
    assert struct.unpack_from("<I",result,16)[0]==zlib.crc32(result[40:])
    pngdata=png.read_bytes()
    assert pngdata[:8]==b"\x89PNG\r\n\x1a\n"
    pos=8
    idat=b""
    while pos<len(pngdata):
        length=struct.unpack_from(">I",pngdata,pos)[0]
        typ=pngdata[pos+4:pos+8]
        payload=pngdata[pos+8:pos+8+length]
        crc=struct.unpack_from(">I",pngdata,pos+8+length)[0]
        assert zlib.crc32(typ+payload)==crc, f"PNG CRC {typ!r}"
        if typ==b"IDAT":idat+=payload
        pos+=12+length
        if typ==b"IEND":break
    assert zlib.decompress(idat)==(
        b"\x00\xff\x00\x00\x00\xff\x00" +
        b"\x00\x00\x00\xff\xff\xff\xff"
    ),"PNG RGB565 pixel conversion"
    assert pos==len(pngdata)

    bad=bytearray(result)
    bad[-1]^=1
    tampered.write_bytes(bad)
    assert zlib.crc32(bad[40:]) != struct.unpack_from("<I",bad,16)[0]
    print("SUSPEND FORMAT/PNG: PASS (CRC32, zlib image, strict ROM identity)")
