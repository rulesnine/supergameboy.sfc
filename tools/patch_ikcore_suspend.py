#!/usr/bin/env python3
"""Add Hakchi/Clover suspendpoint support to a COPY of Ik Core frontend.

Uses the pinned core's libretro snapshot exports and the exact Clover
--load-state-file, --save-on-quit, --save-screenshot-on-quit paths. No core or
SNES/SPC audio engine change, and no modification of #137 or validated #8.
"""
from pathlib import Path
import sys

project = Path(__file__).resolve().parents[1]
p = Path(sys.argv[1])
src = p.read_text("utf-8")
body = (project / "native_n2/ikcore_suspend.inc").read_text("utf-8")

def once(before, after):
    global src
    count = src.count(before)
    if count != 1:
        raise SystemExit(f"SUSPEND anchor count={count}: {before[:130]!r}")
    src = src.replace(before, after, 1)

once("static void (*core_retro_run)(void);\n",
     "static void (*core_retro_run)(void);\n"
     "static size_t (*core_retro_serialize_size)(void);\n"
     "static bool (*core_retro_serialize)(void *, size_t);\n"
     "static bool (*core_retro_unserialize)(const void *, size_t);\n")
once("    LOAD_CORE(retro_run);\n",
     "    LOAD_CORE(retro_run);\n"
     "    LOAD_CORE(retro_serialize_size);\n"
     "    LOAD_CORE(retro_serialize);\n"
     "    LOAD_CORE(retro_unserialize);\n")
once("static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{\n",
     "static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{\n"
     "    if (data && width && height) {\n"
     "        ik_suspend_last_frame = data;\n"
     "        ik_suspend_frame_width = width;\n"
     "        ik_suspend_frame_height = height;\n"
     "        ik_suspend_frame_pitch = pitch;\n"
     "    }\n")
once("int main(int argc, char **argv)\n{\n", body+"\nint main(int argc, char **argv)\n{\n")
once("    ik_sram_initialize(argc, argv);\n",
     "    ik_sram_initialize(argc, argv);\n"
     "    ik_suspend_initialize(argc, argv, pack_path);\n")
once("    if (game_loaded) ik_sram_flush(1);\n",
     "    if (game_loaded) ik_suspend_save();\n"
     "    if (game_loaded) ik_sram_flush(1);\n")
p.write_text(src, "utf-8")
print("IKCORE SUSPEND: state save/load + native Clover screenshot; #8 SRAM kept.")
