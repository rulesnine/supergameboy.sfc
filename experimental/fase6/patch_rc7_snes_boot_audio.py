#!/usr/bin/env python3
"""Send native Snes9x 32040Hz PCM to ALSA at exact pitch, never to mGBA's
32768Hz resampler. Keep SNES and mGBA resampler states totally independent.
"""
from pathlib import Path
import sys
def once(s,old,new,what):
    n=s.count(old)
    if n!=1:raise ValueError(f"{what}: expected 1 anchor got {n}")
    return s.replace(old,new,1)
def patch(s):
    helper=r'''
/* Snes9x firmware runs at 32040Hz. mGBA may generate 32768Hz.
 * Do NOT use audio_batch_cb here: it is bound to mGBA's rate adapter.
 * The original SNES waveform goes straight to ALSA if hardware supports
 * 32040Hz; otherwise resample from 32040Hz with a dedicated rate state. */
static IkAudioRateAdapter ik_rc7_boot_rate;
static unsigned ik_rc7_boot_rate_init_hz=0;
static size_t ik_rc7_boot_pcm_cb(const int16_t *src,size_t frames) {
    size_t pos=0;
    if(!src || !frames || !g_alsa_ready)return frames;
    if(g_audio_rate==32040u)return audio_device_batch_cb(src,frames);
    if(ik_rc7_boot_rate_init_hz!=g_audio_rate) {
        ik_audio_rate_init(&ik_rc7_boot_rate,32040u,g_audio_rate);
        ik_rc7_boot_rate_init_hz=g_audio_rate;
        log_printf("IKSPC BOOT PCM: SNES=32040 ALSA=%u independent_resample=1\n",g_audio_rate);
    }
    while(pos<frames) {
        int16_t out[1024u*2u];
        size_t chunk=frames-pos,produced;
        if(chunk>256u)chunk=256u;
        produced=ik_audio_rate_convert(&ik_rc7_boot_rate,src+pos*2u,
                                        chunk,out,1024u);
        if(produced==SIZE_MAX) {
            log_printf("IKSPC BOOT PCM: rate adapter overflow\n");
            return frames;
        }
        if(produced)(void)audio_device_batch_cb(out,produced);
        pos+=chunk;
    }
    return frames;
}
'''
    s=once(s,"int main(int argc, char **argv)\n{",helper+"\nint main(int argc, char **argv)\n{","helper placement")
    s=once(s,"ik_f6_spc_set_boot_audio(audio_batch_cb);",
           "ik_f6_spc_set_boot_audio(ik_rc7_boot_pcm_cb);","own 32040Hz stream")
    return s
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("usage: patch_rc7_snes_boot_audio.py FRONTEND.c")
    file=Path(sys.argv[1]);file.write_text(patch(file.read_text()))
    print("PASS: SNES firmware native 32040 PCM, isolated from mGBA 32768 rate adapter")
