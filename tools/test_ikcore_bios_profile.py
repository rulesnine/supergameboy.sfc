#!/usr/bin/env python3
"""Static integration regression checks for the passive boot profiler.

A real ARM cross-compile and the full existing suspend/reset/SRAM synthetic
smoke suite run separately in the GitHub Actions build.
"""
from pathlib import Path
import subprocess
import sys
import tempfile

p=Path(sys.argv[1]); c=p.read_text("utf-8")
checks=[
  "BIOS PROFILE HANDOFF",
  "BIOS PROFILE START",
  "BIOS PROFILE : switch=%s",
  "BIOS COST",
  "BIOS AUDIO",
  "DIRECT PROFILE:",
  "DIRECT COST",
  "DIRECT AUDIO",
  "ik_suspend_maybe_restore();",
  "ik_sram_flush(0);",
  "if (game_loaded) ik_suspend_save();",
  "if (game_loaded) ik_sram_flush(1);",
  "while (!g_shutdown_requested && !g_swap_failed && !ik_exit_signal)",
  "IKCORE PERF2 switch: direct GB/SGB",
]
for check in checks:
    if check not in c: raise SystemExit("missing profiler invariant: "+check)
core_start=c.index("        core_retro_run();\n",c.index("while (!g_shutdown_requested"))
resume=c.index("        ik_suspend_maybe_restore();",core_start)
auto=c.index("        ik_sram_flush(0);",resume)
end=c.index("        work_end = now_s();",auto)
if not core_start<resume<auto<end:
    raise SystemExit("existing frame hooks changed order")
save=c.index("    if (game_loaded) ik_suspend_save();")
sram=c.index("    if (game_loaded) ik_sram_flush(1);",save)
unload=c.index("    if (game_loaded && core_retro_unload_game)",sram)
if not save<sram<unload:
    raise SystemExit("existing cleanup state and SRAM sequence changed")
assert c.count("IKCORE PERF2 switch: direct GB/SGB")==1
assert "ikprof_direct=1;" in c
# Exercise the EXACT assembled C core_log function, not a Python re-write.
# Snes9x wraps most log messages in "%s"; the original profiler inspected
# fmt itself and therefore never detected the phase transition.
b=c.index("static void core_log(enum retro_log_level level, const char *fmt, ...)")
e=c.index("\nstatic int get_fb_size(",b)
log_function=c[b:e]
assert "vsnprintf(ikprof_msg, sizeof ikprof_msg, fmt, ikprof_args)" in log_function
mock = r'''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <assert.h>
enum retro_log_level { RETRO_LOG_DEBUG, RETRO_LOG_INFO, RETRO_LOG_WARN, RETRO_LOG_ERROR };
static int ikprof_in_run=1,ikprof_direct=0;
static double ikprof_start_wall=1.0,ikprof_switch_wall=0.0;
static double ikprof_bios_video_at_switch=0.0;
static unsigned long ikprof_bios_late_at_switch=0;
static unsigned long ikprof_bios_recover_at_switch=0;
static unsigned long ikprof_bios_drop_at_switch=0;
static double g_video_seconds=2.25;
static unsigned long g_late_frames=6;
static unsigned long g_audio_recoveries=7;
static unsigned long g_audio_frames_dropped=8;
static unsigned long g_video_frames=1120;
static FILE *g_log = NULL;
static double now_s(void) { return 29.5; }
static void log_printf(const char *fmt,...) {
    va_list ap; va_start(ap,fmt); vfprintf(stdout,fmt,ap); va_end(ap);
}
'''
main = r'''
int main(void) {
    core_log(RETRO_LOG_INFO,"%s","Background boot event");
    assert(!ikprof_direct);
    core_log(RETRO_LOG_INFO,"%s",
             "IKCORE PERF2 switch: direct GB/SGB + live SNES SPC/DSP.");
    assert(ikprof_direct);
    assert(ikprof_switch_wall==29.5);
    assert(ikprof_bios_video_at_switch==2.25);
    assert(ikprof_bios_late_at_switch==6);
    assert(ikprof_bios_recover_at_switch==7);
    assert(ikprof_bios_drop_at_switch==8);
    puts("BIOS HANDOFF %s WRAPPER: PASS");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="ikcore-profiler-fmt-") as d:
    src=Path(d)/"profiler_fmt.c"
    exe=Path(d)/"profiler_fmt"
    src.write_text(mock + "\n" + log_function + "\n" + main,encoding="utf-8")
    subprocess.run(["gcc","-std=gnu11","-O2","-Wall","-Wextra",
                    "-Werror",str(src),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print("IKCORE BIOS PROFILE: PASS (formatted handoff, time accounting, state/SRAM and reset order)")
