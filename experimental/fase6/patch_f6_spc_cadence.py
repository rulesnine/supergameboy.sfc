#!/usr/bin/env python3
"""F6-only N-SPC timing adapter; applied AFTER tools/apply_sgbpack.py.

The legacy #117 SPC frame driver assumes ~60.099 SNES fps.
mGBA GB SGB video reports ~59.7275 fps. The existing F6 host clocks
one SPC frame per mGBA frame, so using SNES fps underproduces PCM by ~0.62%,
consistent with F6 #26 underflows (32,593 samples over 120 seconds).

Leave all legacy #117 APIs unchanged. Add a new F6 function to adjust
the SPC700 *cycles per frontend GB frame* to measured libretro GB fps.
With N-SPC running at 1,024,000 cycles/s, this preserves realtime pitch
and tempo while eliminating an avoidable FIFO deficit.
"""
from pathlib import Path
import sys

def once(s,a,b,label):
    n=s.count(a)
    if n!=1: raise ValueError(f"{label}: expected one anchor, found {n}")
    return s.replace(a,b,1)

def patch(root):
    h=root/"apu"/"apu.h"
    s=h.read_text()
    a="""void  S9xSGBPerfAudioFrame(void);
void  S9xSGBPerfSoundCommand"""
    b="""void  S9xSGBPerfAudioFrame(void);
void  S9xSGBPerfAudioSetFrameHz(double hz);
void  S9xSGBPerfSoundCommand"""
    s=once(s,a,b,"F6-only audio rate declaration")
    h.write_text(s)

    c=root/"apu"/"apu.cpp"
    s=c.read_text()
    a="""constexpr double IK_PERF_SMP_PER_FRAME =
    1024000.0 / 60.09881389744051;
}"""
    b="""static double ik_f6_cycles_per_gb_frame = 1024000.0 / 60.09881389744051;
}

/* F6-only: one SPC step is driven by one *mGBA* GB frame, not one SNES frame.
   Set Hz once after BIOS boot, before the first GB gameplay step. */
void S9xSGBPerfAudioSetFrameHz(double hz)
{
    if (hz >= 50.0 && hz <= 65.0)
        ik_f6_cycles_per_gb_frame = 1024000.0 / hz;
}"""
    s=once(s,a,b,"clock nominal cycles/s")
    s=once(s,"ik_perf_smp_frac += IK_PERF_SMP_PER_FRAME;",
           "ik_perf_smp_frac += ik_f6_cycles_per_gb_frame;",
           "SPC frame consumes correctly paced cycles")
    c.write_text(s)
    print("PASS: isolated SPC frame timing tracks libretro GB timing without modifying #117")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_f6_spc_cadence.py SNES9X_ROOT")
    patch(Path(sys.argv[1]))
