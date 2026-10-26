/* Ik Core / mGBA sound-transfer bridge, no SNES audio engine in this file.
 * The host must call drain after a completed GB frame on the audio-thread
 * command queue; do not invoke SPC700 directly from a GB scanline.
 */
#ifndef IKCORE_SGB_AUDIO_BRIDGE_H
#define IKCORE_SGB_AUDIO_BRIDGE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define IKCORE_SGB_AUDIO_EVENTS 16
#define IKCORE_SGB_SOU_BYTES 4096
#define IKCORE_SGB_LCD_WIDTH 160
#define IKCORE_SGB_COMMAND_SOUND 8
#define IKCORE_SGB_COMMAND_SOU_TRN 9
typedef struct {
    void (*sound)(const uint8_t *packet, unsigned length, void *opaque);
    void (*sou_transfer)(const uint8_t *payload4096, void *opaque);
    void *opaque;
} ikcore_sgb_audio_sink;
void ikcore_sgb_audio_reset(void);
unsigned ikcore_sgb_audio_queued(void);
unsigned ikcore_sgb_audio_dropped(void);
unsigned ikcore_sgb_audio_completed_transfers(void);
/* mGBA hook: one completed SGB command */
void ikcore_sgb_sound_packet_hook(unsigned command,
                                 const unsigned char *data, unsigned length);
/* mGBA software-renderer hook: raw 2-bit pixel tokens for one LCD scanline;
 * MUST be called only during sgbTransfer==1 and SGB command SOU_TRN. */
void ikcore_sgb_lcd_row_hook(unsigned y, const uint8_t *row, unsigned width);
/* Return false if queue empty, SOU_TRN upload not ready, or sink missing.
 * Never reorder SOUND behind a pending SOU_TRN. */
bool ikcore_sgb_audio_dispatch_one(const ikcore_sgb_audio_sink *sink);
#endif
