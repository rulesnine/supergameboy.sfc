#!/usr/bin/env python3
"""Fix F6 audio pipeline WITHOUT changing stable F5/#26 or #43.

Root cause from physical #21:
- Audio device EBUSY -> the ALSA sink discarded before calling
  ik_f6_spc_mix_one; 3,934,720 GB audio samples dropped, 0 SPC mixed;
  SPC FIFO accumulated at 16384 frames even though SOUND 318/318.
- Snes9x SPC output was resampled to ALSA Hz (32040 if ALSA failed)
  rather than actual mGBA callback Hz (32768): drift.

This patch mixes GB+SPC at *mGBA INPUT* rate upstream of the ALSA guard,
then performs ALSA output resampling. On EBUSY it still consumes SPC PCM,
accurately reports silent physical output and retries safely with dmix/
several delays; never kills processes, steals ALSA, or changes system config.
"""
from pathlib import Path
import sys

def once(s,a,b,label):
    n=s.count(a)
    if n!=1:raise ValueError(f"{label}: expected 1 match, got {n}")
    return s.replace(a,b,1)

NEW_WRAPPER=r'''static size_t audio_batch_cb(const int16_t *data, size_t frames)
{
    size_t pos = 0;
    if (!data || !frames)
        return audio_device_batch_cb(data, frames);
    while (pos < frames) {
        size_t i, chunk = frames-pos;
        int16_t mixed[256 * 2];
        if (chunk > 256) chunk=256;
        memcpy(mixed, data + pos*2, chunk*2*sizeof(int16_t));

        /* Always consume actual SPC samples, even if ALSA is busy.
         * Prior F6 mixed inside audio_device_batch_cb, AFTER an early
         * !g_alsa_ready discard: no mix ever happened when ALSA EBUSY. */
        if (g_f6_ready) {
            for (i=0;i<chunk;i++)
                ik_f6_spc_mix_one(&g_f6_spc,&mixed[2*i],&mixed[2*i+1]);
        }
        if (!g_alsa_ready ||
            g_audio_rate == g_ik_rate_adapter.input_rate) {
            (void)audio_device_batch_cb(mixed,chunk);
        } else {
            int16_t converted[1024 * 2];
            size_t produced=ik_audio_rate_convert(&g_ik_rate_adapter,
                                                   mixed,chunk,converted,1024);
            if (produced == SIZE_MAX) {
                g_audio_frames_dropped+=(unsigned long)chunk;
                log_printf("ERROR ALSA: GB+SPC output resampler overflow\n");
            } else if(produced) {
                (void)audio_device_batch_cb(converted,produced);
            }
        }
        pos+=chunk;
    }
    return frames;
}

'''
def patch(s):
    s=once(s,
      '''    for (i = 0; i < frames; ++i) {
        int16_t l = data[i * 2u + 0u], r = data[i * 2u + 1u];
        if (g_f6_ready) ik_f6_spc_mix_one(&g_f6_spc, &l, &r);
        g_audio_ring[g_audio_ring_write * 2u + 0u] = l;
        g_audio_ring[g_audio_ring_write * 2u + 1u] = r;''',
      '''    for (i = 0; i < frames; ++i) {
        g_audio_ring[g_audio_ring_write * 2u + 0u] = data[i * 2u + 0u];
        g_audio_ring[g_audio_ring_write * 2u + 1u] = data[i * 2u + 1u];''',
      "remove now-too-late internal mixing")
    start=s.find("static size_t audio_batch_cb(const int16_t *data, size_t frames)\n{")
    end=s.find("static void audio_sample_cb(int16_t left, int16_t right)\n{",start)
    if start<0 or end<0:raise ValueError("resampler wrapper range missing")
    s=s[:start]+NEW_WRAPPER+s[end:]
    # If ALSA failed, g_audio_rate remains 32040, but mGBA is 32768.
    # Match SPC audio to mGBA input first, then resample merged audio to ALSA.
    s=once(s,'ik_f6_select_pack(argc,argv),g_audio_rate,log_printf)',
             'ik_f6_select_pack(argc,argv),'
             '(unsigned)(avinfo.timing.sample_rate+0.5),log_printf)',
             "native GB/SPC shared sample rate")
    s=once(s,
           'static const char *devices[] = {"default", "plughw:0,0", "hw:0,0"};',
           'static const char *devices[] = {"default", "plug:dmix", "dmix", "plughw:0,0", "hw:0,0"};',
           "nonexclusive ALSA fallbacks")
    s=once(s,
           '        if(g_f6_ready) ik_f6_spc_frame(&g_f6_spc);\n        core_retro_run();',
           '''        /* ALSA may be occupied by Clover at SSH launch. Never terminate
         * or reconfigure Clover: try shared PCM, then retry only 3 times
         * in the 120-second test to avoid repeated log spam. */
        if (!g_alsa_ready && (run_frames == 120 ||
                              run_frames == 600 ||
                              run_frames == 1800)) {
            log_printf("IKF6 ALSA retry at GB frame=%lu (no process changes)\\n",
                       run_frames);
            if (init_alsa((unsigned)(avinfo.timing.sample_rate+0.5))==0)
                log_printf("IKF6 ALSA recovered=1\\n");
        }
        if(g_f6_ready) ik_f6_spc_frame(&g_f6_spc);
        core_retro_run();''',
           "safe retries")
    s=once(s,
           '    log_printf("GB source   : %s\\n",pack_path);',
           '''    if(getenv("IKF6_ORIGINAL_ARCHIVE"))
        log_printf("IKF6 ARCHIVE source: %s\\n",getenv("IKF6_ORIGINAL_ARCHIVE"));
    log_printf("GB source   : %s\\n",pack_path);''',
           "source tracking")
    s=once(s,
           '                       " SPC_frames=%llu clip=%llu\\n",',
           '                       " SPC_frames=%llu SPC_nonzero=%llu clip=%llu\\n",',
           "nonzero PCM counter print")
    s=once(s,
           '''                (unsigned long long)g_f6_spc.frames_advanced,
                (unsigned long long)g_f6_spc.clipped);''',
           '''                (unsigned long long)g_f6_spc.frames_advanced,
                (unsigned long long)g_f6_spc.spc_nonzero,
                (unsigned long long)g_f6_spc.clipped);''',
           "nonzero PCM argument")
    s=once(s,
           'log_printf("IK CORE FASE6 SGBPACK1 SINGLE FILE / mGBA + N-SPC EXPERIMENT\\n");',
           'log_printf("IK CORE FASE6 AUDIO MIX FIX / SGBPACK1 + SPC700 EXPERIMENT\\n");',
           "new build version")
    return s

if __name__ == "__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_f6_audio_mix_retry.py FRONTEND.c")
    path=Path(sys.argv[1])
    path.write_text(patch(path.read_text()))
    print("PASS: upstream SPC mixer, mGBA-rate domain, safe ALSA EBUSY retry, archive provenance")
