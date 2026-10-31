#!/usr/bin/env python3
"""Patch ONLY the generated Fase 5 mGBA frontend, never stable Ik Core #43."""
from pathlib import Path
import sys

NEW_INIT = r'''static int init_alsa(unsigned rate)
{
    /* ALSA on the NES Mini rejected mGBA's 32768 Hz with EINVAL.
       Negotiate a playable hardware rate, then resample from the source.
       Try the stable Ik Core family (32040 Hz) before common PCM rates.
       Reopen the device for each attempt: failed hw_params may leave it in
       a non-reusable state. Never play 32768 samples at 32000 Hz directly. */
    static const char *devices[] = {"default", "plughw:0,0", "hw:0,0"};
    unsigned rates[] = {rate, 32040u, 32000u, 48000u, 44100u};
    size_t d, i;
    int rc = -EINVAL;
    if (load_alsa() != 0) return -1;
    for (d = 0; d < sizeof devices / sizeof devices[0]; ++d) {
        for (i = 0; i < sizeof rates / sizeof rates[0]; ++i) {
            snd_pcm_t *candidate = NULL;
            unsigned hz = rates[i];
            size_t j;
            int duplicate = 0;
            for (j = 0; j < i; ++j)
                if (rates[j] == hz) duplicate = 1;
            if (duplicate) continue;
            rc = p_snd_pcm_open(&candidate, devices[d],
                                SND_PCM_STREAM_PLAYBACK, SND_PCM_NONBLOCK);
            if (rc < 0 || !candidate) {
                if (candidate) p_snd_pcm_close(candidate);
                if (!i) log_printf("ALSA probe  : %s open fallo: %s\n",
                                   devices[d], p_snd_strerror(rc));
                break; /* device unavailable: different sample rate won't help */
            }
            rc = p_snd_pcm_set_params(candidate, SND_PCM_FORMAT_S16_LE,
                                     SND_PCM_ACCESS_RW_INTERLEAVED, 2, hz,
                                     1, 100000);
            if (rc >= 0) rc = p_snd_pcm_prepare(candidate);
            if (rc == 0) {
                g_pcm = candidate;
                g_audio_rate = hz;
                ik_audio_rate_init(&g_ik_rate_adapter, rate, hz);
                g_alsa_ready = 1;
                log_printf("ALSA        : OK, %s stereo S16_LE %u Hz"
                           " (mGBA input=%u Hz, resample=%s)\n",
                           devices[d], hz, rate, hz==rate ? "NO" : "SI");
                return 0;
            }
            log_printf("ALSA probe  : %s %u Hz -> %s\n",
                       devices[d], hz, p_snd_strerror(rc));
            p_snd_pcm_close(candidate);
        }
    }
    log_printf("ERROR ALSA  : ningun dispositivo/frecuencia compatible"
               " para %u Hz de entrada\n", rate);
    return -1;
}'''

WRAPPER = r'''static size_t audio_batch_cb(const int16_t *data, size_t frames)
{
    size_t pos = 0;
    /* Existing ALSA queue reports discarded samples safely if unavailable. */
    if (!g_alsa_ready || !data || !frames ||
        g_audio_rate == g_ik_rate_adapter.input_rate)
        return audio_device_batch_cb(data, frames);
    while (pos < frames) {
        int16_t converted[1024 * 2];
        size_t chunk = frames - pos;
        size_t produced;
        if (chunk > 256) chunk = 256;
        produced = ik_audio_rate_convert(&g_ik_rate_adapter, data+pos*2,
                                          chunk, converted, 1024);
        if (produced == SIZE_MAX) {
            g_audio_frames_dropped += (unsigned long)chunk;
            log_printf("ERROR ALSA  : overflow del adaptador de audio\n");
            return frames;
        }
        if (produced) (void)audio_device_batch_cb(converted, produced);
        pos += chunk;
    }
    return frames;
}

'''

def once(s, a, b, name):
    n = s.count(a)
    if n != 1:
        raise ValueError(f"{name}: expected one anchor, got {n}")
    return s.replace(a,b,1)

def patch(s):
    s = once(s, '#include "libretro.h"\n',
             '#include "libretro.h"\n#include "ik_audio_rate_adapter.h"\n',
             'resampler header')
    s = once(s, 'static unsigned g_audio_rate = 32040;\n',
             'static unsigned g_audio_rate = 32040;\n'
             'static IkAudioRateAdapter g_ik_rate_adapter;\n',
             'resampler state')
    beg = s.find('static int init_alsa(unsigned rate)\n{')
    end = s.find('\nstatic void close_alsa(void)', beg)
    if beg<0 or end<0: raise ValueError('missing init_alsa function')
    s = s[:beg] + NEW_INIT + '\n' + s[end:]
    s = once(s, 'static size_t audio_batch_cb(const int16_t *data, size_t frames)',
             'static size_t audio_device_batch_cb(const int16_t *data, size_t frames)',
             'original ALSA queue')
    s = once(s, 'static void audio_sample_cb(int16_t left, int16_t right)\n',
             WRAPPER + 'static void audio_sample_cb(int16_t left, int16_t right)\n',
             'audio wrapper')
    return s

if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('Usage: patch_mgba_alsa_resample.py FRONTEND.c')
    path = Path(sys.argv[1])
    path.write_text(patch(path.read_text()))
    print('PASS: dedicated mGBA frontend ALSA fallback and rate conversion patched')
