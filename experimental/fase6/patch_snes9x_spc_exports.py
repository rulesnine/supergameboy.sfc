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
/*
 * Fase 6: restore #137's verified SGB v1.2 SNES sound mailbox in the
 * non-threaded SPC-only backend (not the old SNES/GB renderer).
 *
 * SNES CPU ports $2140..$2143 correspond to CPU.port_write(0..3).
 * Original SGB BIOS $00:BABA-$00:BB0D sends two 16-bit words, waits
 * for the matching SPC echo, retries for up to 0x80 frames and emits a
 * zero A/B/score idle transaction with the attribute byte preserved.
 * Without idle/echo, repeated KOF96 typewriter SFX are lost or clipped.
 *
 * Unlike older #137 threaded audio, F6 is single-threaded: mGBA queues
 * SOUND after the GB frame, this mailbox dispatches one transaction at
 * a time, then clocks the actual N-SPC in the following F6 frame.
 */
namespace {
enum { IK_F6_SOUND_FIFO = 4096 };
struct IkF6MailEvent { uint8_t p[4]; };
static IkF6MailEvent ik_f6_events[IK_F6_SOUND_FIFO];
static unsigned ik_f6_rd=0, ik_f6_len=0, ik_f6_echo_wait=0;
static uint8_t ik_f6_last[4]={}, ik_f6_echo[4]={};
static uint8_t ik_f6_attrs=0;
static bool ik_f6_await=false, ik_f6_idle_due=false;
static uint64_t ik_f6_rx=0, ik_f6_sent=0, ik_f6_idle=0;
static uint64_t ik_f6_ack=0, ik_f6_retries=0, ik_f6_timeout=0;
static uint64_t ik_f6_rejected=0, ik_f6_maxwait=0;
static void ik_f6_write_ports(const uint8_t *p) {
    /* Original BIOS stages $0341(SFX A), $0342(SFX B),
       $0343(attributes), and finally $0340(score trigger). */
    SNES::cpu.port_write(1,p[0]);
    SNES::cpu.port_write(2,p[1]);
    SNES::cpu.port_write(3,p[2]);
    SNES::cpu.port_write(0,p[3]);
}
static void ik_f6_write_and_wait(const uint8_t *p) {
    ik_f6_write_ports(p);
    for (unsigned i=0;i<4;++i) ik_f6_last[i]=p[i];
    ik_f6_await=true;
    ik_f6_echo_wait=0;
}
static void ik_f6_dispatch_mailbox() {
    if(ik_f6_await) {
        /* Read SPC-to-SNES ports in the A/B/attrs/score order, but
           compare all four, not just the trigger/music byte. */
        ik_f6_echo[0]=(uint8_t)SNES::smp.port_read(1);
        ik_f6_echo[1]=(uint8_t)SNES::smp.port_read(2);
        ik_f6_echo[2]=(uint8_t)SNES::smp.port_read(3);
        ik_f6_echo[3]=(uint8_t)SNES::smp.port_read(0);
        bool acknowledged=true;
        for(unsigned i=0;i<4;++i)
            if(ik_f6_echo[i]!=ik_f6_last[i]) acknowledged=false;
        if(!acknowledged && ik_f6_echo_wait<0x80u) {
            ik_f6_write_ports(ik_f6_last);
            ++ik_f6_echo_wait;
            ++ik_f6_retries;
            if(ik_f6_echo_wait>ik_f6_maxwait)
                ik_f6_maxwait=ik_f6_echo_wait;
            return;
        }
        if(acknowledged) ++ik_f6_ack; else ++ik_f6_timeout;
        ik_f6_echo_wait=0;
        ik_f6_await=false;
    }
    if(ik_f6_idle_due) {
        const uint8_t idle[4]={0,0,ik_f6_attrs,0};
        ik_f6_write_and_wait(idle);
        ik_f6_idle_due=false;
        ++ik_f6_idle;
        return;
    }
    if(!ik_f6_len) return;
    const IkF6MailEvent e=ik_f6_events[ik_f6_rd];
    ik_f6_rd=(ik_f6_rd+1u)%IK_F6_SOUND_FIFO;
    --ik_f6_len;
    ik_f6_write_and_wait(e.p);
    ik_f6_attrs=e.p[2];
    ik_f6_idle_due=e.p[0]||e.p[1]||e.p[3];
    ++ik_f6_sent;
}
} // namespace
extern "C" {
__attribute__((visibility("default")))
int ikcore_spc_boot_ready(void) {
    return S9xSGBPerfAudioActive() ? 1 : 0;
}
/* Called ONLY after successful Snes9x savestate restore. The validated #40
 * SPC RAM and DSP registers come from that state; the transient PERF2
 * activation flag was outside the savestate and must be re-enabled. */
__attribute__((visibility("default")))
int ikcore_spc_cache_restore_activate(void) {
    if(!S9xSGBPerfAudioActive()) {
        S9xSGBEnterPerfDirectMode();
        S9xSGBPerfAudioEnable();
        Settings.SGB_BIOSModeActive=FALSE;
        Settings.SuperGameBoy=TRUE;
        Settings.PAL=FALSE;
        Settings.FrameTime=Settings.FrameTimeNTSC;
    }
    ik_f6_rd=ik_f6_len=ik_f6_echo_wait=0;
    ik_f6_await=ik_f6_idle_due=false;
    ik_f6_rx=ik_f6_sent=ik_f6_idle=ik_f6_ack=ik_f6_retries=0;
    ik_f6_timeout=ik_f6_rejected=ik_f6_maxwait=0;
    return S9xSGBPerfAudioActive()?1:0;
}
__attribute__((visibility("default")))
int ikcore_spc_send_sound(const unsigned char *packet, unsigned len) {
    if (!packet || len < 16 || (packet[0] >> 3) != 0x08 ||
        !S9xSGBPerfAudioActive()) return 0;
    /* Acceptance means queued, NOT yet acknowledged or audible. */
    if(ik_f6_len>=IK_F6_SOUND_FIFO) {
        ++ik_f6_rejected;
        return 0;
    }
    IkF6MailEvent &e=ik_f6_events[(ik_f6_rd+ik_f6_len)%IK_F6_SOUND_FIFO];
    e.p[0]=packet[1]; e.p[1]=packet[2];
    e.p[2]=packet[3]; e.p[3]=packet[4];
    ++ik_f6_len;
    ++ik_f6_rx;
    return 1;
}
__attribute__((visibility("default")))
int ikcore_spc_send_sou_trn(const unsigned char *data, unsigned bytes) {
    if (!data || bytes != 4096u || !S9xSGBPerfAudioActive()) return 0;
    S9xSGBPerfSouTrn(data);
    return 1;
}
__attribute__((visibility("default")))
int ikcore_spc_set_frame_fps(double fps) {
    if (fps < 50.0 || fps > 65.0) return 0;
    S9xSGBPerfAudioSetFrameHz(fps);
    return 1;
}
__attribute__((visibility("default")))
int ikcore_spc_frame(void) {
    if (!S9xSGBPerfAudioActive()) return 0;
    /* No worker thread in F6. Preserve #137 ordered mailbox semantics
       while keeping the SNES CPU/PPU stopped after firmware handoff. */
    ik_f6_dispatch_mailbox();
    S9xSGBPerfAudioFrame();
    return 1;
}
__attribute__((visibility("default")))
int ikcore_spc_mailbox_stats(uint64_t *out, unsigned count) {
    if(!out || count<9u) return 0;
    out[0]=ik_f6_rx; out[1]=ik_f6_sent; out[2]=ik_f6_idle;
    out[3]=ik_f6_ack; out[4]=ik_f6_retries; out[5]=ik_f6_timeout;
    out[6]=ik_f6_len; out[7]=ik_f6_maxwait; out[8]=ik_f6_rejected;
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
