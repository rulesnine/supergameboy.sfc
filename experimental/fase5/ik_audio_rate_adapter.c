/* SPDX-License-Identifier: MIT */
#include "ik_audio_rate_adapter.h"
#include <string.h>
#include <stdint.h>
void ik_audio_rate_init(IkAudioRateAdapter *r, unsigned input_rate,
                        unsigned output_rate) {
    if (!r) return;
    memset(r, 0, sizeof(*r));
    r->input_rate = input_rate;
    r->output_rate = output_rate;
}
size_t ik_audio_rate_convert(IkAudioRateAdapter *r, const int16_t *in,
                             size_t input_frames, int16_t *out,
                             size_t capacity) {
    double p, step;
    size_t produced = 0;
    int16_t prev_l, prev_r;
    int was_initialized;
    if (!r || !in || !out || !r->input_rate || !r->output_rate) return SIZE_MAX;
    if (!input_frames) return 0;
    if (r->input_rate == r->output_rate) {
        if (capacity < input_frames) return SIZE_MAX;
        memcpy(out, in, input_frames * 2 * sizeof(*in));
        return input_frames;
    }
    was_initialized = r->initialized;
    p = r->position;
    prev_l = r->previous[0];
    prev_r = r->previous[1];
    if (!was_initialized) {
        /* A fixed first-point hold avoids interpolating from silence. */
        prev_l = in[0]; prev_r = in[1]; p = 1.0;
    }
    step = (double)r->input_rate / (double)r->output_rate;
    /* index zero is previous block's last frame. Index 1 is input[0].
       Defer the final point until the next callback so interpolation has
       actual neighboring samples instead of duplicating the boundary. */
    while (p < (double)input_frames) {
        size_t idx = (size_t)p;
        double f = p - (double)idx;
        double a_l = idx ? in[(idx - 1) * 2] : prev_l;
        double a_r = idx ? in[(idx - 1) * 2 + 1] : prev_r;
        double b_l = in[idx * 2], b_r = in[idx * 2 + 1];
        if (produced >= capacity) return SIZE_MAX;
        out[produced * 2] = (int16_t)(a_l + (b_l - a_l) * f);
        out[produced * 2 + 1] = (int16_t)(a_r + (b_r - a_r) * f);
        ++produced;
        p += step;
    }
    r->position = p - (double)input_frames;
    r->previous[0] = in[(input_frames - 1) * 2];
    r->previous[1] = in[(input_frames - 1) * 2 + 1];
    r->initialized = 1;
    return produced;
}
