#!/usr/bin/env python3
"""Passive BIOS vs direct runtime profiler for Ik Core Standalone.

Only patches frontend timing counters in the already assembled #25 frontend.
No SNES CPU/PPU/audio, clock, libretro timing, gameplay or save-state changes.
Single handoff event uses existing exact PERF2 log, which appears once when
the original core switches to direct SGB + retained SPC/DSP audio.
"""
from pathlib import Path
import sys

p=Path(sys.argv[1]); src=p.read_text("utf-8")
def once(old,new):
    global src
    n=src.count(old)
    if n!=1:
        raise SystemExit(f"PROFILE patch anchor count {n}: {old[:110]!r}")
    src=src.replace(old,new,1)

variables = r'''
/* Passive frontend-only diagnostic: counts two existing execution phases.
 * Frame work time includes all of core_retro_run, incl. its callbacks.
 * Video callback time is separately measured by the #137 baseline.
 * 'nonvideo' below is a residual, NOT a pure CPU-only profiler.
 */
static int ikprof_in_run=0,ikprof_direct=0;
static double ikprof_start_wall=0.0,ikprof_switch_wall=0.0;
static double ikprof_bios_work=0.0,ikprof_direct_work=0.0;
static double ikprof_bios_video_at_switch=0.0;
static unsigned long ikprof_bios_frames=0,ikprof_direct_frames=0;
static unsigned long ikprof_bios_over_16=0,ikprof_bios_over_33=0;
static unsigned long ikprof_direct_over_16=0,ikprof_direct_over_33=0;
static unsigned long ikprof_bios_late_at_switch=0;
static unsigned long ikprof_bios_recover_at_switch=0;
static unsigned long ikprof_bios_drop_at_switch=0;
'''
once('static double g_work_seconds = 0.0;\n',
     'static double g_work_seconds = 0.0;\n'+variables)

once('static void core_log(enum retro_log_level level, const char *fmt, ...)\n{\n    const char *tag = "INFO";\n    va_list ap;\n',
'''static void core_log(enum retro_log_level level, const char *fmt, ...)
{
    const char *tag = "INFO";
    va_list ap;
    /* Core often emits log_cb(RETRO_LOG_INFO, "%s", message).
     * Checking the literal format string misses the handoff even though
     * the expanded message is visible in the normal core[INFO] log.
     * Render into a bounded stack buffer only for rare log messages.
     * Preserve the ORIGINAL core log and all real-time frame behavior.
     */
    if (ikprof_in_run && !ikprof_direct && fmt) {
        char ikprof_msg[512];
        va_list ikprof_args;
        va_start(ikprof_args, fmt);
        vsnprintf(ikprof_msg, sizeof ikprof_msg, fmt, ikprof_args);
        va_end(ikprof_args);
        if (strstr(ikprof_msg, "IKCORE PERF2 switch: direct GB/SGB") != NULL) {
            ikprof_direct=1;
            ikprof_switch_wall=now_s();
            ikprof_bios_video_at_switch=g_video_seconds;
            ikprof_bios_late_at_switch=g_late_frames;
            ikprof_bios_recover_at_switch=g_audio_recoveries;
            ikprof_bios_drop_at_switch=g_audio_frames_dropped;
            log_printf("BIOS PROFILE HANDOFF : elapsed=%.3f s, render_frames=%lu\\n",
                       ikprof_switch_wall-ikprof_start_wall,g_video_frames);
        }
    }
''')

once('    start = last = now_s();\n    deadline = start;',
     '    start = last = now_s();\n'
     '    ikprof_in_run=1;\n'
     '    ikprof_start_wall=start;\n'
     '    log_printf("BIOS PROFILE START : monotonic=%.3f\\n",start);\n'
     '    deadline = start;')

once('        core_retro_run();\n        ik_suspend_maybe_restore();\n        ik_sram_flush(0);\n        work_end = now_s();',
'''        core_retro_run();
        ik_suspend_maybe_restore();
        ik_sram_flush(0);
        work_end = now_s();
        {
            /* The resume/autosave hooks are intentionally retained exactly
             * as in #25; only add elapsed-time observation after them.
             */
            const double work=work_end-work_start;
            if (ikprof_direct) {
                ++ikprof_direct_frames;
                ikprof_direct_work+=work;
                if (work>1.0/60.0988) ++ikprof_direct_over_16;
                if (work>1.0/30.0) ++ikprof_direct_over_33;
            } else {
                ++ikprof_bios_frames;
                ikprof_bios_work+=work;
                if (work>1.0/60.0988) ++ikprof_bios_over_16;
                if (work>1.0/30.0) ++ikprof_bios_over_33;
            }
        }''')

