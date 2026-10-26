/* Ik Core phase 2: bounded FIFO for commands destined to the EXISTING
 * SNES SPC700/DSP worker. Not a sound synthesizer or separate SNES emulator.
 * One producer (GB core), one consumer (Ik Core per-frame host), same thread.
 */
#ifndef IKCORE_SGB_AUDIO_FIFO_H
#define IKCORE_SGB_AUDIO_FIFO_H
#include <stdint.h>
#include <stdbool.h>
enum {
  IKCORE_SGB_AUDIO_CAPACITY=16,
  IKCORE_SGB_AUDIO_TRANSFER_BYTES=4096,
  IKCORE_SGB_AUDIO_SOUND_BYTES=112
};
typedef enum {
  IKCORE_SGB_AUDIO_SOUND=1,
  IKCORE_SGB_AUDIO_TRANSFER=2
} ikcore_sgb_audio_kind;
typedef void (*ikcore_spc_packet_callback)(const uint8_t *data,unsigned len,void *user);
void ikcore_sgb_audio_reset(void);
unsigned ikcore_sgb_audio_count(void);
unsigned ikcore_sgb_audio_dropped(void);
bool ikcore_sgb_audio_queue_sound(const uint8_t *data,unsigned len);
bool ikcore_sgb_audio_queue_transfer(const uint8_t *data,unsigned len);
unsigned ikcore_sgb_audio_drain(ikcore_spc_packet_callback sound,
                                ikcore_spc_packet_callback transfer,void *user);
/* Hooks called by the general SGB packet bus and SOU_TRN 4KiB decoder. */
void ikcore_sgb_audio_sound_packet_hook(const uint8_t *data,unsigned len);
void ikcore_sgb_transfer_completed_hook(const uint8_t *payload,unsigned size);
#endif
