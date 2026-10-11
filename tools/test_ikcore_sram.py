#!/usr/bin/env python3
"""Native host smoke test of the exact standalone SRAM C helper.

Extract the real helper from the patched frontend; compile it with tiny libretro
memory stubs. Exercises creation, 5-second check, reload, per-CLV isolation, and
bad-size save protection without any copyrighted ROM or NES Mini.
"""
import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).read_text("utf-8")
start = source.index("static int ikcore_extract_clv_id(")
end = source.index("static char ikcore_resolved_pack[", start)
id_fn = source[start:end]
start = source.index("/* Dedicated native SRAM writer.")
# The reset signal helper is tested separately; the SRAM host smoke test
# only extracts its SRAM functions, not unrelated future frontend helpers.
signal_start = source.find("/* Clover may terminate", start)
end = (signal_start if signal_start >= 0
       else source.index("\nint main(int argc, char **argv)\n{", start))
sram_fn = source[start:end]

with tempfile.TemporaryDirectory(prefix="ikcore-sram-smoke-") as d:
    saves = pathlib.Path(d) / "saves"
    program = pathlib.Path(d) / "smoke.c"
    binary = pathlib.Path(d) / "smoke"
    pre = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <unistd.h>
#define RETRO_MEMORY_SAVE_RAM 0
#define IKCORE_SAVE_DIR "%%SAVES%%"

static unsigned char fake_ram[8192];
static double fake_time = 0.0;
static double now_s(void) { return fake_time; }
static void *fake_memory_data(unsigned t) { (void)t; return fake_ram; }
static size_t fake_memory_size(unsigned t) { (void)t; return sizeof fake_ram; }
static void *(*core_retro_get_memory_data)(unsigned) = fake_memory_data;
static size_t (*core_retro_get_memory_size)(unsigned) = fake_memory_size;
static void log_printf(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    vfprintf(stderr, fmt, args);
    va_end(args);
}
'''
    pre = pre.replace("%%SAVES%%", saves.as_posix())
    main = r'''
static int check(int cond, const char *msg) {
    if (!cond) { fprintf(stderr, "TEST FAILED: %s\n", msg); return 0; }
    return 1;
}
int main(void) {
    char *game_a[] = {"ikcore", "/var/lib/hakchi/games/.storage/CLV-U-BVEMA/Guerreras_magicas.sfc"};
    char *game_b[] = {"ikcore", "/var/lib/hakchi/games/.storage/CLV-U-CPTFJ/SGBPACK_KOF96.sfc"};
    unsigned char ch;
    FILE *f;
    memset(fake_ram, 0xff, sizeof fake_ram);
    ik_sram_initialize(2, game_a);
    if (!check(ik_sram_size == 8192 && !ik_sram_disabled, "initial save enabled")) return 1;
    fake_ram[1] = 0x3c;
    ik_sram_flush(0);
    if (!check(access(IKCORE_SAVE_DIR "/CLV-U-BVEMA.srm", F_OK) != 0,
               "no premature flash write")) return 1;
    fake_time = 5.1;
    ik_sram_flush(0);
    if (!check(access(IKCORE_SAVE_DIR "/CLV-U-BVEMA.srm", F_OK) == 0,
               "autosave after change")) return 1;
    ik_sram_finish();
    memset(fake_ram, 0xff, sizeof fake_ram);
    fake_time = 10.0;
    ik_sram_initialize(2, game_a);
    if (!check(fake_ram[1] == 0x3c, "restore battery SRAM")) return 1;
    ik_sram_flush(1);
    ik_sram_finish();

    memset(fake_ram, 0xff, sizeof fake_ram);
    fake_time = 15.0;
    ik_sram_initialize(2, game_b);
    if (!check(fake_ram[1] == 0xff, "other game starts independently")) return 1;
    fake_ram[1] = 0x42;
    ik_sram_flush(1);
    ik_sram_finish();

    f = fopen(IKCORE_SAVE_DIR "/CLV-U-BVEMA.srm", "rb");
    if (!f) return 1;
    if (fseek(f, 1, SEEK_SET)) return 1;
    ch = (unsigned char)fgetc(f);
    fclose(f);
    if (!check(ch == 0x3c, "other game's save unmodified")) return 1;

    f = fopen(IKCORE_SAVE_DIR "/CLV-U-CPTFJ.srm", "wb");
    if (!f) return 1;
    if (fwrite("BAD", 1, 3, f) != 3) return 1;
    fclose(f);

    memset(fake_ram, 0xff, sizeof fake_ram);
    fake_time = 20.0;
    ik_sram_initialize(2, game_b);
    if (!check(ik_sram_disabled, "corrupted save is protected")) return 1;
    fake_ram[1] = 0x80;
    ik_sram_flush(1);
    ik_sram_finish();
    {
        struct stat st;
        if (stat(IKCORE_SAVE_DIR "/CLV-U-CPTFJ.srm", &st) != 0) return 1;
        if (!check(st.st_size == 3, "corrupt save never overwritten")) return 1;
    }
    puts("IKCORE SRAM SMOKE: PASS (autosave, restore, separate games, corruption guard)");
    return 0;
}
'''
    program.write_text(pre + "\n" + id_fn + "\n" + sram_fn + "\n" + main, "utf-8")
    subprocess.run(["gcc", "-std=gnu11", "-O2", "-Wall", "-Wextra",
                    "-Werror", str(program), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