once('    test_elapsed = now_s() - start;\n',
     '    test_elapsed = now_s() - start;\n'
     '    ikprof_in_run=0;\n')

summary=r'''
    if(ikprof_start_wall>0.0) {
        double bios_wall=(ikprof_switch_wall>0.0)
                         ? ikprof_switch_wall-ikprof_start_wall : test_elapsed;
        double direct_wall=(ikprof_switch_wall>0.0)
                           ? test_elapsed-bios_wall : 0.0;
        double bios_video=(ikprof_switch_wall>0.0)
                          ? ikprof_bios_video_at_switch : g_video_seconds;
        double direct_video=(ikprof_switch_wall>0.0)
                            ? g_video_seconds-bios_video : 0.0;
        double bios_nonvideo=ikprof_bios_work-bios_video;
        double direct_nonvideo=ikprof_direct_work-direct_video;
        if(bios_nonvideo<0.0)bios_nonvideo=0.0;
        if(direct_nonvideo<0.0)direct_nonvideo=0.0;
        log_printf("BIOS PROFILE : switch=%s elapsed=%.3f s frames=%lu actual_fps=%.2f\n",
            ikprof_switch_wall>0.0?"YES":"NO",bios_wall,ikprof_bios_frames,
            bios_wall>0.0?(double)ikprof_bios_frames/bios_wall:0.0);
        log_printf("BIOS COST    : work_ms=%.3f video_ms=%.3f nonvideo_ms=%.3f over16=%lu over33=%lu\n",
            ikprof_bios_frames>0?ikprof_bios_work*1000.0/ikprof_bios_frames:0.0,
            ikprof_bios_frames>0?bios_video*1000.0/ikprof_bios_frames:0.0,
            ikprof_bios_frames>0?bios_nonvideo*1000.0/ikprof_bios_frames:0.0,
            ikprof_bios_over_16,ikprof_bios_over_33);
        log_printf("BIOS AUDIO   : recover=%lu dropped=%lu late=%lu\n",
            ikprof_switch_wall>0.0?ikprof_bios_recover_at_switch:g_audio_recoveries,
            ikprof_switch_wall>0.0?ikprof_bios_drop_at_switch:g_audio_frames_dropped,
            ikprof_switch_wall>0.0?ikprof_bios_late_at_switch:g_late_frames);
        if(ikprof_switch_wall>0.0) {
            log_printf("DIRECT PROFILE: elapsed=%.3f s frames=%lu actual_fps=%.2f\n",
                direct_wall,ikprof_direct_frames,
                direct_wall>0.0?(double)ikprof_direct_frames/direct_wall:0.0);
            log_printf("DIRECT COST   : work_ms=%.3f video_ms=%.3f nonvideo_ms=%.3f over16=%lu over33=%lu\n",
                ikprof_direct_frames>0?ikprof_direct_work*1000.0/ikprof_direct_frames:0.0,
                ikprof_direct_frames>0?direct_video*1000.0/ikprof_direct_frames:0.0,
                ikprof_direct_frames>0?direct_nonvideo*1000.0/ikprof_direct_frames:0.0,
                ikprof_direct_over_16,ikprof_direct_over_33);
            log_printf("DIRECT AUDIO  : recover=%lu dropped=%lu late=%lu\n",
                g_audio_recoveries-ikprof_bios_recover_at_switch,
                g_audio_frames_dropped-ikprof_bios_drop_at_switch,
                g_late_frames-ikprof_bios_late_at_switch);
        }
    }
'''
once('    log_printf("\\nFINAL PERF2\\n");\n',
     '    log_printf("\\nFINAL PERF2\\n");\n'+summary)

p.write_text(src,"utf-8")
print("IK CORE BIOS PROFILE: passive frontend-only phase instrumentation integrated.")
