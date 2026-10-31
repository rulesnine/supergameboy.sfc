/* SPDX-License-Identifier: MIT
 * Standalone signed-stereo S16 rate adaptor for the NES Mini audio device.
 * Continuous streaming phase across libretro callback boundaries.
 */
#ifndef IK_AUDIO_RATE_ADAPTER_H
#define IK_AUDIO_RATE_ADAPTER_H
#include <stddef.h>
#include <stdint.h>
typedef struct {
    unsigned input_rate, output_rate;
    double position;
    int16_t previous[2];
    int initialized;
} IkAudioRateAdapter;
void ik_audio_rate_init(IkAudioRateAdapter *r, unsigned input_rate,
                        unsigned output_rate);
/* 'capacity' is output STEREO FRAMES (not int16 elements).
   Caller keeps short input slices so expected output fits capacity.
   Returns SIZE_MAX if caller's output storage is too small, without
   recording a valid state change.  */
size_t ik_audio_rate_convert(IkAudioRateAdapter *r,
                             const int16_t *in, size_t input_frames,
                             int16_t *out, size_t capacity);
#endif
