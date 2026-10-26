/* Ik Core: final C++-to-SPC handoff adapter (phase 2).
 * This file MUST only link into the patched Ik Core #43 Snes9x host, not
 * mGBA's standalone libretro library. No duplicated SNES APU implementation.
 * The host calls ikcore_sgb_spc_dispatch_frame() on the GB emulation thread
 * once per frame, after producing GB pixels and BEFORE accepting next input.
 */
#include "ikcore_sgb_audio_fifo.h"
#include <stdint.h>
/* Existing functions in Ik Core #43 Snes9x apu.cpp:
 * S9xSGBPerfSoundCommand copies port command into the SPC worker FIFO;
 * S9xSGBPerfSouTrn copies exactly 4096 bytes into the worker event stream. */
void S9xSGBPerfSoundCommand(const uint8_t *packet,uint32_t length);
void S9xSGBPerfSouTrn(const uint8_t *data_4k);

static void send_sound(const uint8_t *packet,unsigned length,void *) {
    S9xSGBPerfSoundCommand(packet,(uint32_t)length);
}
static void send_transfer(const uint8_t *data,unsigned length,void *) {
    if(length==IKCORE_SGB_AUDIO_TRANSFER_BYTES)
        S9xSGBPerfSouTrn(data);
}
/* The SPC queue's begin/end frame and resampler stay owned by Ik Core's
 * existing SNES audio runtime. Never call those twice from this bridge. */
extern "C" unsigned ikcore_sgb_spc_dispatch_frame(void) {
    return ikcore_sgb_audio_drain(send_sound,send_transfer,nullptr);
}
