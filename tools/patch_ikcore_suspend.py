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
# Declare frame-buffer ownership BEFORE video_cb uses it. Keep all expensive
# screenshot work off the normal frame path (copy only twice per second).
start_globals = body.index("static const void *ik_suspend_last_frame = NULL;")
end_globals = body.index("\nstatic void ik_susp_le32", start_globals)
frame_globals = body[start_globals:end_globals]
body = body[:start_globals] + body[end_globals:]
once("static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{\n",
     frame_globals + "\n"
     "static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch)\n{\n"
     "    if (data && ik_suspend_capture_enabled && width && height &&\n"
     "        width <= 512 && height <= 512 && now_s() >= ik_suspend_next_capture) {\n"
     "        size_t rowbytes = (size_t)width *\n"
     "                ((g_pixel_format == RETRO_PIXEL_FORMAT_XRGB8888) ? 4u : 2u);\n"
     "        size_t need = rowbytes * (size_t)height;\n"
     "        if (pitch >= rowbytes && pitch <= 8192 && need <= 512u*512u*4u) {\n"
     "            if (need > ik_suspend_framebuffer_capacity) {\n"
     "                uint8_t *new_buffer = (uint8_t *)realloc(ik_suspend_framebuffer, need);\n"
     "                if (new_buffer) {\n"
     "                    ik_suspend_framebuffer = new_buffer;\n"
     "                    ik_suspend_framebuffer_capacity = need;\n"
     "                }\n"
     "            }\n"
     "            if (ik_suspend_framebuffer_capacity >= need) {\n"
     "                unsigned yy;\n"
     "                for (yy = 0; yy < height; ++yy)\n"
     "                    memcpy(ik_suspend_framebuffer + (size_t)yy*rowbytes,\n"
     "                           (const uint8_t *)data + (size_t)yy*pitch, rowbytes);\n"
     "                ik_suspend_last_frame = ik_suspend_framebuffer;\n"
     "                ik_suspend_frame_width = width;\n"
     "                ik_suspend_frame_height = height;\n"
     "                ik_suspend_frame_pitch = rowbytes;\n"
     "                ik_suspend_capture_format = g_pixel_format;\n"
     "                ik_suspend_next_capture = now_s() + 0.5;\n"
     "            }\n"
     "        }\n"
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
