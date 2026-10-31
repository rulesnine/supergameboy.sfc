#!/usr/bin/env python3
"""Append an independent N-SPC bridge to patched Ik Core #117 Snes9x libretro.
Requires tools/apply_sgbpack.py BEFORE this patch.
No change to SNES firmware, KOF ROM, the stable #43 core or libretro ABI.
"""
from pathlib import Path
import sys

HEAD = r'''
/* Ik Core Fase 6 experimental N-SPC backend exports.
 * These are NOT a second GB emulator: retro_run is only used to bootstrap
 * the original SGB firmware. After handoff, the host calls this audio-only
 * bridge; the old internal GB CPU does NOT advance.
 */
#ifdef IKCORE_SGB_HYBRID_AUDIO
extern "C" {
__attribute__((visibility("default")))
int ikcore_spc_boot_ready(void) {
    return S9xSGBPerfAudioActive() ? 1 : 0;
}
__attribute__((visibility("default")))
int ikcore_spc_send_sound(const unsigned char *packet, unsigned len) {
    if (!packet || len < 16 || (packet[0] >> 3) != 0x08 ||
        !S9xSGBPerfAudioActive()) return 0;
    S9xSGBPerfSoundCommand(packet, len);
    return 1;
}
__attribute__((visibility("default")))
int ikcore_spc_send_sou_trn(const unsigned char *data, unsigned bytes) {
    if (!data || bytes != 4096u || !S9xSGBPerfAudioActive()) return 0;
    S9xSGBPerfSouTrn(data);
    return 1;
}
__attribute__((visibility("default")))
int ikcore_spc_frame(void) {
    if (!S9xSGBPerfAudioActive()) return 0;
#ifdef IKCORE_SGB_PERF_AUDIO_THREADED
    /* Keep SPC work synchronized on the main emulation thread for this
     * first hybrid integration. Threaded #117 dispatch is disabled
     * in the isolated SPC-only module to avoid concurrent DSP mutation. */
#endif
    S9xSGBPerfAudioFrame();
    return 1;
}
__attribute__((visibility("default")))
int ikcore_spc_pull_stereo(short *out, int frames) {
    if (!out || frames <= 0 || frames > 8192 || !S9xSGBPerfAudioActive())
        return 0;
    int available = S9xSpcOutAvailable() / 2;
    if (frames > available) frames = available;
    if (frames <= 0) return 0;
    return S9xPullSpcOutput(out, frames * 2) / 2;
}
__attribute__((visibility("default")))
int ikcore_spc_pending_frames(void) {
    if (!S9xSGBPerfAudioActive()) return 0;
    return S9xSpcOutAvailable() / 2;
}
} // extern C
#endif
'''
def patch(s):
    marker = '/* Ik Core Fase 6 experimental N-SPC backend exports.'
    if marker in s:
        raise ValueError('SPC bridge already present')
    # At EOF, all declarations visible through existing apu/sgb includes.
    if '#include "apu/apu.h"' not in s:
        raise ValueError('Pinned Snes9x libretro.cpp has changed')
    return s + "\n" + HEAD
if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit('Usage: patch_snes9x_spc_exports.py Snes9x/libretro/libretro.cpp')
    p=Path(sys.argv[1]); p.write_text(patch(p.read_text()))
    print('PASS: exported SPC-only audio bridge from existing Ik Core #117 engine')
