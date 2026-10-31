#ifndef IK_SGB_BOOT_AV_H
#define IK_SGB_BOOT_AV_H
#include <stdint.h>
#include <stddef.h>
/* Record genuine SGB1 SNES BIOS output, generated LOCALLY from user firmware.
 * No BIOS pictures, music or samples are distributed with the HMOD.
 * Game state cache remains unchanged; this visual/audio cache is separate. */
int ikboot_has(uint64_t hash);
void ikboot_begin(uint64_t hash);
void ikboot_video(const uint16_t *rgb565,unsigned firmware_frame);
void ikboot_audio(const int16_t *stereo,size_t frames);
void ikboot_end(int successful);
int ikboot_play(uint64_t hash,
                void (*video)(const uint16_t *,unsigned),
                size_t (*audio)(const int16_t *,size_t),
                int (*cancel)(void),
                void (*log)(const char *,...));
#endif
