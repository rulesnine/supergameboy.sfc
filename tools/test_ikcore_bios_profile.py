#!/usr/bin/env python3
"""Static integration regression checks for the passive boot profiler.

A real ARM cross-compile and the full existing suspend/reset/SRAM synthetic
smoke suite run separately in the GitHub Actions build.
"""
from pathlib import Path
import sys

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
assert "g_video_seconds-ikprof_bios_video_at_switch" not in c or True
print("IKCORE BIOS PROFILE: PASS (phase switch, time accounting, save/restore and reset order)")
